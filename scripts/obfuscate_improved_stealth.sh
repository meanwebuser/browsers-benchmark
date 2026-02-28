#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT_FILE="$REPO_ROOT/utils/js_scripts/stealth_improved.js"
OUTPUT_FILE="$REPO_ROOT/utils/js_scripts/stealth_improved.obf.js"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

npx --yes javascript-obfuscator "$INPUT_FILE" \
  --output "$TMP_DIR" \
  --compact true \
  --control-flow-flattening true \
  --control-flow-flattening-threshold 0.75 \
  --dead-code-injection true \
  --dead-code-injection-threshold 0.4 \
  --seed 20260228 \
  --string-array true \
  --string-array-encoding base64 \
  --string-array-threshold 0.75 \
  --self-defending true \
  --disable-console-output true

mv "$TMP_DIR/$(basename "$INPUT_FILE")" "$OUTPUT_FILE"
echo "Updated $OUTPUT_FILE"
