# CI Security Pipeline

> Files prepared in Phase S1.2. Activates the moment this repo is pushed
> to GitHub. Until then they are inert.

## Activation steps

```bash
cd /Users/bhagath/DM_Tool/ai-cmo
git init
git add .
git commit -m "Initial commit"

# Install pre-commit hooks locally (catches secrets BEFORE commit)
pip install pre-commit
pre-commit install
pre-commit run --all-files   # one-time scan of the existing tree

# Push to GitHub — workflow runs automatically
gh repo create dm-tool/ai-cmo --private --source=. --remote=origin --push
```

## What runs on every PR

| Check | Tool | Fail-on |
|---|---|---|
| Committed secrets | `gitleaks` | any rule match |
| Python CVEs | `pip-audit` | any known CVE in `uv.lock` |
| Node CVEs | `pnpm audit` | high+ severity |
| Python static security | `bandit -ll` | medium+ |
| Multi-lang OWASP | `semgrep p/owasp-top-ten` | ERROR severity |
| Tenant isolation | `pytest tests/tenancy/` | any failure |

Daily `cron: "0 3 * * *"` sweep re-runs the dependency audits against
unchanged manifests — catches newly disclosed CVEs.

## What does NOT block the build

- High-severity (not critical) Semgrep findings → warn only. Escalate
  to ERROR severity in `.semgrepignore` only when a finding is confirmed
  a false positive.
- New low-severity Node advisories → recorded in `pnpm audit` output but
  don't fail. Triage in the next sprint.

## Adding a new check

1. Add a job to `.github/workflows/security.yml`.
2. Set `continue-on-error: true` for the first week so it warms up
   without blocking PRs.
3. Once green for a week, set `continue-on-error: false`.

## Suppressing a false positive

- **gitleaks**: add the file path or regex to `allowlist` in `.gitleaks.toml`.
- **bandit**: add `# nosec B<id> — <reason>` inline.
- **semgrep**: add the rule id to `.semgrepignore` with a comment.

Never blanket-suppress an entire rule.
