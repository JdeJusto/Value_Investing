# Lint debt

## No remaining lint debt as of 2026-09-29

`ruff check .` passes with **0 errors** (down from 983 at the start of the
cleanup) and `ruff format --check` is clean on every touched file.

What the cleanup did, in order:

1. **Mechanical autofixes**: import hygiene (F401/I001/RUF100 with the full
   rule set active), modern typing (UP045/006/035/007/037), `datetime.UTC`
   (UP017), SIM/ISC/C408/RUF022.
2. **Documented boundary catch-alls**: `# noqa: BLE001` / `S110` / `S112`
   with the reason inline (providers, network, parser boundaries) — never a
   blanket noqa.
3. **Config** (`ruff.toml`): `target-version = "py314"`, FastAPI
   `Depends()`/`Query()`/... exempted from B008, and N999 ignored for the
   numbered Streamlit pages.
4. **Two real bugs** found by F821 and fixed with tests: the Yahoo
   `get_wacc` undefined-name path (now the shared `compute_wacc`) and the
   missing `CompanyRepository` import in `app/cli.py`.
5. **Isolated fixes**: dead duplicate methods (F811), `itertools.pairwise`
   (RUF007), identical isinstance branches (RUF034), explicit
   `check=False` (PLW1510), negated returns (SIM103/SIM211), dict
   iteration with `.items()` (PLC0206), `lines.extend` (PERF402),
   `ClassVar` (RUF012), duplicated fixture key (F601), `max()` (FURB192),
   implicit concatenation (FLY002) and specific frozen-dataclass
   exceptions in tests (B017).

The `# noqa` comments that remain in the codebase are intentional and each
carries a reason on the same line: boundary catches, the NaT check in the
dividend sorter, yfinance's naive split-index fixtures, and local
human-readable log timestamps.
