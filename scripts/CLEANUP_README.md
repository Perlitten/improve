# 🧹 Disk Cleanup Scripts

**Phase 1, Day 4**

---

## 📁 Scripts

### 1. cleanup_disk.sh

**Purpose:** Manual disk cleanup with dry-run mode

**Usage:**
```bash
# Dry-run (show what would be cleaned)
bash cleanup_disk.sh --dry-run

# Actual cleanup
bash cleanup_disk.sh
```

**What it cleans:**
- Old logs (> 30 days)
- Temporary files (> 7 days)
- Python cache (__pycache__, *.pyc)
- Old backups (> 7 days → archive)
- System logs (journalctl vacuum)

**Features:**
- Dry-run mode for safe testing
- Disk usage reporting (before/after)
- Safe error handling
- Progress indicators

---

### 2. setup_automatic_cleanup.sh

**Purpose:** Setup automatic cleanup (logrotate + cron)

**Usage:**
```bash
# Setup automatic cleanup (requires sudo)
sudo bash setup_automatic_cleanup.sh
```

**What it configures:**
- **Logrotate:** `/etc/logrotate.d/hermes`
  - Daily rotation
  - Keep 30 days
  - Compress old logs
  - Reload services after rotation

- **Daily cleanup:** `/etc/cron.daily/hermes-cleanup`
  - Remove old temp files (> 7 days)
  - Remove old logs (> 30 days)
  - Archive old backups (> 7 days)
  - Clean Python cache
  - Log disk usage

- **Weekly cleanup:** `/etc/cron.weekly/hermes-backup-cleanup`
  - Remove old archived backups (> 30 days)
  - Report archive size

**Features:**
- Configuration testing
- Safe error handling
- Automatic execution (no manual intervention)

---

## 🚀 Deployment

### Quick Deploy (from Windows)

```powershell
cd hermes/deploy
.\deploy_cleanup.ps1
```

This will:
1. Copy scripts to server
2. Make them executable
3. Run dry-run first
4. Ask for confirmation
5. Run actual cleanup
6. Setup automatic cleanup
7. Show final disk usage

### Manual Deploy

```bash
# On server
cd /home/Bilirubin/workspace/hermes

# Copy scripts (if not already there)
# ...

# Make executable
chmod +x scripts/cleanup_disk.sh
chmod +x scripts/setup_automatic_cleanup.sh

# Test cleanup (dry-run)
bash scripts/cleanup_disk.sh --dry-run

# Run cleanup
bash scripts/cleanup_disk.sh

# Setup automatic cleanup
sudo bash scripts/setup_automatic_cleanup.sh
```

---

## 📊 Expected Impact

### Initial Cleanup
- Old logs: 100-500 MB
- Python cache: 50-200 MB
- System logs: 100-1000 MB
- **Total:** 250-1700 MB

### Ongoing Savings
- Daily: 10-50 MB
- Weekly: 50-200 MB
- **Monthly:** 200-800 MB

---

## ✅ Verification

### Check Disk Usage

```bash
# Overall disk usage
df -h /

# Hermes directory usage
du -sh ~/.hermes

# Logs directory
du -sh ~/.hermes/logs

# Backups directory
du -sh ~/.hermes/backups
```

### Check Automatic Cleanup

```bash
# Check logrotate config
sudo cat /etc/logrotate.d/hermes

# Check daily cleanup
sudo cat /etc/cron.daily/hermes-cleanup
sudo ls -l /etc/cron.daily/hermes-cleanup

# Check weekly cleanup
sudo cat /etc/cron.weekly/hermes-backup-cleanup
sudo ls -l /etc/cron.weekly/hermes-backup-cleanup

# Test logrotate
sudo logrotate -d /etc/logrotate.d/hermes

# View cleanup logs
tail -f ~/.hermes/logs/cleanup.log
```

### Monitor Cleanup

```bash
# Watch cleanup logs
tail -f ~/.hermes/logs/cleanup.log

# Check cron execution
sudo grep hermes /var/log/syslog

# Check disk usage over time
df -h / | grep -E "/$"
```

---

## 🛠️ Troubleshooting

### Cleanup Script Fails

**Problem:** Script exits with error

**Solution:**
1. Check permissions: `ls -l scripts/cleanup_disk.sh`
2. Make executable: `chmod +x scripts/cleanup_disk.sh`
3. Check disk space: `df -h /`
4. Check logs: `tail -f ~/.hermes/logs/cleanup.log`

### Automatic Cleanup Not Running

**Problem:** Cron jobs not executing

**Solution:**
1. Check cron service: `sudo systemctl status cron`
2. Check cron logs: `sudo grep hermes /var/log/syslog`
3. Check script permissions: `sudo ls -l /etc/cron.daily/hermes-cleanup`
4. Make executable: `sudo chmod +x /etc/cron.daily/hermes-cleanup`
5. Test manually: `sudo /etc/cron.daily/hermes-cleanup`

### Logrotate Not Working

**Problem:** Logs not rotating

**Solution:**
1. Check logrotate config: `sudo cat /etc/logrotate.d/hermes`
2. Test logrotate: `sudo logrotate -d /etc/logrotate.d/hermes`
3. Force rotation: `sudo logrotate -f /etc/logrotate.d/hermes`
4. Check logrotate logs: `sudo cat /var/log/logrotate.log`

### Disk Still Full

**Problem:** Disk usage still > 70%

**Solution:**
1. Find large files: `find ~/.hermes -type f -size +100M -exec ls -lh {} \;`
2. Check system logs: `sudo journalctl --disk-usage`
3. Vacuum journal: `sudo journalctl --vacuum-time=7d`
4. Check other directories: `du -h / | sort -rh | head -20`
5. Consider archiving more data

---

## 📝 Maintenance

### Regular Checks

**Daily:**
- Check cleanup logs: `tail ~/.hermes/logs/cleanup.log`
- Check disk usage: `df -h /`

**Weekly:**
- Review cleanup logs: `cat ~/.hermes/logs/cleanup.log`
- Check archive size: `du -sh ~/.hermes/backups/archive`

**Monthly:**
- Review disk usage trends
- Adjust cleanup thresholds if needed
- Review archived backups

### Adjusting Thresholds

**To change log retention:**
```bash
# Edit logrotate config
sudo nano /etc/logrotate.d/hermes

# Change "rotate 30" to desired days
```

**To change cleanup thresholds:**
```bash
# Edit daily cleanup script
sudo nano /etc/cron.daily/hermes-cleanup

# Change "-mtime +7" to desired days
```

---

## 🔗 Related Documentation

- [WEEK1_DAY4_PROGRESS.md](../WEEK1_DAY4_PROGRESS.md) - Day 4 progress
- [WEEK1_DAY4_DISK_CLEANUP.md](../WEEK1_DAY4_DISK_CLEANUP.md) - Day 4 plan
- [DAY4_COMPLETE.md](../DAY4_COMPLETE.md) - Completion summary

---

**Last Updated:** 2026-05-06  
**Status:** Ready to deploy ✅
