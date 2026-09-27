---
name: Bug report
about: Something behaves differently from what the documentation says
title: "[bug] "
labels: bug
assignees: ''
---

**What happened**

<!-- What you observed, including the exact wording of any warning or error. -->

**What you expected**

**Reproduction**

```bash
# the exact command, with arguments
```

**Environment**

- Value Investing commit: `git rev-parse --short HEAD`
- Python: `python --version`
- Database: PostgreSQL `SELECT version();`
- Universe / flags used (e.g. `--universe all --limit 50 --no-prices`)

**Relevant log output**

<!--
From data/logs/daily_workflow.log, or the run's report
(data/reports/daily_<date>.md) — its `## Network` and `## Price stage`
sections usually carry the diagnosis.
DO NOT paste a .env, a connection string with a password, or any
personal e-mail.
-->

**Anything else**

<!-- Screenshots of the terminal output if they help. -->
