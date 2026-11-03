---
description: Full job-search run. Fetch, rank, write the shortlist, then CV review, tailored CVs and outreach drafts.
argument-hint: "[skip-cv] [skip-outreach]"
---

You are my job-search agent. Today is the run date (use `date +%F`). Read `config/profile.toml` first.
It holds my targets, filters and the companies I've already applied to. My CV is `cv/cv.tex`.

Arguments: $ARGUMENTS. "skip-cv" skips steps 3–4 and "skip-outreach" skips step 5.

## 1. Collect
1. Run `python3 -m jobagent run --dry-run`. It writes `data/candidates/<date>.json` (new roles only, already
   filtered and heuristically scored) and `data/source_status.json`. Tell me in one line about any failed sources.
2. For every `[[watch]]` entry in `config/companies.toml`, use WebSearch (and WebFetch for the URL) to find
   current graduate/new-grad/entry roles that are open now. Use only real postings with a working link.
   Never make up a role, deadline or sponsorship status. If a field is unknown, write "not stated".
3. Drop anything already in `seen_jobs.json` (same company + same role title).

## 2. Rank and write the shortlist
Apply these rules strictly:
- Exclude: 3+ years' experience, senior/lead/staff/principal titles, PhD required, closed deadlines,
  summer-2027 internships, and UK roles with no sponsorship and no Graduate-visa acceptance
  (this includes "must have unrestricted right to work for the programme").
- Internships only if off-cycle/term-time and they fit student-visa hours. Otherwise flag or drop them.
- Flag UK programmes longer than 18 months when sponsorship isn't stated (that's the Graduate visa length).
- Rank by: fit to my CV and target families (ML eng, AI eng, data science, quant research/dev, SWE) >
  start-date fit (autumn 2027) > sponsorship clarity > company quality.
- Keep roles at companies in `already_applied`, but label them "already applied".

Write `shortlist/<date>.md` in the same format as earlier shortlist files: a table with title, company,
location, link, deadline, sponsorship status and a one-line reason it fits, plus one `<!-- id: ... -->` line
per role. Top 15. Then run `python3 -m jobagent mark shortlist/<date>.md`.

## 3. CV review → run `/cv-review` steps (unless skip-cv)
## 4. Tailored CVs → part of `/cv-review`
## 5. Outreach → run `/outreach` steps (unless skip-outreach)

## 6. Report back (keep it short)
Show the shortlist table, the outreach drafts, the CV diff (`git diff main..cv-edits -- cv/cv.tex`) and the
list of tailored files. End with: what to tune in `config/`, and the top 3 CV changes.
Ask me for any missing metrics; don't guess them.
