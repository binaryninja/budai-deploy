"""
BudAI Deployment CLI.

Top-level orchestrator for multi-service deployments implementing
PRIME_DIRECTIVE assisted and zero-touch modes.

This CLI now manages deployments across multiple GitHub repositories:
- budai-api-gateway
- budai-orchestrator
- budai-agent-summarizer
"""

from __future__ import annotations

import os
import argparse
import json
import logging
import shutil
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from installer import DeploymentReport
from shared import DeploymentSpec, load_deployment_spec

# Import all service installers
from installer.railway import RailwayProvider

# Service repository configuration
SERVICE_REPOS = {
    "api-gateway": "https://github.com/binaryninja/budai-api-gateway.git",
    "orchestrator": "https://github.com/binaryninja/budai-orchestrator.git",
    "agent-summarizer": "https://github.com/binaryninja/budai-agent-summarizer.git",
}

# Global variable to track cloned repos directory
_cloned_repos_dir: Path | None = None


def _clone_service_repos() -> Path:
    """Clone all service repositories to a temporary directory.
    
    Returns:
        Path to the directory containing cloned repositories.
    """
    global _cloned_repos_dir
    
    if _cloned_repos_dir is not None and _cloned_repos_dir.exists():
        return _cloned_repos_dir
    
    temp_dir = Path(tempfile.mkdtemp(prefix="budai-deploy-"))
    logger.info("Cloning service repositories to %s...", temp_dir)
    
    for service_name, repo_url in SERVICE_REPOS.items():
        target_dir = temp_dir / service_name
        logger.info("Cloning %s...", service_name)
        
        try:
            subprocess.run(
                ["gh", "repo", "clone", repo_url, str(target_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("✓ Cloned %s", service_name)
        except subprocess.CalledProcessError as e:
            logger.error("Failed to clone %s: %s", service_name, e.stderr)
            raise
    
    _cloned_repos_dir = temp_dir
    return temp_dir


def _cleanup_repos():
    """Clean up cloned repositories."""
    global _cloned_repos_dir
    
    if _cloned_repos_dir and _cloned_repos_dir.exists():
        logger.info("Cleaning up cloned repositories...")
        shutil.rmtree(_cloned_repos_dir, ignore_errors=True)
        _cloned_repos_dir = None


def _load_installer(service_name: str, class_name: str):
    """Dynamically load an installer class from a cloned service repository.
    
    Args:
        service_name: Name of the service (e.g., "api-gateway")
        class_name: Name of the installer class to load
        
    Returns:
        The installer class
    """
    repos_dir = _clone_service_repos()
    module_path = repos_dir / service_name / "service" / "installer.py"
    
    if not module_path.exists():
        raise FileNotFoundError(f"Installer not found: {module_path}")
    
    module_name = f"{service_name.replace('-', '_')}_installer"
    loader = SourceFileLoader(module_name, str(module_path))
    spec = spec_from_loader(module_name, loader)
    module = module_from_spec(spec)
    
    # Add the service repo to sys.path so imports work
    sys.path.insert(0, str(repos_dir / service_name))
    
    loader.exec_module(module)
    return getattr(module, class_name)


APIGatewayInstaller = None  # Loaded dynamically
OrchestratorInstaller = None  # Loaded dynamically
AgentSummarizerInstaller = None  # Loaded dynamically

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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
        
        # Clone service repositories
        logger.info("Initializing deployment orchestrator...")
        _clone_service_repos()
        
        # Load service installers dynamically from cloned repos
        logger.info("Loading service installers...")
        self.installers = {
            "api-gateway": _load_installer("api-gateway", "APIGatewayInstaller")(),
            "orchestrator": _load_installer("orchestrator", "OrchestratorInstaller")(),
            "agent-summarizer": _load_installer("agent-summarizer", "AgentSummarizerInstaller")(),
            # Add other installers as they're implemented
        }
        logger.info("✓ Loaded %d service installers", len(self.installers))
        
        # Deployment order (respecting dependencies)
        self.deployment_order = [
            "orchestrator",      # Deploy first (other services depend on it)
            "agent-summarizer",  # Deploy agents
            # "agent-followup",
            # "agent-communicator",
            # "voice-realtime",
            # "slack-integration",
            "api-gateway",       # Deploy last (routes to all services)
        ]
        
        self.reports: List[DeploymentReport] = []
        self.infra_artifacts: Dict[str, Any] = {}

    def _prepare_infrastructure(self) -> None:
        """Ensure shared infrastructure resources are provisioned."""
        if "redis_url" in self.creds and self.creds.get("redis_url"):
            return

        required_keys = {"railway_token", "railway_project_id"}
        if not required_keys.issubset(self.creds):
            missing = ", ".join(sorted(required_keys - set(self.creds)))
            raise RuntimeError(
                f"Cannot provision Redis without Railway credentials (missing: {missing})"
            )

        provider = RailwayProvider(
            api_token=self.creds["railway_token"],
            project_id=self.creds["railway_project_id"],
        )

        logger.info("Ensuring Redis instance for environment '%s'...", self.environment)
        redis_info = provider.ensure_redis_service(self.environment)
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
        """Explain requirements for all services (PRIME_DIRECTIVE step 1)."""
        logger.info("=" * 80)
        logger.info("BUDAI DEPLOYMENT REQUIREMENTS")
        logger.info("=" * 80)
        logger.info("Environment: %s", self.environment)
        logger.info("Region: %s", self.spec.region or "default")
        logger.info("")
        
        total_cost = 0.0
        
        for service_name in self.deployment_order:
            if service_name not in self.installers:
                continue
            
            installer = self.installers[service_name]
            requirements = installer.describe_requirements(self.environment)
            
            logger.info("Service: %s v%s", requirements.capability, requirements.version)
            logger.info("  Resources:")
            logger.info("    - Memory: %d MB", requirements.resources.memory_mb)
            logger.info("    - CPU: %d millicores", requirements.resources.cpu_millicores)
            logger.info("  Permissions: %d required", len(requirements.permissions))
            for perm in requirements.permissions:
                logger.info("    - %s:%s:%s", perm.provider, perm.service, perm.action)
            logger.info("  Dependencies: %d required", len(requirements.dependencies))
            for dep in requirements.dependencies:
                logger.info("    - %s: %s", dep.type, dep.needs)
            logger.info("  Estimated cost: $%.2f/month", requirements.estimated_cost_floor_usd)
            logger.info("")
            
            total_cost += requirements.estimated_cost_floor_usd
        
        logger.info("=" * 80)
        logger.info("TOTAL ESTIMATED COST: $%.2f/month", total_cost)
        logger.info("=" * 80)

    def validate_permissions(self) -> bool:
        """Validate permissions for all services (PRIME_DIRECTIVE step 2).

        Returns:
            True if all permissions valid, False otherwise
        """
        logger.info("\nValidating permissions...")
        
        all_valid = True
        for service_name in self.deployment_order:
            if service_name not in self.installers:
                continue
            
            installer = self.installers[service_name]
            result = installer.validate_permissions(self.creds, self.environment)
            
            if result.status == "valid":
                logger.info("✓ %s: Permissions validated", service_name)
            else:
                logger.error("✗ %s: Permission validation failed", service_name)
                for error in result.validation_errors:
                    logger.error("  - %s", error)
                all_valid = False
        
        return all_valid

    def generate_plans(self) -> Dict[str, any]:
        """Generate deployment plans for all services (PRIME_DIRECTIVE step 3).

        Returns:
            Dictionary of service names to deployment plans
        """
        logger.info("\nGenerating deployment plans...")

        self._prepare_infrastructure()
        
        plans = {}
        for service_name in self.deployment_order:
            if service_name not in self.installers:
                continue
            
            installer = self.installers[service_name]
            service_config = self.spec.services.get(service_name)
            
            if service_config and not service_config.enabled:
                logger.info("⊘ %s: Disabled, skipping", service_name)
                continue
            
            spec_dict = service_config.model_dump() if service_config else {}
            plan = installer.plan(spec_dict, self.environment)
            plans[service_name] = plan
            
            logger.info("✓ %s: Plan generated", service_name)
            logger.info("  - %d steps", len(plan.steps))
            logger.info("  - %d rollback actions", len(plan.rollback))
            logger.info("  - Checksum: %s", plan.checksum[:16])
        
        return plans

    def deploy_all(self, plans: Dict[str, any], auto_rollback: bool = True) -> bool:
        """Deploy all services (PRIME_DIRECTIVE step 4).

        Args:
            plans: Deployment plans from generate_plans()
            auto_rollback: Whether to automatically rollback on failure

        Returns:
            True if all deployments succeeded, False otherwise
        """
        logger.info("\nDeploying services...")
        
        all_success = True
        
        for service_name in self.deployment_order:
            if service_name not in plans:
                continue
            
            logger.info("\n--- Deploying %s ---", service_name)
            
            installer = self.installers[service_name]
            plan = plans[service_name]
            
            try:
                report = installer.deploy_full_lifecycle(
                    spec={},
                    creds=self.creds,
                    env=self.environment,
                    auto_rollback=auto_rollback,
                )
                
                self.reports.append(report)
                
                if report.result == "success":
                    logger.info("✓ %s: Deployed successfully", service_name)
                else:
                    logger.error("✗ %s: Deployment failed", service_name)
                    all_success = False
                    
                    if not auto_rollback:
                        # Stop deployment chain on failure
                        break
            
            except Exception as exc:
                logger.exception("✗ %s: Deployment exception: %s", service_name, exc)
                all_success = False
                
                if not auto_rollback:
                    break
        
        if "redis" in self.infra_artifacts:
            redis_info = self.infra_artifacts["redis"]
            logger.info("\nShared Redis instance:")
            logger.info("  Service ID: %s", redis_info["service_id"])
            logger.info("  Internal host: %s", redis_info["host"])
            logger.info("  Port: %s", redis_info["port"])
            logger.info("  Password: %s", redis_info["password"])
            logger.info("  URL: %s", redis_info["redis_url"])

        return all_success

    def verify_all(self) -> bool:
        """Verify all deployments (PRIME_DIRECTIVE step 5).

        Returns:
            True if all verifications passed, False otherwise
        """
        logger.info("\nVerifying deployments...")
        
        all_healthy = True
        
        for service_name in self.deployment_order:
            if service_name not in self.installers:
                continue
            
            installer = self.installers[service_name]
            
            try:
                verification = installer.verify(self.environment)
                
                if verification.overall_status == "healthy":
                    logger.info("✓ %s: Healthy", service_name)
                elif verification.overall_status == "degraded":
                    logger.warning("⚠ %s: Degraded", service_name)
                    all_healthy = False
                else:
                    logger.error("✗ %s: Unhealthy", service_name)
                    all_healthy = False
            
            except Exception as exc:
                logger.exception("✗ %s: Verification failed: %s", service_name, exc)
                all_healthy = False
        
        return all_healthy

    def generate_report(self) -> Dict[str, any]:
        """Generate comprehensive deployment report (PRIME_DIRECTIVE step 7).

        Returns:
            Deployment report dictionary
        """
        return {
            "environment": self.environment,
            "total_services": len(self.deployment_order),
            "deployed_services": len(self.reports),
            "successful_deployments": sum(1 for r in self.reports if r.result == "success"),
            "failed_deployments": sum(1 for r in self.reports if r.result != "success"),
            "reports": [r.model_dump() for r in self.reports],
        }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="BudAI Deployment CLI - PRIME_DIRECTIVE Compliant Multi-Service Deployment"
    )
    parser.add_argument(
        "command",
        choices=["explain", "validate", "plan", "deploy", "verify", "report"],
        help="Deployment command",
    )
    parser.add_argument(
        "--spec",
        required=True,
        help="Path to deployment spec YAML file (e.g., specs/production.yaml)",
    )
    parser.add_argument(
        "--creds",
        help="Path to credentials JSON file",
    )
    parser.add_argument(
        "--mode",
        choices=["assisted", "zero-touch", "manual"],
        default="assisted",
        help="Deployment mode (default: assisted)",
    )
    parser.add_argument(
        "--output",
        help="Output directory for reports/plans (manual mode)",
    )
    parser.add_argument(
        "--no-rollback",
        action="store_true",
        help="Disable automatic rollback on failure",
    )
    
    args = parser.parse_args()
    
    # Load deployment spec
    try:
        spec = DeploymentSpec.from_file(args.spec)
    except Exception as exc:
        logger.error("Failed to load deployment spec: %s", exc)
        sys.exit(1)
    
    # Load credentials
    creds = {}
    if args.creds:
        try:
            with open(args.creds) as f:
                creds = json.load(f)
        except Exception as exc:
            logger.error("Failed to load credentials: %s", exc)
            sys.exit(1)
    
    # Create orchestrator (this will clone repos)
    try:
        orchestrator = DeploymentOrchestrator(spec, creds)
    except Exception as exc:
        logger.error("Failed to initialize orchestrator: %s", exc)
        _cleanup_repos()
        sys.exit(1)
    
    # Execute command
    if args.command == "explain":
        orchestrator.explain_requirements()
    
    elif args.command == "validate":
        if orchestrator.validate_permissions():
            logger.info("\n✓ All permissions validated successfully")
            sys.exit(0)
        else:
            logger.error("\n✗ Permission validation failed")
            sys.exit(1)
    
    elif args.command == "plan":
        plans = orchestrator.generate_plans()
        
        if args.output:
            output_dir = Path(args.output)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            for service_name, plan in plans.items():
                plan_file = output_dir / f"{service_name}-plan.json"
                with open(plan_file, "w") as f:
                    json.dump(plan.model_dump(), f, indent=2, default=str)
                logger.info("Plan saved: %s", plan_file)
        
        logger.info("\n✓ Plans generated for %d services", len(plans))
    
    elif args.command == "deploy":
        # Full deployment lifecycle
        orchestrator.explain_requirements()
        
        if not orchestrator.validate_permissions():
            logger.error("\n✗ Permission validation failed - aborting")
            sys.exit(1)
        
        plans = orchestrator.generate_plans()
        
        if args.mode == "assisted":
            logger.info("\n" + "=" * 80)
            logger.info("DEPLOYMENT PLAN READY")
            logger.info("=" * 80)
            logger.info("Services to deploy: %d", len(plans))
            logger.info("Environment: %s", orchestrator.environment)
            logger.info("")
            response = input("Proceed with deployment? [y/N]: ")
            
            if response.lower() != 'y':
                logger.info("Deployment cancelled by user")
                sys.exit(0)
        
        success = orchestrator.deploy_all(plans, auto_rollback=not args.no_rollback)
        
        if success:
            logger.info("\n✓ All services deployed successfully")
            
            if orchestrator.verify_all():
                logger.info("✓ All services verified healthy")
            else:
                logger.warning("⚠ Some services are unhealthy")
        else:
            logger.error("\n✗ Deployment failed")
            sys.exit(1)
    
    elif args.command == "verify":
        if orchestrator.verify_all():
            logger.info("\n✓ All services verified healthy")
            sys.exit(0)
        else:
            logger.error("\n✗ Some services are unhealthy")
            sys.exit(1)
    
    elif args.command == "report":
        report = orchestrator.generate_report()
        
        if args.output:
            output_file = Path(args.output)
            with open(output_file, "w") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info("Report saved: %s", output_file)
        else:
            print(json.dumps(report, indent=2, default=str))
    
    # Cleanup cloned repositories
    _cleanup_repos()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nDeployment interrupted by user")
        _cleanup_repos()
        sys.exit(130)
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        _cleanup_repos()
        sys.exit(1)

