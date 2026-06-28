#!/usr/bin/env bash
# build_layer.sh
# Packages Python dependencies into a Lambda-compatible layer zip.
# Run this before `cdk deploy`.

set -euo pipefail

LAYER_DIR="lambda_layer/python"
ZIP_FILE="lambda_layer.zip"

echo "→ Cleaning old layer..."
rm -rf lambda_layer "$ZIP_FILE"

echo "→ Installing dependencies into $LAYER_DIR ..."
mkdir -p "$LAYER_DIR"
pip install \
    requests \
    beautifulsoup4 \
    pandas \
    --target "$LAYER_DIR" \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    --upgrade

echo "→ Lambda layer ready at: $LAYER_DIR"
echo "✓ Done. CDK will bundle this directory automatically."
