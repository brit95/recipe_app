#!/usr/bin/env bash
# Build the single-file Recipe Manager binary on Linux/macOS.
# Run from the repo's `recipe_app/` directory.
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if [ ! -d ".venv" ]; then
    echo ">> creating .venv"
    "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo ">> installing build deps"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt >/dev/null
pip install pyinstaller >/dev/null

echo ">> building"
rm -rf build dist
pyinstaller --clean --noconfirm RecipeManager.spec

echo
echo "Build complete:"
ls -lh dist/
echo
echo "Run it:  ./dist/RecipeManager"
