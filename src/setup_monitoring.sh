#!/usr/bin/env bash
# Phase 1: Install Prometheus node_exporter + activate Prometheus + enable n8n metrics
set -euo pipefail

NODE_EXPORTER_VERSION="1.8.2"
ARCH="linux-amd64"
WORKSPACE="/home/Bilirubin/workspace"

echo "=== Phase 1 monitoring setup ==="

# --- node_exporter ---
if [ ! -f /usr/local/bin/node_exporter ]; then
  echo "[1/4] Downloading node_exporter ${NODE_EXPORTER_VERSION}..."
  TMP=$(mktemp -d)
  curl -fsSL "https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.${ARCH}.tar.gz" \
    -o "${TMP}/node_exporter.tar.gz"
  tar -xzf "${TMP}/node_exporter.tar.gz" -C "${TMP}"
  sudo install -m 0755 "${TMP}/node_exporter-${NODE_EXPORTER_VERSION}.${ARCH}/node_exporter" /usr/local/bin/node_exporter
  rm -rf "${TMP}"
  echo "  node_exporter installed → $(node_exporter --version 2>&1 | head -1)"
else
  echo "[1/4] node_exporter already present, skipping download."
fi

# --- systemd unit: node_exporter ---
echo "[2/4] Installing systemd units..."
sudo cp "${WORKSPACE}/node-exporter.service" /etc/systemd/system/node-exporter.service
sudo cp "${WORKSPACE}/prometheus.service" /etc/systemd/system/prometheus.service

sudo systemctl daemon-reload
sudo systemctl enable node-exporter.service prometheus.service
sudo systemctl start node-exporter.service
sudo systemctl start prometheus.service
echo "  Services started."

# --- n8n metrics ---
echo "[3/4] Enabling n8n metrics endpoint..."
N8N_ENV="/srv/automation/n8n.env"
if grep -q "^N8N_METRICS=" "${N8N_ENV}" 2>/dev/null; then
  sudo sed -i 's/^N8N_METRICS=.*/N8N_METRICS=true/' "${N8N_ENV}"
else
  echo "N8N_METRICS=true" | sudo tee -a "${N8N_ENV}" > /dev/null
fi
sudo systemctl restart n8n.service
echo "  n8n metrics enabled."

# --- verify ---
echo "[4/4] Verification..."
sleep 3
echo -n "  node_exporter: "
curl -fsS http://127.0.0.1:9100/metrics | head -2 | tail -1 || echo "FAIL — check node-exporter.service logs"
echo -n "  prometheus: "
curl -fsS http://127.0.0.1:9090/-/ready || echo "FAIL — check prometheus.service logs"
echo
echo "=== Monitoring stack ready ==="
echo "  Prometheus: http://127.0.0.1:9090 (localhost only — expose via nginx with auth if needed)"
echo "  node_exporter: http://127.0.0.1:9100/metrics"
