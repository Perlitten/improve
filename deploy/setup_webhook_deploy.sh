#!/usr/bin/env bash
# Setup GitHub webhook auto-deploy on server
# Run this ONCE on the server to enable automatic deploys

set -euo pipefail

WORKSPACE_PATH="/home/Bilirubin/workspace"
WEBHOOK_PORT=9876
WEBHOOK_SECRET="${WEBHOOK_SECRET:-changeme}"

echo "🔧 Setting up webhook auto-deploy..."
echo ""

# Install webhook tool if not present
if ! command -v webhook &> /dev/null; then
    echo "📦 Installing webhook..."
    sudo apt-get update
    sudo apt-get install -y webhook
fi

# Create webhook configuration
cat > /tmp/hooks.json <<EOF
[
  {
    "id": "workspace-deploy",
    "execute-command": "$WORKSPACE_PATH/deploy_hook.sh",
    "command-working-directory": "$WORKSPACE_PATH",
    "response-message": "Deploying...",
    "trigger-rule": {
      "and": [
        {
          "match": {
            "type": "payload-hmac-sha256",
            "secret": "$WEBHOOK_SECRET",
            "parameter": {
              "source": "header",
              "name": "X-Hub-Signature-256"
            }
          }
        },
        {
          "match": {
            "type": "value",
            "value": "refs/heads/master",
            "parameter": {
              "source": "payload",
              "name": "ref"
            }
          }
        }
      ]
    }
  }
]
EOF

sudo mv /tmp/hooks.json /etc/webhook/hooks.json
sudo chown root:root /etc/webhook/hooks.json

# Create deploy script
cat > "$WORKSPACE_PATH/deploy_hook.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/home/Bilirubin/workspace/.deploy.log"

echo "$(date -Iseconds) - Deploy triggered" >> "$LOG_FILE"

cd /home/Bilirubin/workspace

# Pull latest changes
git fetch origin
git reset --hard origin/master

# Restart services if needed
if systemctl is-active --quiet brain-mcp; then
    sudo systemctl restart brain-mcp
    echo "$(date -Iseconds) - Restarted brain-mcp" >> "$LOG_FILE"
fi

if systemctl is-active --quiet infra-health-loop.timer; then
    sudo systemctl daemon-reload
    echo "$(date -Iseconds) - Reloaded systemd" >> "$LOG_FILE"
fi

echo "$(date -Iseconds) - Deploy complete" >> "$LOG_FILE"
EOF

chmod +x "$WORKSPACE_PATH/deploy_hook.sh"

# Create systemd service
sudo tee /etc/systemd/system/webhook-deploy.service > /dev/null <<EOF
[Unit]
Description=GitHub Webhook Deploy Service
After=network.target

[Service]
Type=simple
User=Bilirubin
ExecStart=/usr/bin/webhook -hooks /etc/webhook/hooks.json -port $WEBHOOK_PORT -verbose
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable webhook-deploy
sudo systemctl start webhook-deploy

echo ""
echo "✅ Webhook deploy setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Add webhook in GitHub repo settings:"
echo "   URL: http://your-server:$WEBHOOK_PORT/hooks/workspace-deploy"
echo "   Secret: $WEBHOOK_SECRET"
echo "   Content type: application/json"
echo "   Events: Just the push event"
echo ""
echo "2. Test with: curl -X POST http://localhost:$WEBHOOK_PORT/hooks/workspace-deploy"
echo ""
echo "3. View logs: journalctl -u webhook-deploy -f"
