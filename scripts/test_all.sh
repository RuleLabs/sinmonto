#!/usr/bin/env bash
# Rejoue en local exactement la même séquence que .github/workflows/tests.yml
# — pratique depuis Termux pour vérifier avant un `git push`.
set -e

cd "$(dirname "$0")/.."

python3 -m sinmonto._exceptions
python3 -m sinmonto._core
python3 -m sinmonto._trace
python3 -m sinmonto._testing
python3 -m sinmonto._context
python3 -m sinmonto._dsl
python3 -m sinmonto._engine
python3 examples/end_to_end.py

echo ""
echo "Tout est vert."
