# BudAI Deploy

Deployment orchestrator for BudAI microservices implementing the PRIME_DIRECTIVE self-deployment framework.

## Overview

BudAI Deploy is a multi-service deployment orchestrator that manages deployments across separate GitHub repositories:

- [budai-api-gateway](https://github.com/binaryninja/budai-api-gateway)
- [budai-orchestrator](https://github.com/binaryninja/budai-orchestrator)
- [budai-agent-summarizer](https://github.com/binaryninja/budai-agent-summarizer)

This tool clones service repositories at runtime, loads their installers, and orchestrates deployments in the correct dependency order.

## Quick Start

### Prerequisites

- Python 3.11+
- GitHub CLI (`gh`) installed and authenticated
- Railway account and API token (for Railway deployments)
- OpenAI API key
- Slack credentials (for services that need them)

### Installation

```bash
# Clone this repository
gh repo clone binaryninja/budai-deploy
cd budai-deploy

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

```bash
# Explain deployment requirements
python cli/deploy.py explain --spec specs/production.yaml

# Validate permissions
python cli/deploy.py validate --spec specs/production.yaml --creds specs/credentials.json

# Generate deployment plans
python cli/deploy.py plan --spec specs/production.yaml --creds specs/credentials.json

# Deploy all services (assisted mode - requires confirmation)
python cli/deploy.py deploy --spec specs/production.yaml --creds specs/credentials.json --mode assisted

# Verify deployments
python cli/deploy.py verify --spec specs/production.yaml --creds specs/credentials.json

# Generate deployment report
python cli/deploy.py report --spec specs/production.yaml --creds specs/credentials.json
```

## Configuration

### Deployment Specifications

Deployment specs are YAML files in the `specs/` directory:

```yaml
# specs/production.yaml
environment: production
region: us-west-1

services:
  orchestrator:
    enabled: true
    replicas: 1
    resources:
      memory_mb: 512
      cpu_millicores: 500
  
  agent-summarizer:
    enabled: true
    replicas: 2
    resources:
      memory_mb: 512
      cpu_millicores: 500
  
  api-gateway:
    enabled: true
    replicas: 2
    resources:
      memory_mb: 1024
      cpu_millicores: 1000
```

### Credentials

Create a `specs/credentials.json` file with your credentials:

```json
{
  "railway_token": "your-railway-api-token",
  "railway_project_id": "your-project-id",
  "openai_api_key": "sk-...",
  "slack_signing_secret": "...",
  "slack_bot_token": "xoxb-...",
  "redis_url": "redis://..." // optional, will be provisioned if not provided
}
```

**⚠️ Never commit credentials.json to version control!**

## How It Works

1. **Repository Cloning:** The CLI clones all service repositories to a temporary directory using `gh` CLI
2. **Installer Loading:** Each service's installer is dynamically loaded from its repository
3. **Dependency Management:** Services are deployed in dependency order (orchestrator → agents → gateway)
4. **Infrastructure Provisioning:** Shared resources (Redis) are provisioned automatically
5. **Deployment Execution:** Each service is deployed using its PRIME_DIRECTIVE installer
6. **Verification:** Health checks verify each service is running correctly
7. **Cleanup:** Temporary directories are cleaned up after deployment

## Deployment Modes

### Assisted Mode (Default)

Generate deployment plan and ask for confirmation:

```bash
python cli/deploy.py deploy --spec specs/production.yaml --creds specs/credentials.json --mode assisted
```

### Zero-Touch Mode

Deploy automatically within pre-approved guardrails:

```bash
python cli/deploy.py deploy --spec specs/production.yaml --creds specs/credentials.json --mode zero-touch
```

### Manual Export Mode

Export deployment artifacts for manual execution:

```bash
python cli/deploy.py deploy --spec specs/production.yaml --creds specs/credentials.json --mode manual --output terraform/
```

## Commands

### `explain`

Explains deployment requirements for all services:

```bash
python cli/deploy.py explain --spec specs/production.yaml
```

Shows:
- Resource requirements (CPU, memory)
- Required permissions
- Dependencies
- Estimated costs

### `validate`

Validates that you have the required permissions:

```bash
python cli/deploy.py validate --spec specs/production.yaml --creds specs/credentials.json
```

### `plan`

Generates deployment plans without executing:

```bash
python cli/deploy.py plan --spec specs/production.yaml --creds specs/credentials.json --output plans/
```

### `deploy`

Executes full deployment lifecycle:

```bash
python cli/deploy.py deploy --spec specs/production.yaml --creds specs/credentials.json
```

Options:
- `--mode`: assisted, zero-touch, or manual (default: assisted)
- `--no-rollback`: Disable automatic rollback on failure

### `verify`

Verifies all deployed services are healthy:

```bash
python cli/deploy.py verify --spec specs/production.yaml --creds specs/credentials.json
```

### `report`

Generates deployment report:

```bash
python cli/deploy.py report --spec specs/production.yaml --creds specs/credentials.json --output report.json
```

## Service Repositories

The deployment orchestrator manages these service repositories:

| Service | Repository | Port |
|---------|------------|------|
| API Gateway | [budai-api-gateway](https://github.com/binaryninja/budai-api-gateway) | 8000 |
| Orchestrator | [budai-orchestrator](https://github.com/binaryninja/budai-orchestrator) | 8001 |
| Agent Summarizer | [budai-agent-summarizer](https://github.com/binaryninja/budai-agent-summarizer) | 8002 |

### Adding New Services

To add a new service:

1. Create the service repository following the existing structure
2. Update `SERVICE_REPOS` in `cli/deploy.py`:

```python
SERVICE_REPOS = {
    "api-gateway": "https://github.com/binaryninja/budai-api-gateway.git",
    "orchestrator": "https://github.com/binaryninja/budai-orchestrator.git",
    "agent-summarizer": "https://github.com/binaryninja/budai-agent-summarizer.git",
    "agent-followup": "https://github.com/binaryninja/budai-agent-followup.git",  # New service
}
```

3. Update the deployment order in `DeploymentOrchestrator.__init__()` if needed

## PRIME_DIRECTIVE Framework

Each service implements the PRIME_DIRECTIVE installer contract:

```python
class ServiceInstaller(Installer):
    def describe_requirements(env) -> Requirements
    def validate_permissions(creds, env) -> ValidationResult
    def plan(spec, env) -> DeploymentPlan
    def apply(plan, creds) -> ApplyResult
    def verify(env) -> VerificationReport
    def rollback(plan, creds) -> RollbackResult
    def report() -> DeploymentReport
```

This enables:
- **Self-documentation:** Services explain their own requirements
- **Permission validation:** Services check they have required access
- **Safe deployment:** Automatic rollback on failure
- **Health verification:** Built-in health checks

## Troubleshooting

### GitHub Authentication Error

```bash
# Ensure gh CLI is authenticated
gh auth status

# Re-authenticate if needed
gh auth login
```

### Repository Clone Failures

```bash
# Check your GitHub access to service repositories
gh repo view binaryninja/budai-api-gateway
gh repo view binaryninja/budai-orchestrator
gh repo view binaryninja/budai-agent-summarizer
```

### Deployment Failures

```bash
# Check Railway logs
railway logs --service orchestrator --tail 100

# Verify permissions
python cli/deploy.py validate --spec specs/production.yaml --creds specs/credentials.json

# Run with verbose logging
export LOG_LEVEL=DEBUG
python cli/deploy.py deploy --spec specs/production.yaml --creds specs/credentials.json
```

### Service Health Issues

```bash
# Verify individual service health
curl https://orchestrator.up.railway.app/health
curl https://api-gateway.up.railway.app/health
curl https://agent-summarizer.up.railway.app/health

# Check Redis connectivity
redis-cli -u $BUDAI_REDIS_URL ping
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Run installer contract tests
pytest tests/installer_tests/
```

### Code Quality

```bash
# Format code
ruff format .

# Lint
ruff check .

# Type check
mypy .
```

## Architecture

```
budai-deploy/
├── cli/
│   └── deploy.py           # Main deployment orchestrator CLI
├── installer/
│   ├── base.py             # Base installer interface
│   ├── railway.py          # Railway provider implementation
│   └── schemas.py          # Pydantic schemas for deployment
├── shared/
│   ├── config.py           # Configuration management
│   ├── events.py           # Event definitions
│   ├── health.py           # Health check utilities
│   └── observability.py    # Logging and monitoring
├── specs/
│   ├── production.yaml     # Production deployment spec
│   ├── development.yaml    # Development deployment spec
│   └── credentials.example.json  # Example credentials file
├── requirements.txt
└── README.md
```

## License

MIT License - Part of the BudAI project

## Support

- **Issues:** https://github.com/binaryninja/budai-deploy/issues
- **Documentation:** https://github.com/binaryninja/budai-deploy
- **Service Repos:** See links above

---

**Built with the PRIME_DIRECTIVE principle: Every capability deploys itself.**

