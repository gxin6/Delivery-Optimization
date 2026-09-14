#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
REQS="$PROJECT_ROOT/requirements.txt"

if [ ! -f "$REQS" ]; then
    echo "ERROR: $REQS not found" >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found on PATH" >&2
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
else
    echo "Using existing venv at $VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "Installing requirements from $REQS ..."
pip install -r "$REQS"
