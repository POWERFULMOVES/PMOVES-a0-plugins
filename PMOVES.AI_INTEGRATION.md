# PMOVES.AI Integration — Agent Zero Plugins

## Role in PMOVES.AI

This repository is the **community plugin index** for Agent Zero, surfaced within PMOVES.AI's agent orchestration layer. It provides:

- **Plugin discovery** — Curated index of Agent Zero plugins available to all PMOVES.AI agents
- **Capability extension** — Plugins extend Agent Zero's tool repertoire beyond core MCP tools
- **Community contributions** — Third-party plugins vetted through CI validation and human review

## Service Integration

Agent Zero (port 8080) loads plugins from this index at startup. Plugins are referenced by their `index.yaml` entries, which point to external repositories.

| Service | Port | Purpose |
|---------|------|---------|
| Agent Zero API | 8080 | Plugin host / orchestrator |
| Agent Zero UI | 8081 | Plugin management interface |

## Plugin Structure

Each plugin is a folder containing:
- `index.yaml` — Plugin metadata pointing to its source repository
- Optional thumbnail (`.png`, `.jpg`, `.webp`, max 20KB)

## Usage in PMOVES.AI

Plugins are loaded by Agent Zero during orchestration. The PMOVES.AI agent team configuration (`pmoves/configs/agent-teams.yaml`) references plugin capabilities when assigning tasks to agents.

## Health Check

Plugin availability is verified through Agent Zero's health endpoint:

```bash
curl http://localhost:8080/healthz
```

## Security Notes

- Plugins execute within Agent Zero's sandbox — no direct host access
- Plugin submissions require CI validation + human review before merge
- MCP tool allowlisting should be configured per-agent (see Phase C audit notes)
