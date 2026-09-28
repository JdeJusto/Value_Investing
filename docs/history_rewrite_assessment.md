# Git history assessment

This assessment is superseded by the maintainer's decision recorded in
[`history_rewrite_recommendation.md`](history_rewrite_recommendation.md).

**Decision — 2026-09-28:** keep the existing history. The maintainer accepts
the account-associated author email in historical commits; no filter-repo,
rebase, or force-push is planned. The contact email is intentionally published
in `SECURITY.md` and `CODE_OF_CONDUCT.md`.

This decision does not apply to credentials, API keys, database passwords,
private user data, or another person's contact details. Those must never be
committed. This file intentionally contains no history-rewrite commands; the
earlier assessment was based on the repositories' previous private status and
is no longer a current release checklist.
