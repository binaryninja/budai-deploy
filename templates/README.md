# Railway Config as Code Templates

These templates should be added to each service repository as `railway.json` at the root level.

## Purpose

Using Railway's Config as Code feature, we can define build and deploy settings directly in the service repositories. This:

1. **Simplifies deployment** - Railway automatically reads these settings when deploying
2. **Version control** - Build/deploy configs are versioned with the code
3. **Transparency** - Settings are visible in the repository, not hidden in Railway dashboard
4. **Consistency** - Same settings apply across all environments

## How to Use

### For Each Service Repository

1. Copy the appropriate `*-railway.json` template to the service's repository root
2. Rename it to `railway.json`
3. Customize the settings if needed (adjust ports, commands, etc.)
4. Commit and push to the repository

### Example: Orchestrator

```bash
cd ~/budai-orchestrator
cp ../budai-deploy/templates/orchestrator-railway.json ./railway.json
git add railway.json
git commit -m "Add Railway config as code"
git push
```

### Example: API Gateway

```bash
cd ~/budai-api-gateway
cp ../budai-deploy/templates/api-gateway-railway.json ./railway.json
git add railway.json
git commit -m "Add Railway config as code"
git push
```

### Example: Agent Summarizer

```bash
cd ~/budai-agent-summarizer
cp ../budai-deploy/templates/agent-summarizer-railway.json ./railway.json
git add railway.json
git commit -m "Add Railway config as code"
git push
```

## Configuration Sections

### Build Section

- **builder**: Which builder to use (NIXPACKS, DOCKERFILE, RAILPACK)
- **buildCommand**: Command to run during build phase

### Deploy Section

- **startCommand**: Command to start the service
- **healthcheckPath**: Endpoint Railway checks to verify deployment health
- **healthcheckTimeout**: Seconds to wait for health check to pass (default: 300)
- **restartPolicyType**: How to handle crashes (ON_FAILURE, ALWAYS, NEVER)
- **restartPolicyMaxRetries**: Maximum restart attempts before marking as failed

## What This Doesn't Include

The `railway.json` file **does not include environment variables** for security reasons. Environment variables are still set via:

1. The Railway dashboard UI
2. The Railway API (via our deployment scripts)
3. The Railway CLI

## Benefits of This Approach

### Before (API-only approach)
- Service configuration scattered between code and API calls
- Hard to see what settings are applied
- Changes require code modifications to deployment scripts

### After (Config as Code)
- Configuration lives with the service code
- Settings are visible in pull requests
- Railway automatically applies settings on every deployment
- Deployment scripts only need to handle:
  - Service creation
  - Environment variables
  - Deployment triggering

## Deployment Flow with Config as Code

1. **Deploy script creates service** (if not exists) and links to GitHub repo
2. **Railway detects railway.json** in the repository
3. **Railway applies settings** from the JSON file automatically
4. **Deploy script sets environment variables** (secrets, URLs, etc.)
5. **Railway builds and deploys** using the configured settings

## Schema and Autocomplete

The `"$schema"` line at the top enables autocomplete in editors like VSCode. When you edit `railway.json`, you'll get:
- Autocomplete for available settings
- Inline documentation
- Validation warnings

## Reference

Full documentation: https://docs.railway.com/reference/config-as-code

