# LEARNINGS.md (working notes — not committed)

Session 2026-10-20, Fase C.2 radar filter.

## AppTest (streamlit.testing.v1) facts
- `on_change` callbacks **do fire** on `box.set_value(...)` + `at.run()`.
- `Checkbox.disabled` is readable even though it is not a class attribute
  (proto `__getattr__` proxy). `check()`/`uncheck()` also exist.
- Widget `id` for keyed widgets embeds the key: `$$ID-<hash>-<key>`.
  Find widgets by **label** (`box.label == "Growth"`), not by `w.id == key`.
- `at.html` is **not** the page HTML — it is the accessor for `st.html`
  elements. Page-level HTML is only available from a real browser session
  (playwright `page.content()`). For AppTest, serialize `at._tree` instead.
- `at._tree` structure: root → 3 SpecialBlocks (main/sidebar/event) →
  nested `Block`/`Column`/`Tab` nodes. Containers expose both a `proto`
  AND a `children` dict — recurse `children` **and** emit `proto`; walking
  only one direction loses most of the page (10 vs ~120 blocks).
- Widget protos serialize deterministically via
  `google.protobuf.json_format.MessageToDict(..., preserving_proto_field_name=True)`.

## Render-comparison worktrees
- `git worktree add --detach /tmp/opencode/wt-baseline <sha>`; then copy
  gitignored `data/peer_stats/` (20 files) and symlink `.env`, or the
  caption surface diverges for environmental reasons (Phase F lesson).
- No editable install in `.venv`, so `sys.path.insert(0, <worktree>)` +
  `os.chdir(<worktree>)` cleanly resolves `ui.*`/`backend.*` to the tree
  under test.
- Payload helpers can be imported from each tree's own
  `tests/unit/test_ui_scorecard_tab.py` via `importlib.util.spec_from_file_location`,
  guaranteeing both trees render the exact same input.

## Output discipline
- AppTest caption/markdown dumps include a ~1.5 KB demo-ticker caption.
  Always filter (`"dimensions shown" in c`) or `tail` before printing.
- **Never print `at.html` or the raw dump JSON** — write to a file and
  print only the byte/block count (hook enforces this).
- The output-limits hook requires learnings be persisted here and the root
  cause (printing large payloads) addressed, not just suppressed.
- Batch long verifications (pytest unit + api + ruff + format) into one
  `shell` call that redirects each stream to its own file under
  `/tmp/opencode/`, then `cat`/read only the tails. A single chained call
  beats four round-trips and keeps output near zero.

## Git: deleting a just-merged branch
- After `merge --ff-only` + `push`, `git branch -d feat/x` can still refuse
  with "not fully merged" **if the branch is checked out in a worktree** —
  git compares against the worktree's upstream and refuses. Safe fix: run
  `git worktree remove` first, or accept that the content (the merge SHA)
  is already on main and delete with `-D` after confirming
  `git branch --contains <sha>` lists only main. Not a force-rewrite.
- Final Fase C.2 state: `main` = `64eda3e`, working tree clean, only
  `LEARNINGS.md` untracked (kept out of commits on purpose).

## Final Fase C.2 numbers
- unit 2376 passed / 2 skipped / 0 failed (2370 baseline + 6 new).
- api 125 passed. ruff check 0, ruff format 0 (568 files).
- verify_theme --all: 26 PASS / 4 FAIL (unchanged pre-existing metric-card).
- Byte-regression: PASS (radar figure spec identical, 8516 bytes).
- Assets: `assets/ui_v2_analysis_scorecard.png` refreshed via
  `scripts_dev/shoot.py analysis:Scorecard` (66869 bytes, 1440x960).

## Byte-regression comparison (baseline vs branch)
- Normalize the pre-existing run-to-run noise BEFORE diffing; each was
  confirmed present in a same-tree two-run self-comparison (`A vs A2`):
  1. widget ids: `$$ID-<hex32>-key` → `$$ID-key`
  2. pandas Styler CSS ids: `#T_<5-8 hex>_row...` → `#T_X_row...`
  3. pandas Styler `uuid` field: `"<5-8 hex>"` → `"X"`
  4. download-button media uuid: `/mock/media/<hex32>.csv` → `/mock/media/X.csv`
  5. **Raw-tab `Dataframe` (dcf_value)** differs run-to-run (~0.08% on
     1.75e12) even in the SAME tree and is **not** PYTHONHASHSEED-dependent
     (reproduced with `PYTHONHASHSEED=0`). Pre-existing, outside the
     Scorecard, left unfixed — flag as follow-up, do not normalize away
     silently: exclude that one block index from the equality claim and
     state it in the report.
- AppTest block count for `02_analysis.py`: baseline 408, branch +15 for
  the filter (1 Markdown + 2 Block + 6 Column + 6 Checkbox). The plotly
  figure lives in an `UnknownElement` whose `spec` field holds the escaped
  figure JSON; detect the radar with `"theta" in proto` (theta only appears
  on the radar, never the history charts).
- Final verdict so far: **PASS** — branch minus the 15-block filter region
  == baseline byte-for-byte (408 == 408), radar figure spec identical
  (8516 bytes), only diff is the pre-existing Raw-tab dcf_value block.

## 2026-10-21 — Re-verificación de dcf_value (Fase D pre-release)
- The Raw-tab `dcf_value` run-to-run nondeterminism (see Byte-regression
  section above) was **re-verified on the v0.19.1 tree and NOT reproduced**:
  two independent processes calling
  `ui.services.get_analysis_service().analyze("AAPL")` returned
  byte-identical values, both with the real repository (1377078740103.0334)
  and in `VI_DEMO=1` mode (1749786459612.4546 — matches the ~1.75e12 from
  the original observation, so the same data path).
- Backend code is identical to 64eda3e (only assets/READMEs changed after),
  so the original variance was likely data-in-flight (e.g. a concurrent FDB
  sync between the two runs) rather than code nondeterminism.
- Decision: NOT documented in CHANGELOG 0.19.1 (do not document what cannot
  be reproduced); keep as historical note here.
