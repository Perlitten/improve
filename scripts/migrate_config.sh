#!/bin/bash
# Migrate existing configs to unified config.yaml
# Phase 1, Day 3: Config Consolidation

set -e

HERMES_HOME="$HOME/.hermes"
CONFIG_FILE="$HERMES_HOME/config.yaml"
BACKUP_DIR="$HERMES_HOME/config_backup_$(date +%Y%m%d_%H%M%S)"

echo "=== Hermes Config Migration ==="
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"
echo "✅ Created backup directory: $BACKUP_DIR"

# Backup existing configs
echo ""
echo "📦 Backing up existing configs..."

if [ -f "$HERMES_HOME/automation.env" ]; then
    cp "$HERMES_HOME/automation.env" "$BACKUP_DIR/"
    echo "  ✅ Backed up automation.env"
fi

if [ -f "$HERMES_HOME/model_capabilities.json" ]; then
    cp "$HERMES_HOME/model_capabilities.json" "$BACKUP_DIR/"
    echo "  ✅ Backed up model_capabilities.json"
fi

# Find and backup other configs
find "$HERMES_HOME" -maxdepth 2 \( -name "*.env" -o -name "*config*.json" -o -name "*config*.yaml" \) 2>/dev/null | while read file; do
    if [ "$file" != "$CONFIG_FILE" ] && [ -f "$file" ]; then
        cp "$file" "$BACKUP_DIR/"
        echo "  ✅ Backed up $(basename $file)"
    fi
done

# Create new unified config
echo ""
echo "📝 Creating unified config..."

cat > "$CONFIG_FILE" <<EOF
# Hermes Unified Configuration
# Generated: $(date)

hermes:
  home: $HERMES_HOME
  log_level: INFO
  workspace: /home/Bilirubin/workspace/hermes

database:
  host: 127.0.0.1
  port: 5432
  name: rag
  user: \${POSTGRES_USER}
  password: \${POSTGRES_PASSWORD}

providers:
  openrouter:
    api_key: \${OPENROUTER_API_KEY}
    base_url: https://openrouter.ai/api/v1
    timeout: 60
    max_retries: 3
  
  nvidia:
    api_key: \${NVIDIA_API_KEY}
    base_url: https://integrate.api.nvidia.com/v1
    timeout: 60
    max_retries: 3

models:
  primary:
    model: anthropic/claude-sonnet-4
    provider: openrouter
    max_cost_per_task: 0.50
    max_tokens: 200000
  
  fallback:
    - model: nvidia/nemotron-3-super-120b-a12b:free
      provider: openrouter
      max_cost_per_task: 0.00
      max_tokens: 32000
    
    - model: meta/llama-3.3-70b-instruct
      provider: nvidia
      max_cost_per_task: 0.00
      max_tokens: 128000

task_queue:
  max_concurrent: 2
  checkpoint_interval: 60
  default_priority: 5
  max_retries: 3

cost_tracking:
  enabled: true
  daily_budget: 10.00
  alert_threshold: 0.80

memory:
  vector_db: postgres
  embedding_model: text-embedding-3-small
  chunk_size: 1000
  chunk_overlap: 200

n8n:
  enabled: true
  base_url: http://localhost:5678
  webhook_base: http://localhost:5678/webhook

monitoring:
  prometheus_port: 9090
  metrics_enabled: true
  health_check_interval: 60

logging:
  level: INFO
  format: json
  rotation: daily
  retention_days: 30
EOF

echo "✅ Created $CONFIG_FILE"

# Verify config
echo ""
echo "🔍 Verifying config..."

if [ -f "$CONFIG_FILE" ]; then
    echo "✅ Config file exists"
    
    # Check if environment variables are set
    if [ -f "$HERMES_HOME/automation.env" ]; then
        source "$HERMES_HOME/automation.env"
    fi
    
    if [ -z "$POSTGRES_USER" ]; then
        echo "⚠️  Warning: POSTGRES_USER not set"
    else
        echo "✅ POSTGRES_USER set"
    fi
    
    if [ -z "$OPENROUTER_API_KEY" ]; then
        echo "⚠️  Warning: OPENROUTER_API_KEY not set"
    else
        echo "✅ OPENROUTER_API_KEY set"
    fi
    
    if [ -z "$NVIDIA_API_KEY" ]; then
        echo "⚠️  Warning: NVIDIA_API_KEY not set"
    else
        echo "✅ NVIDIA_API_KEY set"
    fi
else
    echo "❌ Config file not created"
    exit 1
fi

echo ""
echo "✅ Migration complete!"
echo ""
echo "Backup location: $BACKUP_DIR"
echo "New config: $CONFIG_FILE"
echo ""
echo "Next steps:"
echo "1. Review $CONFIG_FILE"
echo "2. Ensure environment variables are set in $HERMES_HOME/automation.env"
echo "3. Test config loading: cd /home/Bilirubin/workspace/hermes && python3 -c 'from src.config_loader import ConfigLoader; c = ConfigLoader(); c.load(); c.validate(); print(\"✅ Config valid\")'"
echo "4. Restart services: sudo systemctl restart hermes-gateway"
