#!/bin/bash
# ホッシーくん画面（127.0.0.1:8765）。Tunnel には出さない。
set -euo pipefail

PYTHON="${HOSSY_PYTHON:-/Users/hoshiokomatsu/hosshy/venv/bin/python}"
SERVER_DIR="${HOSSY_SERVER_DIR:-/Users/hoshiokomatsu/hosshy/mcp-server}"
cd "$SERVER_DIR"
exec "$PYTHON" ui_server.py
