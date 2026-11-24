# Dependency security (Dependabot)

Last review: 2026-11-03 (CI repair + Dependabot triage). The npm surfaces
(mobile app and web frontend) were retired in v0.36.0, so the project has a
single Python dependency graph.

## Gates

- **Backend**: `pipenv verify` and the pin contract in
  `tests/unit/test_pipfile_lock_pins.py`. Audits are run by hand with
  `pip-audit` against the project interpreter. `pipenv update <pkg> --lock-only`
  re-resolves the whole graph, so every lock refresh must be diffed and the
  pin test must stay green.
- **Alerts**: GitHub parses `Pipfile.lock` natively for the dependency graph
  even though the `pip` ecosystem is not in `.github/dependabot.yml`
  (security updates work without a version-update entry).

## Fixed in this cycle

| Package | From → To | Alerts | Fix |
|---|---:|---:|---|
| `pillow` | 12.3.0 → 13.0.0 | 41 (5 crit, 23 high, 13 med) | `streamlit` 1.66.0 → 1.66.1 first: 1.66.0 pinned `pillow<13`; 1.66.1 allows `<14` |
| `soupsieve` | 2.10 → 4.0.0 | high | polynomial-time DoS in `< 4.0.0`; parser tests green with BeautifulSoup 4.15.0 |

The Pillow bump only changes the `streamlit` and `pillow` entries of
`Pipfile.lock`; `pyarrow 25.0.1`, `soupsieve 4.0.0` and `websockets 16.1.1`
are guarded by `test_pipfile_lock_pins.py`. `pip-audit` reports no known
vulnerabilities afterwards.

## Dependabot configuration

`.github/dependabot.yml` groups minor/patch updates for GitHub Actions so the
backlog does not turn into one PR per action. The `pip` ecosystem stays
disabled because pipenv rejects the `python_version` range in
`Pipfile.requires` (pypa/pipenv#1050); Python packages are updated by hand
with the pin review described above.
