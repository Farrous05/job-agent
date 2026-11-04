---
description: Full job-search run. Fetch everything, Claude scores every matching role, shortlist, recall check, CV work, outreach.
argument-hint: "[skip-cv] [skip-outreach] [skip-linkedin] [skip-recall]"
---

You are my job-search agent. Today is the run date (use `date +%F`). Read `config/profile.toml` first:
targets, filters, work rights, languages, city tiers, and the companies I've already applied to.
My CV is `cv/cv.tex`. Arguments: $ARGUMENTS (each "skip-…" skips that step).
Do ALL steps in one go, in order, without stopping to ask me (ask only if something blocks you). Roles added
late (LinkedIn, recall) just need one more `batches` → score → `merge-scores` pass: do it, it's cheap
because existing scores are cached.

Everything goes through ONE pipeline in `data/runs/<today>/` so nothing is judged twice or missed:
fetch → import extra finds → Claude scores every role → merge into shortlist + All matches.

## 1. Fetch (2–3 min)
Run `python3 -m jobagent run --dry-run`. It fetches all company boards + freehire (+ Reed), applies my
filters, drops roles I've already been shown, and writes ALL remaining roles to
`data/runs/<today>/candidates.json`. Tell me in one line: jobs fetched, roles kept, failed sources.

## 2. Add what the feeds miss
1. **Watch list:** for every `[[watch]]` company in `config/companies.toml`, WebSearch (and WebFetch the URL)
   for roles at my level that are open now. **Boards:** 3–4 WebSearch queries for job boards that suit me
   (TARGETjobs, Bright Network, Gradcracker, Welcome to the Jungle, YC Work at a Startup), built from my
   role families, start date and cities. Only real postings with a working link; WebFetch each one to
   confirm it's still open and copy ~1,500 characters of its description and any deadline.
   Never invent a role, deadline or sponsorship status.
   Save them as a JSON list to `data/runs/<today>/imported/web.json`
   (`[{"source": "web", "company", "title", "location", "url", "description", "deadline"}]`), then run
   `python3 -m jobagent import data/runs/<today>/imported/web.json`.
2. **LinkedIn jobs** (unless skip-linkedin, and only if Chrome is connected): follow `/linkedin-jobs`.
   If Chrome isn't connected, say so in one line and continue.

## 3. Score every role (the important part)
1. Run `python3 -m jobagent batches` (add `--rescore` only if I ask to redo old scores). It writes `data/runs/<today>/batches/batch-NNN.md` for every role that
   has no score yet (scores are cached, so later runs only score new roles).
2. Score EVERY batch. Each file says exactly what to write: one JSON line per role to
   `data/runs/<today>/scores/batch-NNN.jsonl` with `fit` 1–5, a concrete one-line `reason`, `deadline`,
   `start`, `concerns`. Read `cv/cv.tex` and `config/profile.toml` once first.
   To go faster, use the Task tool to score up to 4 batches in parallel (give each subagent the batch path,
   `cv/cv.tex` and `config/profile.toml`, and the instruction to write only the JSONL file). Tell each
   subagent: read each role's WHOLE excerpt (up to 2,000 characters), not just the first lines; read the batch
   file in full (use several Read calls with offsets if needed); never score from the title alone when an
   excerpt exists.
   How to judge: my CV and target roles first; then level (graduate/junior, no 3+ years), start date vs
   my graduation (Sept 2027) and student-visa limits on internships; language of the job; city size;
   company quality. Roles I marked "not_interested" in `seen_jobs.json` show what I don't want: score similar
   roles lower. Companies I've applied to (`status` applied/interviewing/offer/rejected) count as already applied.
3. Run `python3 -m jobagent merge-scores`. It writes `data/runs/<today>/matches.json` (all scored roles, the
   job page's "All matches" tab) and `shortlist/<today>[-runN].md` (top 15 with fit ≥ 3), and marks those as
   shown. If it reports unscored roles or problems in score files, fix them and run it again.

## 4. Recall check (unless skip-recall)
Find 10–20 real, currently open postings that SHOULD match me, from sources other than our feeds
(Gradcracker, Bright Network, TARGETjobs, LinkedIn if connected), for my target roles and cities.
Save them to `data/runs/<today>/recall.json` (`[{"company", "title", "url", "location"}]`) and run
`python3 -m jobagent recall data/runs/<today>/recall.json`. Read `recall_report.md`:
- "filtered out": check the reason. If a filter is wrong, say which setting to change.
- "missing": if the company has a Greenhouse/Lever/Ashby/Workday board, propose adding it to
  `config/companies.toml` (don't edit the config without asking).
Recall postings that fit me can be imported (step 2) and scored too.

**Filter audit:** run `python3 -m jobagent audit`. It lists up to 40 roles the filters REMOVED that look
relevant. Read `data/runs/<today>/audit.md`, follow its instructions, and report any wrong removals with the
setting to change. Wrongly removed roles that fit me can be imported (step 2) and scored.

## 5. CV → follow `/cv-review` (unless skip-cv)
## 6. Outreach → follow `/outreach` (unless skip-outreach)

## 7. Report back (keep it short)
- Counts: fetched, kept, scored (new vs cached), shortlisted; recall % (this run and all runs) and the misses
  that matter; filter-audit findings.
- The shortlist table (title, company, city, deadline, fit, one-line reason).
- Output of `python3 -m jobagent reminders` (deadlines closing soon, follow-ups due).
- CV changes (`scripts/cv_diff.sh --text`), tailored files, outreach file.
- Tell me to open the job page in my own terminal: `python3 -m jobagent view` (don't start it yourself: it
  runs until Ctrl+C; use `python3 -m jobagent view --static` to just refresh the HTML files).
- For the top 3 roles, suggest `/apply <company>` to draft the cover letter and answers.
- What to tune in `config/`, and any questions (never guess missing facts).
