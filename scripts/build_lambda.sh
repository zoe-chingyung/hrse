#!/bin/bash
# Runs inside the Lambda builder container.
# Installs runtime deps + hrse package into /out,
# which is mounted from the host as lambda_packages/hrse/.

set -euo pipefail

OUT_DIR="/out"

echo "[1/3] Cleaning output directory..."
rm -rf "${OUT_DIR:?}"/*

echo "[2/3] Installing runtime dependencies..."
pip install \
    --target "$OUT_DIR" \
    --requirement /build/requirements.txt \
    --quiet \
    --root-user-action ignore

echo "[3/3] Installing hrse package..."
pip install \
    --target "$OUT_DIR" \
    --no-deps \
    /build \
    --quiet \
    --root-user-action ignore

FILE_COUNT=$(python3 -c "import os; print(sum(len(f) for _,_,f in os.walk('$OUT_DIR')))")
echo "Done — $FILE_COUNT files in package."
echo "Run 'terraform apply' to zip and deploy."
