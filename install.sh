#!/usr/bin/env bash
set -euo pipefail

python -m venv venv
. venv/bin/activate
pip install -r requirements
playwright install
playwright install-deps
python -m camoufox fetch
patchright install chromium

npm install
git config core.hooksPath .githooks

./scripts/obfuscate_improved_stealth.sh

if [ ! -f .env ]; then
  cp .env.example .env
fi
