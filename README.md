# job-agent

A local job-search agent you run on your own laptop with Claude Code. It finds roles that fit **your** CV and
rules, remembers what it already showed you, tailors your CV per role (you approve every change), and drafts
LinkedIn notes (you send them). It never applies, sends or clicks Connect.

**How it works**
1. `python3 -m jobagent run` fetches jobs. It reads public company job boards (Greenhouse, Lever, Ashby,
   Workday) for the employers in `config/companies.toml`, plus freehire.me (a free aggregator covering about
   185,000 companies, startups included) and Reed (UK, optional key). It filters with the rules in your
   `config/profile.toml`, skips anything in `seen_jobs.json` and ranks the rest. No LLM, free, safe to schedule.
2. `/job-run` in Claude Code does the judgement work. It searches companies with no feed, checks postings are
   still open, ranks with a 1–5 fit score, reviews your CV (`/cv-review`) and drafts outreach (`/outreach`).

```
config/profile.toml      YOUR settings: written by /onboard (schema: profile.example.toml)
config/regions.toml      region presets (UK, EU/EEA/CH, US, Canada, ...): edit to add cities
config/companies.toml    company job boards + [[watch]] companies checked by web search
jobagent/                fetcher, filters, seen store (Python stdlib only)
seen_jobs.json           every job already shown to you
shortlist/DATE.md        top roles per run
outreach/DATE.md         people + draft notes (you send them)
cv/cv.tex                your master CV (changed only on branch cv-edits, merged by you)
cv/tailored/*.tex        per-role versions; PDFs in cv/build/
.claude/commands/        /onboard, /job-run, /cv-review, /outreach
```

> Your CV and profile live in this repo. If you fork it, keep the fork **private**.

## Setup (macOS; Linux is the same minus Homebrew/launchd)

1. **Get the code** (Python 3.11+, no packages needed):
   ```bash
   git clone https://github.com/Farrous05/job-agent.git ~/job-agent
   ```
2. **Install LaTeX** (to build CV PDFs) and `pdfinfo`. The small option is BasicTeX:
   ```bash
   brew install --cask basictex && brew install poppler
   ```
   ```bash
   eval "$(/usr/libexec/path_helper)" && sudo tlmgr update --self && sudo tlmgr install titlesec enumitem xurl
   ```
   Or install the full `mactex-no-gui` (about 5 GB) instead of BasicTeX.
3. **Install Claude Code** and sign in with your Claude account (no API key needed):
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```
4. **For outreach only:** install the Claude in Chrome extension, sign in to Claude and LinkedIn in Chrome.
5. **Optional, UK jobs:** get a free Reed key at https://www.reed.co.uk/developers/jobseeker, then:
   ```bash
   echo 'export REED_API_KEY=your_key' >> ~/.zshrc
   ```

## First time: onboarding (about 15 minutes)
```bash
cd ~/job-agent && claude
```
Type `/onboard`. Claude will:
- read your CV (`.tex`, `.pdf`, `.docx` or `.txt`) and turn it into `cv/cv.tex` if needed (you check it);
- ask about your target roles, level, dates, regions, work rights and visa situation, internships,
  companies you've applied to, and outreach;
- write `config/profile.toml`, then do a test fetch and adjust until the roles look right to you.

## Running it
Every run starts from the repo folder (not a subfolder):
```bash
cd ~/job-agent && claude --chrome
```
Then type one of:
- `/job-run`: shortlist, CV suggestions, tailored CVs and outreach drafts (about 15–25 min).
- `/job-run skip-outreach` or `/job-run skip-cv`: the same minus that step.
- `/cv-review` or `/outreach`: just that step, on the latest shortlist.

Other commands:
- **Free fetch, no Claude:** `python3 -m jobagent run` (writes a keyword-ranked shortlist).
- **What failed last time:** `python3 -m jobagent status`.
- **Build the CV PDFs and check each is one page:** `scripts/build_cv.sh`.

## Daily schedule (optional, free)
```bash
sed "s#REPO_PATH#$HOME/job-agent#" scripts/com.jobagent.plist > ~/Library/LaunchAgents/com.jobagent.plist && launchctl load ~/Library/LaunchAgents/com.jobagent.plist
```
It runs daily at 08:40, or at next wake, with logs in `data/logs/`. Outreach is never scheduled. To stop it:
```bash
launchctl unload ~/Library/LaunchAgents/com.jobagent.plist
```

## Reviewing CV changes
- See the changes:
  ```bash
  git diff HEAD..cv-edits -- cv/cv.tex
  ```
- Merge when happy:
  ```bash
  git merge cv-edits
  ```
- Claude never invents experience or numbers. It asks you in `cv/cv_feedback.md`.

## Rules the filters follow
- A role is removed for sponsorship **only** if its description explicitly says it won't sponsor, and only in
  regions where your profile says you need sponsorship. "Not stated" changes nothing.
- PhD-only roles are removed by default. "PhD or Master's" roles are kept.
- Too much experience asked, excluded title words, locations outside your regions and roles for later
  graduating classes are removed. Everything else is ranked, not removed.

## Tuning
Run `/onboard` again to change your profile, or edit `config/profile.toml` directly. Add employers to
`config/companies.toml` (`[[board]]` with an ATS slug, or `[[watch]]` for web search).
