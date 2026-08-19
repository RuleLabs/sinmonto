# Contributing to sinmonto

*[Version française](./docs/fr/CONTRIBUTING.md)*

Thanks for your interest in `sinmonto` (*Sɛ́n mɔto*, Fon for "rule engine").

This project was developed solo from a phone (Termux, Android — no PC),
with an unusual multi-AI governance model: architectural decisions go
through documented cross-reviews, not a single opinion. External
contributions are welcome, within that framework.

## Before you start

1. Read [`README.md`](README.md) — usage and known limitations.
2. Read [`docs/constitution-finale.md`](docs/constitution-finale.md) §2
   *(French)* — the **10 locked architectural decisions**. They're not
   up for debate in an issue or PR. If a genuine technical impossibility
   comes up while implementing (not in theory), flag it explicitly —
   don't quietly work around it.
3. If you're touching the core: [`AGENTS.md`](AGENTS.md) *(French)* for
   code conventions and the exact verification routine.

## The 10 locked decisions

1. No full Rete network — light alpha indexing only.
2. `Context` mutable during an evaluation cycle, frozen into an immutable
   `FrozenContext` at the end (`commit()`).
3. `Signal` (trigger) and `Fact` (information) are two distinct types.
4. Effects-as-data: no rule executes a side effect — it returns described
   `Effect`s, a separate executor applies them.
5. Native explainability — every condition, true or false, must be
   traceable.
6. No multi-day durability in the core (`ContextStore`/`FactStore` are
   abstract, in-memory implementations by default).
7. Injected time (`Clock`), never `time.time()` in the engine.
8. `engine.compile()` locks the configuration.
9. `__slots__` on hot internal objects — never on the user `payload`.
10. Common `Evaluable` protocol, distinct classes implementing it.

## The v1.0 filter

Before proposing a feature: *"does this genuinely bring v1.0 closer, or
are we dreaming up a feature that may never actually need to exist right
now?"* If it's the second answer, the idea belongs in
[`docs/roadmap-vision.md`](docs/roadmap-vision.md) *(French)*, not in the
core just yet.

## Installing and running the tests

```bash
git clone https://github.com/RuleLabs/sinmonto.git
cd sinmonto
pip install -e .
```

Zero runtime or test dependencies — no `pytest`. Tests live in `tests/`,
separate from the source code. From the repo root:

```bash
python3 tests/run_all.py
python3 examples/end_to_end.py
```

*(`./scripts/test_all.sh` runs both in one command.)*

To debug a single module: `python3 tests/run_all.py test_core`.

Files in `tests/` import `sinmonto` normally (`pip install -e .` makes
that possible); `tests/run_all.py` also adds the repo root to `sys.path`
as a fallback in case the editable install was skipped. A failure exits
with a non-zero code (`os._exit(1)`), usable in CI.

## How to propose a change

**Typo, broken link, doc fix** — direct PR, no issue needed.

**Bug fix** — Open a short issue (expected vs. observed behavior, how to
reproduce, mini-runner output if relevant). A PR can follow immediately
if you already have the fix.

**Architectural change** (new feature, behavior change, new primitive) —
Open an issue first. Don't start coding before the direction is
validated. These decisions go through the **living contract** process
([`docs/contrat-vivant-gabarit.md`](docs/contrat-vivant-gabarit.md)
*(French)*): a written mission, cross-reviews, a structured report,
synthesis before locking in. You can take part — propose a mission,
respond to a report — but the final call rests with the maintainer.

### What we expect in a PR
- A clean change, a clear scope — no hidden rewrite tucked into a
  three-line patch.
- Relevant tests run locally, plus `examples/end_to_end.py`.
- Docs updated (`README.md`, `CHANGELOG.md`, or `docs/`) if visible
  behavior changes.
- No direct import from an internal module (`from sinmonto._core import
  Fact`) — only the `sinmonto.__all__` surface (37 names) is guaranteed.

## The expected tone

[`docs/journal-integration.md`](docs/journal-integration.md) *(French)*
honestly documents bugs, false starts, and review mistakes — yours
included, where relevant. That's not something to hide, it's a project
value. *"I first tried X, it didn't work because Y, I ended up going
with Z"* is a perfectly valid PR description here — preferable to a
polished-over account.

## Review

The repo is maintained solo, in 0.x preview. Response time may vary
depending on the maintainer's availability (from their phone). No SLA
expectation; a polite ping after two weeks of silence is welcome.

## License

By contributing, you agree that your contribution is published under the
project's license: [Apache License 2.0](LICENSE).
