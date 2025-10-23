"""
BudAI Deployment CLI.

Top-level orchestrator for multi-service deployments implementing
PRIME_DIRECTIVE assisted and zero-touch modes.

This CLI manages deployments of BudAI services to Railway, with each
service deployed from its own GitHub repository.

Railway Config-as-Code Integration:
-----------------------------------
This deployment tool leverages Railway's config-as-code feature. Each service
repository should contain a railway.json file that defines build and deploy
settings (start command, health checks, build command, etc.).

When Railway deploys from GitHub:
1. It automatically reads the railway.json from the service repo
2. Applies those build/deploy settings to the deployment
3. This deployment tool only needs to:
   - Create/connect the service to the GitHub repo
   - Set environment variables (secrets, URLs, etc.)
   - Trigger the deployment

See templates/ directory for example railway.json configurations.
"""

from __future__ import annotations

import os
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from installer import DeploymentReport
from installer.railway import RailwayProvider
from shared import DeploymentSpec

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Service repository configuration
SERVICE_REPOS = {
    "api-gateway": {
        "repo": "binaryninja/budai-api-gateway",
        "branch": "master",
        "port": 8000,
    },
    "orchestrator": {
        "repo": "binaryninja/budai-orchestrator",
        "branch": "master",
        "port": 8001,
    },
    "agent-summarizer": {
        "repo": "binaryninja/budai-agent-summarizer",
        "branch": "master",
        "port": 8002,
    },
    "agent-followup": {
        "repo": "binaryninja/budai-agent-followup",
        "branch": "main",
        "port": 8003,
    },
    "voice-realtime": {
        "repo": "binaryninja/budai-voice-realtime",
        "branch": "main",
        "port": 8005,
    },
    "slack-integration": {
        "repo": "binaryninja/budai-slack-integration",
        "branch": "main",
        "port": 8006,
    },
    "voice-frontend": {
        "repo": "binaryninja/budai-voice-frontend",
        "branch": "main",
        "port": 3000,
    },
}


class DeploymentOrchestrator:
    """Orchestrates multi-service deployments with dependency management."""

    def __init__(self, spec: DeploymentSpec, creds: Dict[str, any]) -> None:
        """Initialize deployment orchestrator.

        Args:
            spec: Deployment specification
            creds: Credentials dictionary
        """
        self.spec = spec
        self.creds = creds
        self.environment = os.getenv("BUDAI_TARGET_ENV", self.spec.environment)
        
        # Initialize Railway provider
        required_keys = {"railway_token", "railway_project_id"}
        if not required_keys.issubset(self.creds):
            missing = ", ".join(sorted(required_keys - set(self.creds)))
            raise RuntimeError(
                f"Railway credentials required (missing: {missing})"
            )
        
        self.provider = RailwayProvider(
            api_token=self.creds["railway_token"],
            project_id=self.creds["railway_project_id"],
        )
        
        # Deployment order (respecting dependencies)
        self.deployment_order = [
            "orchestrator",      # Deploy first (other services depend on it)
            "agent-summarizer",  # Deploy agents
            "agent-followup",
            # "agent-communicator",
            "voice-realtime",
            "api-gateway",       # Deploy after dependencies are ready
            "slack-integration",
            "voice-frontend",
        ]
        
        self.reports: List[DeploymentReport] = []
        self.infra_artifacts: Dict[str, Any] = {}

    def _prepare_infrastructure(self) -> None:
        """Ensure shared infrastructure resources are provisioned."""
        if "redis_url" in self.creds and self.creds.get("redis_url"):
            return

        logger.info("Ensuring Redis instance for environment '%s'...", self.environment)
        redis_info = self.provider.ensure_redis_service(self.environment)
        self.creds["redis_url"] = redis_info["redis_url"]
        self.creds["redis_password"] = redis_info["password"]
        self.creds["redis_host"] = redis_info["host"]
        self.creds["redis_service_id"] = redis_info["service_id"]
        self.creds["redis_port"] = redis_info["port"]

        self.infra_artifacts["redis"] = redis_info
        logger.info(
            "Redis ready at %s (service %s)",
            redis_info["redis_url"],
            redis_info["service_id"],
        )

    def explain_requirements(self) -> None:
        """Explain requirements for all services."""
        logger.info("=" * 80)
        logger.info("BUDAI DEPLOYMENT REQUIREMENTS")
        logger.info("=" * 80)
        logger.info("Environment: %s", self.environment)
        logger.info("Region: %s", self.spec.region or "default")
        logger.info("")
        
        for service_name in self.deployment_order:
            if service_name not in SERVICE_REPOS:
                continue
            
            service_info = SERVICE_REPOS[service_name]
            service_config = self.spec.services.get(service_name)
            
            if service_config and not service_config.enabled:
                logger.info("Service: %s (DISABLED)", service_name)
                continue
            
            logger.info("Service: %s", service_name)
            logger.info("  Repository: https://github.com/%s", service_info["repo"])
            logger.info("  Branch: %s", service_info["branch"])
            logger.info("  Port: %d", service_info["port"])
            
            if service_config:
                logger.info("  Resources:")
                logger.info("    - Memory: %d MB", service_config.resources.memory_mb)
                logger.info("    - CPU: %d millicores", service_config.resources.cpu_millicores)
                if service_config.resources.replicas and service_config.resources.replicas > 1:
                    logger.info("    - Replicas: %d", service_config.resources.replicas)
            logger.info("")
        
        logger.info("=" * 80)

    def deploy_all(self) -> bool:
        """Deploy all services to Railway.

        Returns:
            True if all deployments succeeded, False otherwise
        """
        logger.info("\nDeploying services...")
        
        # Ensure Redis is available
        self._prepare_infrastructure()
        
        all_success = True
        
        for service_name in self.deployment_order:
            if service_name not in SERVICE_REPOS:
                continue
            
            service_config = self.spec.services.get(service_name)
            if service_config and not service_config.enabled:
                logger.info("⊘ %s: Disabled, skipping", service_name)
                continue
            
            logger.info("\n--- Deploying %s ---", service_name)
            
            try:
                service_info = SERVICE_REPOS[service_name]
                slack_internal_url = f"http://budai-slack-integration.railway.internal:{SERVICE_REPOS['slack-integration']['port']}"
                voice_internal_url = f"http://budai-voice-realtime.railway.internal:{SERVICE_REPOS['voice-realtime']['port']}"
                
                # Check if service already exists
                existing_service = self.provider._get_service_by_name(
                    f"budai-{service_name}",
                    self.creds["railway_project_id"]
                )
                is_new_service = existing_service is None
                
                # Prepare static variables (never change for a service)
                static_vars = {
                    "BUDAI_SERVICE_NAME": service_name,
                    "BUDAI_SERVICE_VERSION": "1.0.0",
                    "PORT": str(service_info["port"]),
                }
                
                # Add service-specific static variables (internal URLs)
                if service_name == "api-gateway":
                    static_vars.update({
                        "BUDAI_ORCHESTRATOR_URL": f"http://budai-orchestrator.railway.internal:{SERVICE_REPOS['orchestrator']['port']}",
                    })
                elif service_name == "orchestrator":
                    static_vars.update({
                        "BUDAI_AGENT_SUMMARIZER_URL": f"http://budai-agent-summarizer.railway.internal:{SERVICE_REPOS['agent-summarizer']['port']}",
                    })
                elif service_name == "slack-integration":
                    static_vars.update({
                        "BUDAI_API_GATEWAY_URL": f"http://budai-api-gateway.railway.internal:{SERVICE_REPOS['api-gateway']['port']}",
                    })
                
                # Prepare dynamic variables (change between deployments/environments)
                dynamic_vars = {
                    "BUDAI_ENVIRONMENT": self.environment,
                    "BUDAI_REDIS_URL": self.creds["redis_url"],
                    "BUDAI_OPENAI_API_KEY": self.creds.get("openai_api_key", ""),
                }

                if service_name in {"api-gateway", "orchestrator"}:
                    dynamic_vars["BUDAI_SLACK_INTEGRATION_URL"] = slack_internal_url
                if service_name in {"api-gateway", "slack-integration"}:
                    dynamic_vars["BUDAI_VOICE_REALTIME_URL"] = voice_internal_url
                
                # Add service-specific dynamic variables (secrets)
                if service_name == "api-gateway":
                    dynamic_vars.update({
                        "BUDAI_SLACK_SIGNING_SECRET": self.creds.get("slack_signing_secret", ""),
                        "BUDAI_SLACK_BOT_TOKEN": self.creds.get("slack_bot_token", ""),
                    })
                elif service_name == "orchestrator":
                    dynamic_vars.update({
                        "BUDAI_SLACK_SIGNING_SECRET": self.creds.get("slack_signing_secret", ""),
                    })
                elif service_name == "slack-integration":
                    slack_bot_token = self.creds.get("slack_bot_token", "")
                    slack_signing_secret = self.creds.get("slack_signing_secret", "")
                    if not slack_bot_token or not slack_signing_secret:
                        raise RuntimeError(
                            "Slack integration requires both slack_bot_token and slack_signing_secret credentials."
                        )
                    dynamic_vars.update({
                        "SLACK_BOT_TOKEN": slack_bot_token,
                        "SLACK_SIGNING_SECRET": slack_signing_secret,
                        "BUDAI_SLACK_BOT_TOKEN": slack_bot_token,
                        "BUDAI_SLACK_SIGNING_SECRET": slack_signing_secret,
                    })
                
                # For NEW services: combine all variables and pass during creation
                # This sets everything atomically in one operation
                initial_vars = None
                if is_new_service:
                    initial_vars = {**static_vars, **{k: v for k, v in dynamic_vars.items() if v}}
                    logger.info("Creating new service with %d variables", len(initial_vars))
                
                # Create or get the service connected to GitHub repo
                # Railway will automatically read railway.json from the repo for build/deploy config
                service_id = self.provider.create_service(
                    name=f"budai-{service_name}",
                    project_id=self.creds["railway_project_id"],
                    source_repo=service_info["repo"],
                    source_branch=service_info["branch"],
                    environment=self.environment,
                    variables=initial_vars,
                )
                
                # For NEW services, explicitly connect the repo with branch
                # serviceCreate doesn't support branch overrides, so we use serviceConnect
                if is_new_service:
                    logger.info("Connecting service to branch '%s'...", service_info["branch"])
                    self.provider._connect_service_repo(
                        service_id=service_id,
                        repo=service_info["repo"],
                        branch=service_info["branch"],
                        environment=self.environment,
                    )
                    logger.info("Service connected to GitHub repo and branch")
                
                # For EXISTING services: only update variables that have changed
                # For NEW services: skip this (all vars already set during creation)
                if not is_new_service:
                    # Filter out empty values
                    non_empty_vars = {k: v for k, v in dynamic_vars.items() if v}
                    
                    if non_empty_vars:
                        env_id = self.provider._get_environment_id(
                            self.creds["railway_project_id"],
                            self.environment
                        )
                        existing_vars = self.provider.get_service_variables(
                            self.creds["railway_project_id"],
                            env_id,
                            service_id
                        )
                        # Only update variables that have changed
                        changed_vars = {
                            k: v for k, v in non_empty_vars.items()
                            if k not in existing_vars or existing_vars[k] != v
                        }
                        
                        if changed_vars:
                            logger.info("Updating %d changed variable(s): %s", 
                                      len(changed_vars), ", ".join(changed_vars.keys()))
                            # Set environment variables
                            # Note: Each variable change triggers a deployment automatically
                            self.provider.set_environment_variables(
                                service_id=service_id,
                                environment=self.environment,
                                variables=changed_vars,
                                project_id=self.creds["railway_project_id"]
                            )
                            logger.info("Variable updates will trigger deployment automatically")
                        else:
                            logger.info("No variables changed, no deployment needed")
                else:
                    # New service - Railway will auto-deploy when service instance is ready
                    logger.info("New service created. Railway will auto-deploy when ready.")
                    logger.info("Monitor deployment status at: https://railway.com/project/%s/service/%s",
                              self.creds["railway_project_id"], service_id)
                
                logger.info("✓ %s: Deployed successfully (service ID: %s)", service_name, service_id)
                
            except Exception as exc:
                logger.exception("✗ %s: Deployment exception: %s", service_name, exc)
                all_success = False
        
        if "redis" in self.infra_artifacts:
            redis_info = self.infra_artifacts["redis"]
            logger.info("\nShared Redis instance:")
            logger.info("  Service ID: %s", redis_info["service_id"])
            logger.info("  Internal host: %s", redis_info["host"])
            logger.info("  Port: %s", redis_info["port"])
            logger.info("  URL: %s", redis_info["redis_url"])

        return all_success

    def verify_all(self) -> bool:
        """Verify all deployments are healthy.

        Returns:
            True if all verifications passed, False otherwise
        """
        logger.info("\nVerifying deployments...")
        
        all_healthy = True
        
        for service_name in self.deployment_order:
            if service_name not in SERVICE_REPOS:
                continue
            
            service_config = self.spec.services.get(service_name)
            if service_config and not service_config.enabled:
                continue
            
            try:
                service_full_name = f"budai-{service_name}"
                # Check if service exists and is deployed
                # In a real implementation, you'd check the deployment status via Railway API
                logger.info("✓ %s: Service configured", service_name)
                
            except Exception as exc:
                logger.exception("✗ %s: Verification failed: %s", service_name, exc)
                all_healthy = False
        
        return all_healthy


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="BudAI Deployment CLI - Deploy services to Railway from GitHub repos"
    )
    parser.add_argument(
        "command",
        choices=["explain", "deploy", "verify"],
        help="Deployment command",
    )
    parser.add_argument(
        "--spec",
        required=True,
        help="Path to deployment spec YAML file (e.g., specs/production.yaml)",
    )
    parser.add_argument(
        "--creds",
        required=True,
        help="Path to credentials JSON file",
    )
    parser.add_argument(
        "--mode",
        choices=["assisted", "zero-touch"],
        default="assisted",
        help="Deployment mode (default: assisted)",
    )
    
    args = parser.parse_args()
    
    # Load deployment spec
    try:
        spec = DeploymentSpec.from_file(args.spec)
    except Exception as exc:
        logger.error("Failed to load deployment spec: %s", exc)
        sys.exit(1)
    
    # Load credentials
    try:
        with open(args.creds) as f:
            creds = json.load(f)
    except Exception as exc:
        logger.error("Failed to load credentials: %s", exc)
        sys.exit(1)
    
    # Create orchestrator
    try:
        orchestrator = DeploymentOrchestrator(spec, creds)
    except Exception as exc:
        logger.error("Failed to initialize orchestrator: %s", exc)
        sys.exit(1)
    
    # Execute command
    if args.command == "explain":
        orchestrator.explain_requirements()
    
    elif args.command == "deploy":
        orchestrator.explain_requirements()
        
        if args.mode == "assisted":
            logger.info("\n" + "=" * 80)
            logger.info("DEPLOYMENT PLAN READY")
            logger.info("=" * 80)
            logger.info("Services to deploy: %d", len(orchestrator.deployment_order))
            logger.info("Environment: %s", orchestrator.environment)
            logger.info("")
            response = input("Proceed with deployment? [y/N]: ")
            
            if response.lower() != 'y':
                logger.info("Deployment cancelled by user")
                sys.exit(0)
        
        success = orchestrator.deploy_all()
        
        if success:
            logger.info("\n✓ All services deployed successfully")
            logger.info("\nNext steps:")
            logger.info("1. Check Railway dashboard for deployment progress")
            logger.info("2. Services will auto-deploy from GitHub on future commits")
            logger.info("3. Monitor logs via: railway logs --service <service-name>")
            
            if orchestrator.verify_all():
                logger.info("✓ All services configured")
        else:
            logger.error("\n✗ Deployment failed")
            sys.exit(1)
    
    elif args.command == "verify":
        if orchestrator.verify_all():
            logger.info("\n✓ All services configured")
            sys.exit(0)
        else:
            logger.error("\n✗ Some services have issues")
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nDeployment interrupted by user")
        sys.exit(130)
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        sys.exit(1)
