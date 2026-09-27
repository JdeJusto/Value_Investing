# History rewrite recommendation — for the public release

**Recommendation: Option B — accept the e-mail in the history. Do not
rewrite.** Nothing destructive was executed while writing this: no
`git filter-repo`, no `rebase`, no `--force`.

The decision is yours to make; this document gives the matrix, the
recommendation and the exact commands for each option so you can execute it
when you decide to.

## The facts this recommendation rests on

| Fact | Value |
| --- | --- |
| Repositories are currently **private** (anonymous `curl` → HTTP 404) | both |
| Personal e-mail in Value_Investing history | 71 lines, first in `3b4ec1e` (2026-04-26) |
| Personal e-mail in Financial-DataBase history | 4 lines, all in `3537f0b` (2026-09-27) |
| Personal e-mail in either **HEAD** | **0** (forward-scrubbed) |
| Total commits, Value_Investing | ~120 (five months) |
| Total commits, Financial-DataBase | 3 |
| Other author identities in history | `jdejusto@example.com`, `jdejusto@localhost`, **`noreply@anthropic.com`** (FDB) |
| Forks / collaborators | none known (the repositories have been private) |

## Option matrix

| | **A. Rewrite everything** (`filter-repo`) | **B. Accept** (recommended) | **C. Rewrite only the offending commits** |
| --- | --- | --- | --- |
| E-mail out of history | yes, everywhere | no (stays in old commits) | no, unless the rewrite covers every commit that contains it |
| Hashes rewritten | **all**, from `3b4ec1e` (Apr) in VI; from `3537f0b` in FDB | none | from the earliest offending commit onward |
| Force-push | required | not required | required |
| Cost of a mistake | high (lost commits if the backup is wrong) | none | medium |
| Collaborator action | re-clone or hard reset | none | re-clone or hard reset |
| GitHub caches | old objects can stay reachable for a while | n/a | same as A |
| Reversible | no | n/a | no |
| Fixes `noreply@anthropic.com` | yes | no | no |
| Time cost | ~15 min plus verification, twice | 0 | more than A, and messier |

**The asymmetry that decides it:** the e-mail is already the identity
associated with the GitHub account, so the marginal exposure of publishing
the history is small — anyone who sees a commit knows who wrote it, and the
account itself is the strongest signal. A rewrite, by contrast, rewrites
five months of hashes in a repository with real history, and a botched
rewrite is unrecoverable without a backup.

**What would change this recommendation:** if the e-mail were not the
account identity, if the repository were forked or mirrored elsewhere before
the rewrite, or if the address were shared with someone who has not consented
to it being public. In that case Option A becomes the right call, and Option C
is not enough because the string appears in many non-adjacent commits.

## If you choose A: the exact sequence

Mandatory first step — a full mirror backup. Do not skip it.

```bash
# 0. Back up BOTH repositories as mirrors (fast, complete, recoverable)
git clone --mirror git@github.com:JdeJusto/Value_Investing.git    /tmp/backup-Value_Investing.git
git clone --mirror git@github.com:JdeJusto/Financial-DataBase.git /tmp/backup-Financial-DataBase.git

# 1. Preconditions: nothing unpushed, clean tree
cd ~/Value_Investing        && git status --short && git log --oneline origin/main..HEAD
cd ~/Financial-DataBase     && git status --short && git log --oneline origin/main..HEAD
# both commands must print nothing

# 2. Install the tool (once)
pip install git-filter-repo

# 3. Rewrite, one repository at a time. Substitute the address locally;
#    do NOT type it into a tracked file or a commit message.
export SEC_CONTACT_EMAIL='the-real-address'      # shell only
cd ~/Value_Investing
git filter-repo --replace-text <(printf '%s==><your-e-mail>\n' "$SEC_CONTACT_EMAIL")
cd ~/Financial-DataBase
git filter-repo --replace-text <(printf '%s==><your-e-mail>\n' "$SEC_CONTACT_EMAIL")

# 4. Verify before pushing anything
for repo in ~/Value_Investing ~/Financial-DataBase; do
  (cd "$repo" && git log --all -S "$SEC_CONTACT_EMAIL" --oneline | head)   # expect nothing
done
grep -rl "$SEC_CONTACT_EMAIL" ~/Value_Investing ~/Financial-DataBase \
  --exclude-dir=.git --exclude=.env                                  # expect only .env

# 5. Push (lease-protected; if it is rejected, STOP and investigate)
cd ~/Value_Investing    && git push --force-with-lease origin main
cd ~/Financial-DataBase && git push --force-with-lease origin main

# 6. GitHub: ask support to drop cached views of the old objects if the
#    address is still reachable through a commit permalink.
```

Recovery if step 5 goes wrong:

```bash
cd ~/Value_Investing
git push --force origin refs/remotes/origin/main:refs/heads/main   # from the backup clone
```

## Do NOT forget

- **The mirror backup is mandatory** (`git clone --mirror … .git.bak`). A
  rewrite without one is unrecoverable.
- Do both repositories in the same session; rewriting only one leaves the
  other with the string in its history.
- Any fork or clone made before the rewrite keeps the old history and must be
  re-cloned.
- A rewrite also removes `noreply@anthropic.com` from the author metadata of
  the commits that used it. Decide whether you want that too.

## What to do on the day you publish

1. Set the account-wide commit identity so nothing personal leaks again:
   `git config --global user.email jdejusto@users.noreply.github.com`.
2. Add a `SECURITY.md` contact address (the shipped file has a
   `<your-e-mail>` placeholder that must be replaced in the commit, not in a
   later private edit).
3. Confirm `git grep -i "<address>" HEAD` is empty in both repositories.
4. If you took Option B, optionally add one line to the README stating that
   the history predates the email scrub — it saves a future reader the
   archaeology.
