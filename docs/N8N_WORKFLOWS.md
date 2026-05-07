# n8n Workflows Status

## Created Workflows (Inactive)

### 1. Daily Memory Health Check
- **ID:** `1025795e-fb71-4296-869d-5d6bfe694ed8`
- **Schedule:** Daily at 08:00 UTC
- **Endpoint:** `GET http://127.0.0.1:8787/memory/health-detail`
- **Status:** Inactive (requires credential setup)

### 2. Gateway Audit Monitor
- **ID:** `a7bfe3eb-83ee-4f0c-9f99-03770f0b9825`
- **Schedule:** Every 30 minutes
- **Endpoint:** `GET http://127.0.0.1:8787/gateway/audit/recent?limit=20`
- **Status:** Inactive (requires credential setup)

---

## Activation Instructions (Manual)

To activate these workflows in n8n UI (http://127.0.0.1:5678):

1. **Create HTTP Header Auth Credential:**
   - Go to: Credentials → Add Credential → HTTP Header Auth
   - Name: `Hermes API Key`
   - Header Name: `X-Hermes-Api-Key`
   - Header Value: `<HERMES_N8N_API_KEY from /srv/automation/.env>`

2. **Configure Workflows:**
   - Open each workflow
   - Click on "HTTP Request" node
   - Under "Credential for Header Auth" → select "Hermes API Key"
   - Save workflow

3. **Activate:**
   - Toggle "Active" switch for each workflow

---

## Current Production Monitoring

**Active monitoring is handled by Hermes cron jobs:**

- `Daily Memory Health Check` (job_id: 11eb0b005c5c)
  - Schedule: 0 8 * * *
  - Script: `~/.hermes/scripts/health_check.py`
  - Status: Active

- `Gateway Audit Monitor` (job_id: 03a44e28dbed)
  - Schedule: */30 * * * *
  - Script: `~/.hermes/scripts/gateway_audit.py`
  - Status: Active

**n8n workflows are optional duplicates** — activate only if you prefer n8n-based scheduling over Hermes cron.

---

## Why n8n Workflows Are Inactive

n8n encrypts credentials before storing them in the database. Creating credentials via SQL INSERT is risky:
- Wrong encryption format breaks workflows
- Plaintext secrets in DB violate security
- Future n8n upgrades may fail

**Recommendation:** Use Hermes cron jobs for production monitoring. Activate n8n workflows only if needed via UI.
