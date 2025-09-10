cat > "$REPO/update.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

# Secrets
set -a
source "$REPO_DIR/secrets/env"
set +a

# Align to minute so timestamps are stable
sleep $(( 60 - $(date +%S) ))

# Ensure feeder branch exists & is current
git checkout -B status-updates || true
git pull --rebase origin status-updates || true

# Run exporter
"./.venv/bin/python" "./tools/exporter.py"

# Commit only if health.json changed
git add health.json
if git diff --cached --quiet; then
  echo "No changes in health.json"
  exit 0
fi

git -c user.name="status-bot" -c user.email="status-bot@local" \
  commit -m "minute update: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push origin status-updates
EOF

chmod +x "$REPO/update.sh"