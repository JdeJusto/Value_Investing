# Security posture

Last full sweep: 2026-11-18 (v0.34.8 + picomatch advisory).

## Dependabot

| Repo | Open | High | Med | Low | Notes |
|---|---:|---:|---:|---:|---|
| Value_Investing (mobile) | 2 | 1 | 0 | 1 | `picomatch` high (no fix) + `deepmerge` low |
| Value_Investing (frontend) | 1 | 1 | 0 | 0 | `picomatch` high, cascades through Vite/fdir/tinyglobby |
| Value_Investing (Pipfile.lock) | 0 | 0 | 0 | 0 | `dnspython`/`opentelemetry-api` fixed; pins guarded |
| Financial-DataBase | 0 | 0 | 0 | 0 | `pip-audit`/Dependabot clean |

Closed in this sweep:

| Package | Manifest | Severity | Resolution |
|---|---|---|---|
| `zod` | `mobile/package-lock.json` | high | override `^4.6.7` |
| `glob` | `mobile/package-lock.json` | moderate | override `^14.0.6` |
| `node-forge` | `mobile/package-lock.json` | low/medium | override `^1.4.3` (4 alerts) |
| `minimatch` | `mobile/package-lock.json` | moderate | overrides `^11.0.8` for `@typescript-eslint/typescript-estree` and `@expo/fingerprint` |
| `soupsieve` | `Pipfile.lock` | high | upgraded 2.10 → **4.0.0** (polynomial-time DoS in `< 4.0.0`) |

## Code Scanning (CodeQL)

| Repo | Open | Notes |
|---|---:|---|
| Value_Investing | 0 | path-injection in the price cache fixed in v0.32.1 (SHA-256 cache keys) |
| Financial-DataBase | 0 | — |

## Secret Scanning

| Repo | Open |
|---|---:|
| Value_Investing | 0 |
| Financial-DataBase | 0 |

The FMP and Tiingo keys are read from `.env` (gitignored) and are never
written to tracked files, tests, docs or logs. Provider exceptions are
redacted before logging (`***`). `.env.example` contains placeholders only.

## Accepted risks

- **`deepmerge` (mobile, low)**: no patched version exists (`>=4.2.0` is
  vulnerable and 4.3.1 is the latest). It is a build-time dependency of
  Jest/Expo config, not part of the runtime Metro bundle. Revisit when Jest
  or Expo replaces it.
- **`picomatch` (mobile + frontend, high, GHSA-fc5q-39xc-vjpf)**: ReDoS in
  single-branch repeated extglobs. The advisory range is `*` and no patched
  version exists (2026-11-18). It reaches Expo CLI/Metro (mobile) and Vite
  (frontend) as a build-time glob dependency, not the runtime bundle.
  `config/npm_audit_allowlist.txt` contains this single GHSA; all other
  high/critical findings still fail CI. Revisit as soon as picomatch ships
  a fix and remove the line.
- **Expo/Jest low-severity advisories**: the remaining low findings require a
  downgrade to Expo 52 / Jest 25 (`fixAvailable.isSemVerMajor: true`), which
  would break the SDK.
- CI runs `scripts/npm_audit_gate.py` for mobile and frontend. It fails on any
  high/critical finding except the explicitly allowlisted GHSA; critical
  findings are never allowed.

## Historical fixes

- 2026-11-11: path-injection in the price cache (v0.32.1). SHA-256 cache
  keys; CodeQL 4 high → 0.
- 2026-11-13: mobile Dependabot zod/glob/node-forge/minimatch patched.
- 2026-11-13: soupsieve 4.0.0 (high, DoS); parser tests green with
  BeautifulSoup 4.15.0.
- 2026-11-18: dnspython 2.9.2 (high, GHSA-vvf4-9x63-8xvv) and
  opentelemetry-api 1.45.2 (moderate, CVE-2026-126360) from Dependabot
  #85/#84; transitive lock-only update.

## How to re-run the sweep

```bash
gh api "repos/JdeJusto/Value_Investing/dependabot/alerts?state=open" \
  --paginate --jq '[.[] | {severity: .security_advisory.severity, package: .dependency.package.name}]'
gh api "repos/JdeJusto/Value_Investing/code-scanning/alerts?state=open" --paginate
gh api "repos/JdeJusto/Value_Investing/secret-scanning/alerts?state=open" --paginate
python3 scripts/npm_audit_gate.py --cwd mobile
python3 scripts/npm_audit_gate.py --cwd frontend
.venv/bin/pipenv verify
```
