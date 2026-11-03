# Code Scanning (CodeQL) findings

Last review: 2026-10-24 (post-v0.19.2 maintenance)

## Open (1)

- **#24** `py/incomplete-url-substring-sanitization` (warning) in
  `tests/unit/test_boot_script.py` — test code only, uses substring check
  against a known test URL pattern. Not a production security issue; no fix
  applied to avoid changing test semantics. Risk accepted.

## Fixed (23)

All previous CodeQL alerts (path injection in services/cache, workflow
permissions, etc.) are marked fixed on `main`. See GitHub Security > Code
Scanning for history.
