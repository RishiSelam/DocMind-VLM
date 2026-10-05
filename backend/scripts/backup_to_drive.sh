#!/usr/bin/env bash
# Copy all DocMind runs to Google Drive with rclone, in a new dated folder each time.
#
#   bash backend/scripts/backup_to_drive.sh                 # runs, history, database, reports, logs
#   bash backend/scripts/backup_to_drive.sh --with-uploads  # also the uploaded documents (~90 MB)
#
# Needs an rclone remote (default name "gdrive", override with DOCMIND_REMOTE) whose root is the
# shared Drive folder. Uses "rclone copy", so nothing on Drive is ever deleted or overwritten.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REMOTE="${DOCMIND_REMOTE:-gdrive}"
RCLONE="$(command -v rclone || echo "$HOME/.local/bin/rclone")"
PY="$ROOT/backend/.venv/bin/python"; [ -x "$PY" ] || PY=python3
STAMP="$(date +%Y%m%d-%H%M%S)"
STAGE="$ROOT/data/exports/drive-$STAMP"

mkdir -p "$STAGE"
"$PY" "$ROOT/backend/scripts/export_runs.py" --out "$STAGE/runs"
"$PY" "$ROOT/backend/scripts/export_history.py" --out "$STAGE/history"
cp "$ROOT/RUN_REPORT.md" "$STAGE/" 2>/dev/null || true
[ -d "$ROOT/logs" ] && cp -r "$ROOT/logs" "$STAGE/logs"
if [ "${1:-}" = "--with-uploads" ]; then cp -r "$ROOT/data/uploads" "$STAGE/uploads"; fi

"$RCLONE" copy "$STAGE" "$REMOTE:docmind-$STAMP" --progress
echo "Uploaded to $REMOTE:docmind-$STAMP (local copy: $STAGE)"
