---
description: Full job-search run. Fetch, rank, write the shortlist, then CV review, tailored CVs and outreach drafts.
argument-hint: "[skip-cv] [skip-outreach]"
---

You are my job-search agent. Today is the run date (use `date +%F`). Read `config/profile.toml` first:
it holds my target roles, level, graduation/start dates, accepted regions, work rights per region (and the
`notes` about my visa situation), filters, and the companies I've already applied to. My CV is `cv/cv.tex`.
If `config/profile.toml` doesn't exist, stop and tell me to run `/onboard` first.

Arguments: $ARGUMENTS. "skip-cv" skips steps 3–4 and "skip-outreach" skips step 5.

## 1. Collect
1. Run `python3 -m jobagent run --dry-run`. It writes `data/candidates/<date>.json` (new roles only, already
   filtered and heuristically scored) and `data/source_status.json`. Tell me in one line about any failed sources.
2. For every `[[watch]]` entry in `config/companies.toml`, use WebSearch (and WebFetch for the URL) to find
   current roles at my level (from the profile) that are open now. Use only real postings with a working link.
   Never make up a role, deadline or sponsorship status. If a field is unknown, write "not stated".
3. Discovery (companies NOT in the config): the fetcher already includes freehire.me (an aggregator of
   ~185k companies, startups included). In candidates.json those rows have `"new_company": true`. Also run
   3–4 WebSearch queries for job boards that suit my field and regions (e.g. UK graduates: TARGETjobs,
   Bright Network, Gradcracker; Europe: Welcome to the Jungle; startups: YC Work at a Startup, Wellfound),
   built from my role families, level, start date and preferred cities.
   If a good company keeps appearing and has a Greenhouse/Lever/Ashby URL, suggest adding it to
   `config/companies.toml` in your final report (don't edit the config without asking).
4. For roles found by web search (not from the fetcher), WebFetch the posting to confirm it's still open.
   Drop it if it's closed or the page is gone.
5. Drop anything already in `seen_jobs.json` (same company + same role title).

## 2. Rank and write the shortlist
Apply these rules strictly:
- Exclude: more experience than `[filters].max_years_experience`, the excluded title words, PhD-only roles
  (if `[filters].phd = "exclude_phd_only"`), closed deadlines, internships the profile excludes, locations
  outside `[regions].accept`, and roles in a `needs_sponsorship` region whose DESCRIPTION explicitly says
  there is no visa sponsorship.
- Sponsorship not stated, mixed, or only "must have the right to work": KEEP the role, don't rank it lower,
  and write the status as stated ("Not stated", "Mixed: check", "asks for right to work: check").
- Use `[work_rights].notes` to flag visa issues (e.g. a programme longer than my post-study visa).
- Rank by: fit to my CV and target role families > start-date fit (my `earliest_start`) > sponsorship
  explicitly offered (only matters where I need it) > company quality (`dream_companies`, then tiers).
- Keep roles at companies in `already_applied`, but label them "already applied".

Write `shortlist/<date>.md` in the same format as earlier shortlist files: a table with title, company,
location, link, deadline, sponsorship status and a one-line reason it fits. Start that reason with a fit score
like "4/5:", and mark companies not in our config with "(new)". Add one `<!-- id: ... -->` line
per role. Top 15. Then run `python3 -m jobagent mark shortlist/<date>.md`.

## 3. CV review → run `/cv-review` steps (unless skip-cv)
## 4. Tailored CVs → part of `/cv-review`
## 5. Outreach → run `/outreach` steps (unless skip-outreach)

## 6. Report back (keep it short)
Show the shortlist table, the outreach drafts, the CV diff (`git diff HEAD..cv-edits -- cv/cv.tex`) and the
list of tailored files. End with: what to tune in `config/`, and the top 3 CV changes.
Ask me for any missing metrics; don't guess them.
