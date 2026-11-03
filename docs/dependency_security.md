# Dependency security (Dependabot)

Last review: 2026-11-03 (CI repair + Dependabot triage)

## Gates

- **Frontend**: `npm audit --audit-level=high` in CI (`.github/workflows/ci.yml`).
  `npm audit fix --force` is never used: it crosses majors that the parent
  packages do not support.
- **Backend**: `pipenv verify` and the pin contract in
  `tests/unit/test_pipfile_lock_pins.py`. Audits are run by hand with
  `pip-audit` against the project interpreter. `pipenv update <pkg> --lock-only`
  re-resolves the whole graph, so every lock refresh must be diffed and the
  pin test must stay green.
- **Alerts**: GitHub parses `Pipfile.lock` and `mobile/package-lock.json`
  natively for the dependency graph even though those ecosystems are not in
  `.github/dependabot.yml` (security updates work without a version-update
  entry).

## Fixed in this cycle

| Package | From → To | Alerts | Fix |
|---|---:|---:|---|
| `follow-redirects` | 1.16.1 → 1.16.2 | 1 (high) | `frontend/package.json` override (GHSA-mrwp-f3q8-3g9p) |
| `pillow` | 12.3.0 → 13.0.0 | 41 (5 crit, 23 high, 13 med) | `streamlit` 1.66.0 → 1.66.1 first: 1.66.0 pinned `pillow<13`; 1.66.1 allows `<14` |
| `node-forge` | 1.4.0 → 1.4.2 | 11 (5 high, 3 med, 3 low) | `mobile/package.json` override; reached through `expo` → `@expo/cli` |
| `decode-uri-component` | 0.5.0 → 0.5.1 | 1 (high) | `mobile/package.json` override; reached through `expo-router` → `query-string` |

The Pillow bump only changes the `streamlit` and `pillow` entries of
`Pipfile.lock`; `pyarrow 25.0.1`, `soupsieve 2.10`, `websockets 16.1.1` and
`fastapi 0.150.0` are unchanged (guarded by `test_pipfile_lock_pins.py`).
`pip-audit` reports no known vulnerabilities afterwards.

## Residual alerts (documented, not closed)

| Package | Installed | Fix | Why it is not applied | Revisit when |
|---|---|---|---|---|
| `glob` | 13.0.6 | 14.0.2 | `@expo/cli` requires `glob@^13`; 14 is a major with an ESM/API break | Expo CLI accepts glob 14 |
| `minimatch` | 10.2.6 | 11.0.1 | `@typescript-eslint/typescript-estree` requires `minimatch@^10.2.2`; dev-only tooling | typescript-eslint supports minimatch 11 |
| `zod` | 3.25.76 | 4.6.6 | Expo 57 requires `zod@^3.25.76`; Dependabot reports `security_update_not_possible` because the update would downgrade Expo 57 → 54 | Expo SDK upgrade that supports zod 4 |
| `deepmerge` | 4.3.1 | none | No patched version published (GHSA-gcqx-w48m-w2h4, low; prototype poisoning in `mergeObject`, build/config and Jest only) | A patched release exists |

The only open Code Scanning alert (#24,
`py/incomplete-url-substring-sanitization` in `tests/unit/test_boot_script.py`)
is a test-only false positive documented in `docs/code_scanning.md`.

## Dependabot configuration

`.github/dependabot.yml` groups minor/patch updates for the frontend and
GitHub Actions so the backlog does not turn into one PR per dependency. The
`pip` ecosystem stays disabled because pipenv rejects the `python_version`
range in `Pipfile.requires` (pypa/pipenv#1050); Python packages are updated by
hand with the pin review described above. Mobile is covered by security
updates; its Expo-pinned majors are left to the regular SDK upgrade.
