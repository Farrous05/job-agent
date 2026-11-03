# job-agent

**New here? Read [HOW_TO_USE.md](HOW_TO_USE.md).** Your jobs are in `shortlist/LATEST.html` (open it in a browser).

A local job-search agent for graduate ML/AI, data science, quant and SWE roles starting autumn 2027.
Why it's built this way: see [RESEARCH.md](RESEARCH.md).

**How it works**
1. `python3 -m jobagent run` fetches public ATS feeds (Greenhouse, Lever, Ashby, Workday) for the companies in
   `config/companies.toml`, plus freehire.me (free aggregator, ~185k companies incl. startups) and Reed (if
   `REED_API_KEY` is set). It filters them with your rules in `config/profile.toml`, reads each description for an explicit
   sponsorship statement, skips anything in `seen_jobs.json` and writes `shortlist/YYYY-MM-DD.md`.
   No LLM, free, safe to schedule.
2. `/job-run` inside Claude Code does the judgement work. It runs the fetcher, checks company pages and UK grad
   boards by web search, ranks the roles, reviews the CV (`/cv-review`) and drafts LinkedIn notes (`/outreach`).

```
config/profile.toml      your filters, targets, already-applied list
config/companies.toml    ATS boards + [[watch]] companies checked by web search
jobagent/                fetcher, filters, seen store (Python stdlib only)
seen_jobs.json           every job already reported (reruns show only new ones)
shortlist/DATE.md        top 15 per run
outreach/DATE.md         people + draft connection notes (you send them)
cv/cv.tex                master CV (edited only on branch cv-edits, merged by you)
cv/tailored/*.tex        per-role versions; cv/build/ holds PDFs
cv/cv_feedback.md        CV review summary + questions for you
.claude/commands/        /job-run, /cv-review, /outreach
scripts/                 build_cv.sh, run_scheduled.sh, launchd plist
```

## Setup (macOS; Linux is the same minus launchd)

1. **Clone and check Python 3.11+** (no packages needed):
   ```bash
   git clone https://github.com/Farrous05/job-agent.git ~/job-agent
   ```
   ```bash
   cd ~/job-agent && python3 --version && python3 -m unittest discover tests
   ```
2. **LaTeX** (for compiling CVs). On macOS:
   ```bash
   brew install --cask mactex-no-gui
   ```
   You also need `pdfinfo`:
   ```bash
   brew install poppler
   ```
3. **Claude Code**: install it, then sign in with your Claude account (no API key needed):
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```
4. **Claude in Chrome** (outreach only): install the Claude extension in Chrome, sign in to the same Claude
   account and sign in to LinkedIn in that Chrome. Then start Claude with `claude --chrome`, or run `/chrome`
   inside a session.
5. **Optional: Reed API** (adds a UK aggregator). Get a free key at https://www.reed.co.uk/developers/jobseeker,
   then add it to `~/.zshrc`:
   ```bash
   echo 'export REED_API_KEY=your_key_here' >> ~/.zshrc
   ```
6. **Optional: fewer permission prompts.** Save this as `.claude/settings.json` (I couldn't write it from the cloud session):
   ```json
   {"permissions": {"allow": ["Bash(python3 -m jobagent:*)", "Bash(scripts/build_cv.sh:*)", "Bash(git diff:*)",
     "Bash(date:*)", "WebSearch", "WebFetch"], "deny": ["Bash(git merge:*)"]}}
   ```

## First run on your laptop
```bash
python3 -m jobagent run --dry-run && python3 -m jobagent status
```
`status` lists the boards that failed. Some tokens in `config/companies.toml` are marked `verified = false`.
For each failure, open the company's careers page, copy the slug from the job URL (for example
`job-boards.greenhouse.io/<slug>`) and fix it, or delete the entry.

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

## Scheduling locally (launchd)
```bash
sed "s#REPO_PATH#$HOME/job-agent#" scripts/com.fares.jobagent.plist > ~/Library/LaunchAgents/com.fares.jobagent.plist
```
```bash
launchctl load ~/Library/LaunchAgents/com.fares.jobagent.plist
```
It runs daily at 08:40, or at next wake if the laptop was asleep. Logs go to `data/logs/`.
- `JOBAGENT_MODE=script` (default in the plist): fetcher only, £0.
- `JOBAGENT_MODE=claude`: headless `claude -p` runs `/job-run skip-cv skip-outreach` using your Claude plan.
- Outreach is **never** scheduled. LinkedIn browsing stays interactive and supervised.
- To stop it:
  ```bash
  launchctl unload ~/Library/LaunchAgents/com.fares.jobagent.plist
  ```
- Cron alternative:
  ```bash
  (crontab -l; echo "40 8 * * * $HOME/job-agent/scripts/run_scheduled.sh") | crontab -
  ```

Choose one mode. Both mark shortlisted jobs as seen, so running both on the same day splits the new roles between them.

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
