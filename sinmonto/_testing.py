"""Mini-runner de test interne. Zéro dépendance externe.

Remplace pytest tant que la surface du projet ne le justifie pas.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable


def test(name: str, fn: Callable[[], None]) -> None:
    try:
        fn()
        print(f"  ok {name}")
    except AssertionError as e:
        print(f"  FAIL {name}: {e}")
    except Exception as e:
        print(f"  ERROR {name}: {type(e).__name__}: {e}")
        traceback.print_exc()


def assert_eq(actual: Any, expected: Any, msg: str = "") -> None:
    if actual != expected:
        raise AssertionError(f"{msg}\nExpected: {expected}\nActual: {actual}")


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
