# Security Policy

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Report it privately through GitHub's private reporting for this repository
(**Security → Report a vulnerability**). If private reporting is unavailable,
email the maintainer at <mailto:jaimedejusto@gmail.com> and ask for a secure
channel before sending sensitive details. Do not open a public issue with
reproduction steps or vulnerability details.

Include: affected version or commit, reproduction steps, impact, and any
suggested mitigation. Expect an acknowledgement within a week.

## What counts as a vulnerability here

- Anything that leaks credentials, connection strings, API keys or personal
  data that is committed to the repository.
- Code injection or unsafe deserialization reachable from a normal run.
- A path that writes market data to a persistent store. **Prices must never be
  persisted** by this project; if you find a code path that does, that is a bug
  worth reporting.
- Anything that causes the SEC ingestion to violate its fair-access rules
  (for example a missing or non-compliant `User-Agent`).

## Non-vulnerabilities

- The SEC answering HTTP 403/429. That is upstream rate limiting or a
  non-compliant contact, documented in the companion
  [Financial-DataBase SEC investigation](https://github.com/JdeJusto/Financial-DataBase/blob/main/docs/sec_403_investigation.md).
- Yahoo Finance rate limiting. Handled by the preflight
  (`backend/services/yahoo_health.py`).
- A report that only needs a configuration change you have not made yet (for
  example no `SEC_USER_AGENT` in your `.env`).

## Known dependency advisories

- **`ecdsa` 0.19.2 — CVE-2024-23342 / GHSA-wj6h-64fc-37mp (high, no fixed
  version).** `python-jose` depends on `ecdsa` unconditionally, and we declare
  it in the `Pipfile` to sign and validate JWTs. The vulnerable code is ECDSA
  signature *verification*, while this project only uses `HS256`
  (`ALGORITHM` in `backend/core/config.py`, used by `backend/core/security.py`),
  so the path is unreachable today. We keep the alert open rather than
  dismissing it, so a future switch to an ECDSA algorithm resurfaces it. If we
  ever need asymmetric JWT signing, replace `python-jose` with a maintained
  JOSE implementation first.

## Supported versions

| Version | Supported |
| --- | --- |
| `main` | yes |
| older commits / tags | no — pin to `main` and rebuild |

This project has no release tags yet; `main` is the supported line.

## Disclosure policy

1. Report privately.
2. Confirm receipt, then confirm the fix and its release.
3. Publish the advisory after the fix is available, unless disclosure would
   put users at risk.
4. Credit the reporter unless anonymity is preferred.

We will not pursue legal action over good-faith research that follows this
policy, respects other users' data, and does not degrade the service.
