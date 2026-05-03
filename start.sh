#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Install dependencies if not already present
if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "Installing dependencies…"
  pip3 install -r requirements.txt
fi

echo "Starting Home Transit Board on http://0.0.0.0:8080"
uvicorn app:app --host 0.0.0.0 --port 8080
