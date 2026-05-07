#!/bin/bash
# Disk cleanup script for Hermes
# Phase 1, Day 4

set -e

HERMES_HOME="$HOME/.hermes"
WORKSPACE="/home/Bilirubin/workspace/hermes"
DRY_RUN=false

# Parse arguments
if [ "$1" = "--dry-run" ]; then
    DRY_RUN=true
fi

echo "=== Hermes Disk Cleanup ==="
echo ""

# Show current disk usage
echo "📊 Current disk usage:"
df -h / | grep -E "Filesystem|/$"
echo ""
du -sh "$HERMES_HOME" 2>/dev/null || echo "Hermes home: N/A"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "🔍 DRY RUN MODE - No changes will be made"
    echo ""
fi

# Phase 1: Old logs
echo "🧹 Phase 1: Cleaning old logs (> 30 days)..."
OLD_LOGS=$(find "$HERMES_HOME/logs" -name "*.log" -mtime +30 2>/dev/null | wc -l)
echo "  Found $OLD_LOGS old log files"

if [ "$DRY_RUN" = false ] && [ "$OLD_LOGS" -gt 0 ]; then
    find "$HERMES_HOME/logs" -name "*.log" -mtime +30 -delete
    echo "  ✅ Removed $OLD_LOGS old log files"
else
    echo "  Would remove $OLD_LOGS files"
fi

# Phase 2: Temporary files
echo ""
echo "🧹 Phase 2: Cleaning temporary files (> 7 days)..."
mkdir -p "$HERMES_HOME/temp"
TEMP_FILES=$(find "$HERMES_HOME/temp" -type f -mtime +7 2>/dev/null | wc -l)
echo "  Found $TEMP_FILES temporary files"

if [ "$DRY_RUN" = false ] && [ "$TEMP_FILES" -gt 0 ]; then
    find "$HERMES_HOME/temp" -type f -mtime +7 -delete
    echo "  ✅ Removed $TEMP_FILES temporary files"
else
    echo "  Would remove $TEMP_FILES files"
fi

# Phase 3: Python cache
echo ""
echo "🧹 Phase 3: Cleaning Python cache..."
CACHE_DIRS=$(find "$WORKSPACE" -name "__pycache__" -type d 2>/dev/null | wc -l)
echo "  Found $CACHE_DIRS cache directories"

if [ "$DRY_RUN" = false ] && [ "$CACHE_DIRS" -gt 0 ]; then
    find "$WORKSPACE" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find "$WORKSPACE" -name "*.pyc" -delete 2>/dev/null || true
    find "$WORKSPACE" -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true
    echo "  ✅ Removed Python cache"
else
    echo "  Would remove $CACHE_DIRS cache directories"
fi

# Phase 4: Archive old backups
echo ""
echo "🧹 Phase 4: Archiving old backups (> 7 days)..."
mkdir -p "$HERMES_HOME/backups/archive"
OLD_BACKUPS=$(find "$HERMES_HOME/backups" -maxdepth 1 -name "*.tar.gz" -mtime +7 2>/dev/null | wc -l)
echo "  Found $OLD_BACKUPS old backups"

if [ "$DRY_RUN" = false ] && [ "$OLD_BACKUPS" -gt 0 ]; then
    find "$HERMES_HOME/backups" -maxdepth 1 -name "*.tar.gz" -mtime +7 \
      -exec mv {} "$HERMES_HOME/backups/archive/" \;
    echo "  ✅ Archived $OLD_BACKUPS backups"
else
    echo "  Would archive $OLD_BACKUPS backups"
fi

# Phase 5: System logs (requires sudo)
echo ""
echo "🧹 Phase 5: Cleaning system logs..."
if command -v journalctl &> /dev/null; then
    JOURNAL_SIZE=$(sudo journalctl --disk-usage 2>/dev/null | grep -oP '\d+\.\d+[GM]' | head -1 || echo "N/A")
    echo "  Current journal size: $JOURNAL_SIZE"
    
    if [ "$DRY_RUN" = false ]; then
        echo "  Vacuuming journal (keep last 7 days)..."
        sudo journalctl --vacuum-time=7d
        echo "  ✅ Journal vacuumed"
    else
        echo "  Would vacuum journal to 7 days"
    fi
else
    echo "  journalctl not available"
fi

# Show final disk usage
echo ""
echo "📊 Final disk usage:"
df -h / | grep -E "Filesystem|/$"
echo ""
du -sh "$HERMES_HOME" 2>/dev/null || echo "Hermes home: N/A"

echo ""
if [ "$DRY_RUN" = true ]; then
    echo "🔍 Dry run complete. Run without --dry-run to apply changes."
else
    echo "✅ Cleanup complete!"
fi
