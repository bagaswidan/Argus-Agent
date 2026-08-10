# Contributing

Thanks for reading this before opening a PR. It'll save us both a round-trip.

## Ground rules

1. **Tests come first.** Write the failing test, watch it fail, then write the code that makes it pass. That's the project's rhythm and it's non-negotiable. A PR without a test for the change is a PR that's not done yet.
2. **No change-detector tests.** If your test fails whenever a model list grows, a version bumps, or an enum count changes, it's testing the wrong thing. Tests should assert how things relate, not freeze a current value. Example: assert every catalog entry has a context length, don't assert the exact catalog contents.
3. **No reading source in tests.** A test that opens a `.py` file and regexes its contents is testing the shape of code, not its behavior. Extract the logic into a small function and test that function.
4. **Fix the class, not the site.** If you found a bug, check sibling code paths for the same flaw before you merge your fix. We've had "fixed here, broken two lines down" more than once.

## Flaky policy

If a test passes on retry, it's still a bug. Timing-sensitive tests need real sync mechanisms (events, joins) and loose wall-clock bounds — no `assert not wait_until(...)` races. If you touched a test because it was flaky, say so in the PR description.

## Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the suite the way CI does:

```bash
scripts/run_tests.sh
```

That wrapper sets a clean env: temp HOME, UTC timezone, no provider keys. Don't call `pytest` directly and expect the same result — the wrapper exists because direct pytest on a dev machine diverges from CI.

Run one file:

```bash
scripts/run_tests.sh tests/unit/brain/test_router.py -q
```

## What belongs in core vs. what doesn't

Argus keeps its core narrow on purpose. Every model tool ships on every API call, so the bar for a new core tool is high. Before adding one, consider: does a CLI command + skill cover it? A service-gated tool? A plugin? An extension? Extensions are the preferred escape hatch — see `src/argus/extension/`.

Similarly: no new env vars for non-secret config. Settings go in `config.yaml`-style config. Env vars are for secrets only.

## Commit messages

Short subject, present tense. Reference what and why, not how:

```
fix: prefix-token rewrite for multi-word FTS5 queries
```

## PR checklist

- [ ] Tests written first, and they fail without the change
- [ ] Full suite passes via `scripts/run_tests.sh`
- [ ] No change-detector tests, no source-reading tests
- [ ] Sibling code paths checked for the same bug class
- [ ] Changelog entry added under `Unreleased`

That's it. Open the PR, and thank you for doing the checklist part so I don't have to ask.
