#!/bin/bash
# Setup automatic cleanup for Hermes
# Phase 1, Day 4

set -e

echo "=== Setup Automatic Cleanup ==="
echo ""

# Create logrotate config
echo "📝 Creating logrotate configuration..."
sudo tee /etc/logrotate.d/hermes > /dev/null <<'EOF'
/home/Bilirubin/.hermes/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 Bilirubin Bilirubin
    sharedscripts
    postrotate
        systemctl reload hermes-gateway 2>/dev/null || true
    endscript
}

/var/log/hermes/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 root root
}
EOF

echo "✅ Logrotate configuration created"

# Create daily cleanup script
echo ""
echo "📝 Creating daily cleanup script..."
sudo tee /etc/cron.daily/hermes-cleanup > /dev/null <<'EOF'
#!/bin/bash
# Daily cleanup for Hermes

HERMES_HOME="/home/Bilirubin/.hermes"
LOG_FILE="$HERMES_HOME/logs/cleanup.log"

echo "=== Hermes Daily Cleanup - $(date) ===" >> "$LOG_FILE"

# Remove old temporary files
find "$HERMES_HOME/temp" -type f -mtime +7 -delete 2>> "$LOG_FILE"

# Remove old logs
find "$HERMES_HOME/logs" -name "*.log" -mtime +30 -delete 2>> "$LOG_FILE"

# Archive old backups
mkdir -p "$HERMES_HOME/backups/archive"
find "$HERMES_HOME/backups" -maxdepth 1 -name "*.tar.gz" -mtime +7 \
  -exec mv {} "$HERMES_HOME/backups/archive/" \; 2>> "$LOG_FILE"

# Remove Python cache
find /home/Bilirubin/workspace/hermes -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find /home/Bilirubin/workspace/hermes -name "*.pyc" -delete 2>/dev/null

# Report disk usage
df -h / | tail -1 >> "$LOG_FILE"
du -sh "$HERMES_HOME" >> "$LOG_FILE"

echo "=== Cleanup Complete ===" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
EOF

sudo chmod +x /etc/cron.daily/hermes-cleanup
echo "✅ Daily cleanup script created"

# Create weekly backup cleanup script
echo ""
echo "📝 Creating weekly backup cleanup script..."
sudo tee /etc/cron.weekly/hermes-backup-cleanup > /dev/null <<'EOF'
#!/bin/bash
# Weekly backup cleanup for Hermes

HERMES_HOME="/home/Bilirubin/.hermes"
ARCHIVE_DIR="$HERMES_HOME/backups/archive"
LOG_FILE="$HERMES_HOME/logs/cleanup.log"

echo "=== Weekly Backup Cleanup - $(date) ===" >> "$LOG_FILE"

# Remove archived backups older than 30 days
find "$ARCHIVE_DIR" -name "*.tar.gz" -mtime +30 -delete 2>> "$LOG_FILE"

# Report archive size
du -sh "$ARCHIVE_DIR" >> "$LOG_FILE"

echo "=== Backup Cleanup Complete ===" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
EOF

sudo chmod +x /etc/cron.weekly/hermes-backup-cleanup
echo "✅ Weekly backup cleanup script created"

# Test logrotate
echo ""
echo "🧪 Testing logrotate configuration..."
sudo logrotate -d /etc/logrotate.d/hermes

echo ""
echo "✅ Automatic cleanup setup complete!"
echo ""
echo "Configured:"
echo "  - Logrotate: /etc/logrotate.d/hermes"
echo "  - Daily cleanup: /etc/cron.daily/hermes-cleanup"
echo "  - Weekly cleanup: /etc/cron.weekly/hermes-backup-cleanup"
echo ""
echo "Cleanup will run automatically:"
echo "  - Daily: Remove old logs and temp files"
echo "  - Weekly: Remove old archived backups"
echo "  - Logrotate: Rotate logs daily, keep 30 days"
