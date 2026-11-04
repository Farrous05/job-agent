# job-agent

**New here? Read [HOW_TO_USE.md](HOW_TO_USE.md).** Set up once with `scripts/install_mac.sh`: a daily run, a Telegram bot (your phone remote) and an always-on job page. Your jobs are in `shortlist/LATEST.html` (open it in a browser).

A local job-search agent for graduate ML/AI, data science, quant and SWE roles starting autumn 2027.
Why it's built this way: see [RESEARCH.md](RESEARCH.md).

**How it works**
1. `python3 -m jobagent run --dry-run` fetches ~9,000 jobs: company boards (Greenhouse, Lever, Ashby, Workday),
   freehire.me (search terms + every role at watch-list firms) and Reed. It applies your filters and writes
   **every** remaining role to `data/runs/<date>/candidates.json`.
2. `/job-run` in Claude Code adds web-search and LinkedIn finds (`jobagent import`), then **Claude scores every
   role 1–5 against your CV** (`jobagent batches` → score files → `jobagent merge-scores`; scores are cached).
   Then it writes the top 15, runs a recall check against known postings, does CV work and outreach drafts.
3. `python3 -m jobagent view` is the job page: Top picks, All matches, My applications (stages and notes), Stats.
4. `/apply <company>` drafts the cover letter and form answers. You submit.

```
config/profile.toml      your filters, targets, already-applied list
config/companies.toml    ATS boards + [[watch]] companies checked by web search
jobagent/                sources, filters, pipeline (score/merge/recall), tracker, job page (stdlib only)
data/runs/DATE/          candidates, scoring batches + scores, matches, recall report (local only)
seen_jobs.json           every job already reported (reruns show only new ones)
shortlist/DATE.md        top 15 per run
outreach/DATE.md         people + draft connection notes (you send them)
cv/cv.tex                master CV (edited only on branch cv-edits, merged by you)
cv/tailored/*.tex        per-role versions; cv/build/ holds PDFs
cv/cv_feedback.md        CV review summary + questions for you
.claude/commands/        /job-run, /cv-review, /outreach, /linkedin-jobs, /apply
applications/            drafted cover letters and answers per role
scripts/                 build_cv.sh, run_scheduled.sh, launchd plist
```

## Setup
Step by step, from a fresh Mac: **[HOW_TO_USE.md → Set up once](HOW_TO_USE.md#set-up-once-about-30-minutes-most-of-it-downloads)**.
In short: Homebrew → `brew install python git gh poppler` + MacTeX → `gh auth login` → Claude Code → clone →
`notify-setup --telegram` → `scripts/install_mac.sh`.

## Running it
- **Full agent run** (interactive, about 10–20 min):
  ```bash
  claude --chrome
  ```
  Then type `/job-run`, or `/job-run skip-outreach`.
- **Just the fetcher** (free): `python3 -m jobagent run`
- **Just CV work:** `/cv-review` · **Just outreach:** `/outreach`
- **Mark a hand-edited shortlist as seen:** `python3 -m jobagent mark shortlist/2026-11-03.md`
- **Compile CVs and check one page:** `scripts/build_cv.sh`
- **See suggested CV changes (red/blue PDF):** `scripts/cv_diff.sh`

## Scheduling
`scripts/install_mac.sh` installs the daily 08:40 run (Claude mode), the Telegram bot and the always-on job page
as launchd agents. Logs: `data/logs/`. Remove them: `scripts/install_mac.sh --uninstall`.
Outreach is **never** scheduled: LinkedIn browsing stays interactive and supervised.

## CV workflow (you approve everything)
- General edits live on branch **`cv-edits`**. Review them:
  ```bash
  git diff main..cv-edits -- cv/cv.tex
  ```
  Merge only when you're happy:
  ```bash
  git checkout main && git merge cv-edits
  ```
- Tailored versions in `cv/tailored/` start with a `% TAILORING:` comment listing their 2–3 tweaks.
- Claude never invents metrics. Open questions are listed in `cv/cv_feedback.md`.

## Tuning
- `config/profile.toml`: title exclusions, max years, family weights, company tiers, shortlist size.
- `config/companies.toml`: add boards (`[[board]]`) or web-checked companies (`[[watch]]`).
- Mark a job `"status": "applied"` or `"dismissed"` in `seen_jobs.json` to keep your own record.
