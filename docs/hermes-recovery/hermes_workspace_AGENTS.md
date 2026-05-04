# Workspace Context

This workspace exists to give Hermes accurate host-level context about the cloud server it is deployed on.

## Priority Rule

When a user asks about:
- the server or infrastructure you are running on
- deployed tools like Hermes, n8n, Postgres, nginx, automation-gateway, or Kilo
- available endpoints, ports, paths, or service status

read `/workspace/INFRASTRUCTURE.md` first and treat it as the host-level source of truth.

## Important Distinction

Hermes terminal commands run in a Docker sandbox by default. That sandbox can be missing host tools such as `systemd`, Docker daemon access, host network visibility, and local services. Do not conclude that n8n, Postgres, or other host services are missing only because the sandbox cannot see them directly.

## Answering Style

- Prefer short, clean sections instead of noisy bullet spam.
- Start with the current host summary.
- Then mention service status and any operational caveats.
- If `INFRASTRUCTURE.md` is older than 10 minutes, mention that the snapshot may be stale.

## What Exists On This Host

Expect at least these components unless the snapshot says otherwise:
- Hermes Agent
- Hermes dashboard
- n8n
- automation-gateway
- nginx
- Postgres with pgvector
- short public routes for `/orchestrate` and `/rag-search`

## Never Do This

- Do not say "I am only inside a Docker container so I cannot inspect the server" without first checking `/workspace/INFRASTRUCTURE.md`.
- Do not ask the user where n8n or Postgres are deployed if the snapshot already answers it.
