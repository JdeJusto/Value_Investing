# History rewrite assessment — leaked SEC contact e-mail

**Decision: SKIP the rewrite.** Both repositories are **private**, the
e-mail is no longer in either HEAD, and rewriting the history would change
every hash, require a force-push and break any collaborator in exchange for
no reduction in exposure.

Nothing destructive was executed: no `git filter-repo`, no `rebase`, no
`--force`. This document is the assessment only.

## Visibility (measured, unauthenticated)

```bash
$ curl -s -o /dev/null -w "%{http_code}\n" https://github.com/JdeJusto/Value_Investing
404
$ curl -s -o /dev/null -w "%{http_code}\n" https://github.com/JdeJusto/Financial-DataBase
404
```

A public repository answers 200 to an anonymous request; 404 means the
repositories are private (or renamed). Both remotes point at
`github.com/JdeJusto/<repo>`, so the 404 applies to them.

**Consequence:** the literal e-mail was never exposed to the public. It only
ever existed in local clones and in the private remote.

## Where the literal appears

| Repo | In HEAD? | Commits that add or remove it | First appearance |
| --- | --- | --- | --- |
| Value Investing | **no** | 10 | `3b4ec1e` (2026-04-26, "ya esta la base") |
| Financial-DataBase | **no** | 2 | `3537f0b` (2026-09-27, live SEC refresh report) |

Value Investing commits: `3b4ec1e`, `078451a`, `52085f4`, `cd32a83`,
`665b5d2`, `4b4267b`, `dbbc028`, `b22fe3a` (introduced or still contained it)
and `bbb2801`, `5137135` (the forward scrub that removed it).

Verification that HEAD is clean in both:

```bash
# <SEC_CONTACT_EMAIL> is the real address, substituted locally and never
# written to a tracked file:
$ git grep -c "$SEC_CONTACT_EMAIL" HEAD         # no output in either repo
```

The only remaining copies on disk are the git-ignored `.env` files, which is
where the SEC contact is supposed to live.

## Why skip

Costs of the rewrite:

1. **Every hash from `3b4ec1e` (FDB: from `3537f0b`) onward changes** — in
   Value Investing that is five months of history, hundreds of commits.
2. **Force-push required** (`--force-with-lease`), which rewrites published
   refs and can desynchronise a clone.
3. **Collaborators must re-clone or hard-reset.** Any uncommitted work or
   unpushed branch is at risk.
4. `filter-repo` also removes the original refs only after a gc, and the old
   objects can persist on the remote for a while — so even a "successful"
   rewrite is not a guaranteed erasure, only an obfuscation.
5. Commit signatures (if any) and any references to old hashes in issues,
   notes or documentation would break.

Benefits: the literal disappears from the private history of two private
repositories, where it is readable only by someone who already has access to
the code and the `.env` that legitimately contains it.

**Verdict: the benefit does not justify the cost.** The exposure was already
contained by repository visibility, and the forward scrub removed it from
every checked-out state.

## If you ever decide to proceed anyway

Only if the repositories become public, or if you want the history scrubbed
for hygiene reasons and are the only collaborator.

```bash
# SEC_CONTACT_EMAIL holds the real address; export it in your shell,
# never in a tracked file or in a commit message.

# 1. Safety first: everything is pushed, the tree is clean, and you have a
#    full backup or a fresh clone of both repositories elsewhere.
git status --short          # must be empty
git log --oneline origin/main..HEAD   # must be empty (nothing unpushed)
git clone --mirror git@github.com:JdeJusto/Value_Investing.git /tmp/backup-vi.git

# 2. Rewrite (rewrites ALL refs, hence the backup above)
cd /path/to/Value_Investing
git filter-repo --replace-text <(printf '%s==><your-e-mail>\n' "$SEC_CONTACT_EMAIL")
# same for Financial-DataBase

# 3. Only then push, and only with the lease guard
git push --force-with-lease origin main
# For the other branches/tags, list them first and repeat deliberately:
#   git for-each-ref --format='%(refname)' refs/heads refs/tags

# 4. Verify
git grep -c "$SEC_CONTACT_EMAIL" $(git rev-list --all) | head   # expect nothing
```

Notes:

- `filter-repo` is not usually installed (`pip install git-filter-repo`).
- Replay local commits on top **before** the rewrite; afterwards, re-apply
  anything that was not pushed (that is why step 1 requires an empty
  `origin/main..HEAD`).
- Collaborators: `git fetch && git reset --hard origin/main` (or re-clone).
- Expect to do it for both repositories in the same session; doing only one
  leaves the other with the literal in its history.

## Recommendation (final)

**No rewrite.** Keep the forward scrub, which is already committed and pushed
(`bbb2801`, `5137135` in Value Investing; `1662dbe` in Financial-DataBase).
Re-evaluate this document only if a repository is made public — at that point
the rewrite becomes worthwhile, and this file holds the exact commands.
