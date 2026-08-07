"""Mini-runner de test interne. Zéro dépendance externe.

Remplace pytest tant que la surface du projet ne le justifie pas.
"""

from __future__ import annotations

import atexit
import os
import sys
import traceback
from typing import Any, Callable

_failure_count = 0


def test(name: str, fn: Callable[[], None]) -> None:
    global _failure_count
    try:
        fn()
        print(f"  ok {name}")
    except AssertionError as e:
        _failure_count += 1
        print(f"  FAIL {name}: {e}")
    except Exception as e:
        _failure_count += 1
        print(f"  ERROR {name}: {type(e).__name__}: {e}")
        traceback.print_exc()


def assert_eq(actual: Any, expected: Any, msg: str = "") -> None:
    if actual != expected:
        raise AssertionError(f"{msg}\nExpected: {expected}\nActual: {actual}")


def _exit_nonzero_if_any_failure() -> None:
    # Avant : un run avec des FAIL/ERROR s'affichait mais se terminait avec
    # un code de sortie 0 — un script CI ne détectait jamais l'échec.
    # Trouvé en revue croisée (DeepSeek, Qwen) — 2026-08.
    #
    # sys.exit() ici ne suffit PAS : une exception levée depuis un callback
    # atexit est explicitement avalée par Python ("Exception ignored in
    # atexit callback"), le code de sortie du process reste 0 quand même —
    # vérifié en le testant, pas supposé. os._exit() contourne ce mécanisme
    # (sortie directe, sans lever SystemExit) ; flush explicite d'abord
    # pour ne pas perdre les lignes déjà imprimées.
    if _failure_count:
        print(f"\n{_failure_count} test(s) en échec.")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)


atexit.register(_exit_nonzero_if_any_failure)


if __name__ == "__main__":
    def test_pass() -> None:
        assert_eq(1 + 1, 2)

    def test_assert_eq_raises_on_mismatch() -> None:
        try:
            assert_eq(1, 2, "one is not two")
        except AssertionError:
            pass
        else:
            raise AssertionError("assert_eq should have raised")

    test("basic pass", test_pass)
    test("assert_eq raises correctly", test_assert_eq_raises_on_mismatch)
