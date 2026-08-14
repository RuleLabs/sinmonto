#!/usr/bin/env python3
"""Découvre et lance tous les tests de tests/test_*.py. Zéro dépendance.

Usage :
    python3 tests/run_all.py              # tout lancer
    python3 tests/run_all.py test_core     # un seul module (débogage)

Remplace le mini-runner sinmonto/_testing.py (supprimé du package installé —
il n'était pas dans sinmonto.__all__, aucune raison de le livrer aux
utilisateurs finaux via `pip install sinmonto`). Le mécanisme de sortie
(compteur d'échecs + os._exit) est le même, vérifié pour cette raison précise
lors d'une revue croisée : sys.exit() seul, appelé depuis un callback atexit,
est explicitement avalé par Python — os._exit() après un flush() explicite
est nécessaire pour que le code de sortie soit réellement pris en compte.
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent

# Fallback si le package n'est pas installé en mode éditable (pip install -e .)
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _discover_test_modules() -> list[str]:
    return sorted(
        f"tests.{f.stem}"
        for f in _TESTS_DIR.glob("test_*.py")
    )


def run(only: str | None = None) -> None:
    total = 0
    failures = 0

    for mod_name in _discover_test_modules():
        if only and only not in mod_name:
            continue

        mod = importlib.import_module(mod_name)
        test_fns = sorted(
            (name, fn)
            for name in dir(mod)
            if name.startswith("test_") and callable(fn := getattr(mod, name))
        )
        if not test_fns:
            continue

        print(f"\n--- {mod_name} ---")
        for name, fn in test_fns:
            total += 1
            try:
                fn()
                print(f"  ok {name}")
            except AssertionError as e:
                failures += 1
                print(f"  FAIL {name}: {e}")
            except Exception as e:
                failures += 1
                print(f"  ERROR {name}: {type(e).__name__}: {e}")
                traceback.print_exc()

    print(f"\n{total} tests, {failures} échec(s).")
    if failures:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)


if __name__ == "__main__":
    run(only=sys.argv[1] if len(sys.argv) > 1 else None)
