#!/usr/bin/env bash
# Rejoue en local exactement la même séquence que .github/workflows/tests.yml
# — pratique depuis Termux pour vérifier avant un `git push`.
set -e

cd "$(dirname "$0")/.."

python3 tests/run_all.py
python3 examples/end_to_end.py

echo ""
echo "Tout est vert."
