# BudAI Combined Architecture Readout

## Executive Snapshot
- The platform now runs as four coordinated repositories (`budai-deploy`, `budai-api-gateway`, `budai-orchestrator`, `budai-agent-summarizer`) after the monorepo split, with the deployment CLI cloning repos, provisioning Redis, and sequencing rollouts (`BudAI/MIGRATION.md:13`, `BudAI/MIGRATION.md:17`, `BudAI/MIGRATION.md:218`).
- Core runtime services are live for ingress, orchestration, and summarization, while follow-up, communicator, voice realtime, and Slack integration endpoints remain unimplemented blockers for the intended workflows (`budai-deploy/ARCHITECTURE.md:156`, `budai-deploy/ARCHITECTURE.md:170`, `budai-deploy/ARCHITECTURE.md:185`, `budai-deploy/ARCHITECTURE.md:28`, `budai-deploy/ARCHITECTURE.md:199`).
- Every service still builds from the same shared code layout, copying common `shared/` and `installer/` modules into each image via service-specific Dockerfiles that point Railway at the correct build context (`BudAI/DOCKER_ARCHITECTURE.md:5`, `BudAI/MIGRATION.md:103`).
- Agent summarizer health checks were relaxed so deployments stay green even if Redis or OpenAI lag, providing actionable guidance on required environment variables (`budai-agent-summarizer/DEPLOYMENT.md:8`, `budai-agent-summarizer/DEPLOYMENT.md:19`, `budai-agent-summarizer/DEPLOYMENT.md:36`).

## Repository & Service Topology
- **budai-deploy** - Python CLI that provisions Redis, clones service repos via `gh`, and deploys in dependency order; it remains the control-plane for multi-service releases (`BudAI/MIGRATION.md:17`, `BudAI/MIGRATION.md:227`).
- **budai-api-gateway** - Slack and voice ingress (port 8000) with HMAC verification and downstream calls into orchestrator and future integrations (`budai-deploy/ARCHITECTURE.md:156`).
- **budai-orchestrator** - Event-driven workflow engine (port 8001) that coordinates summarization and follow-up flows through Redis streams and HTTP agent calls (`budai-deploy/ARCHITECTURE.md:170`, `budai-deploy/ARCHITECTURE.md:282`).
- **budai-agent-summarizer** - OpenAI-backed summarization microservice (port 8002) with resilient startup and health-reporting improvements applied (`budai-deploy/ARCHITECTURE.md:185`, `budai-agent-summarizer/DEPLOYMENT.md:19`).
- **Missing services** - Follow-up, communicator, voice realtime, and Slack integration placeholders remain defined in specs but are not yet implemented, leaving meeting lifecycle automation incomplete (`budai-deploy/ARCHITECTURE.md:28`, `budai-deploy/ARCHITECTURE.md:199`, `budai-deploy/ARCHITECTURE.md:307`).
- Shared libraries (`shared/`, `installer/`) are duplicated across repos, enabling independent deployment but raising coordination costs for cross-cutting fixes (`BudAI/MIGRATION.md:103`).

## Build & Deployment Mechanics
- Each service relies on a Dockerfile that installs the global `requirements.txt`, copies shared modules, and then copies its service directory before launching FastAPI; Railway selects the appropriate Dockerfile through per-service `railway.json` files (`BudAI/DOCKER_ARCHITECTURE.md:43`, `BudAI/DOCKER_ARCHITECTURE.md:86`).
- Dependency management is still monolithic: all services install the same package set, so Slack-specific or OpenAI-specific upgrades ripple across every container (`BudAI/ARCHITECTURE_ANALYSIS.md:181`).
- The architecture review recommends quick wins—splitting requirements into layered files and adding `.dockerignore` for each service—to cut build time and image size (`BudAI/ARCHITECTURE_ANALYSIS.md:181`, `BudAI/ARCHITECTURE_ANALYSIS.md:226`, `BudAI/ARCHITECTURE_ANALYSIS.md:552`).
- `budai-deploy` should remain the source of truth for end-to-end releases; it already provisions Redis when missing and drives deployments sequentially to respect dependencies (`BudAI/MIGRATION.md:17`, `budai-deploy/ARCHITECTURE.md:388`).

## Operational Observations
- Summarizer health checks now surface dependency status without failing liveness, preventing Railway from cycling deployments during transient Redis or OpenAI outages (`budai-agent-summarizer/DEPLOYMENT.md:19`).
- Successful deployments hinge on providing `BUDAI_OPENAI_API_KEY` (and optional Redis overrides) through Railway environment variables, called out explicitly in the remediation guide (`budai-agent-summarizer/DEPLOYMENT.md:36`).
- System-level observability and automated testing are still missing, leaving limited insight into production behavior once additional services come online (`budai-deploy/ARCHITECTURE.md:535`).

## Risks & Gaps
- Absent follow-up, communicator, voice, and Slack integration services mean the orchestrated meeting lifecycle cannot progress past summarization, and gateway endpoints will error once invoked (`budai-deploy/ARCHITECTURE.md:199`, `budai-deploy/ARCHITECTURE.md:282`).
- Duplicated shared libraries introduce drift risk; a bug fix must be ported manually to every service repo until a shared package or git submodule strategy is adopted (`BudAI/MIGRATION.md:103`).
- Monolithic dependency files inflate container footprints and security surface area; unused libraries are still installed across services (`BudAI/ARCHITECTURE_ANALYSIS.md:181`).
- There is no guardrail preventing accidental cross-service imports, which could erode service boundaries as code evolves (`BudAI/ARCHITECTURE_ANALYSIS.md:303`).

## Recommended Next Moves
1. **Finish the missing services** - Implement voice realtime, Slack integration, follow-up, and communicator components before expanding workflows; these are flagged as the top-phase actions (`budai-deploy/ARCHITECTURE.md:490`).
2. **Trim build fat** - Split shared vs service-specific requirements and add `.dockerignore` files to shrink build context and speed Railway rebuilds (`BudAI/ARCHITECTURE_ANALYSIS.md:551`, `BudAI/ARCHITECTURE_ANALYSIS.md:552`).
3. **Harden code boundaries** - Add import linting and shared contract tests so duplicated libraries stay aligned and services only depend on sanctioned interfaces (`BudAI/ARCHITECTURE_ANALYSIS.md:560`, `BudAI/ARCHITECTURE_ANALYSIS.md:562`).
4. **Optimize Docker caching** - Reorder COPY layers and consider a shared base image once teams grow, as outlined in the architecture review (`BudAI/ARCHITECTURE_ANALYSIS.md:563`, `BudAI/ARCHITECTURE_ANALYSIS.md:458`).
5. **Plan for shared-library packaging** - When the team size or release cadence demands it, evaluate extracting the duplicated shared modules into a versioned package while keeping deployment coordination simple (`BudAI/MIGRATION.md:103`, `BudAI/ARCHITECTURE_ANALYSIS.md:570`).

## Reference Checklist
- `budai-deploy/ARCHITECTURE.md`
- `BudAI/MIGRATION.md`
- `BudAI/ARCHITECTURE_ANALYSIS.md`
- `BudAI/DOCKER_ARCHITECTURE.md`
- `budai-agent-summarizer/DEPLOYMENT.md`
