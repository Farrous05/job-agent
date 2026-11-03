---
description: Set up the job agent for a new person. Interviews them, writes config/profile.toml and sets up their CV.
---

You're setting up this job-search agent for the person in front of you. Interview them, then write
`config/profile.toml` (use `config/profile.example.toml` as the schema) and set up their CV.
Re-running `/onboard` updates an existing profile: show what's there and ask what to change.

## How to interview
- Ask **one short group of questions at a time** (max 3 questions per message), in plain language, and wait
  for the answer. Use AskUserQuestion with options where the answer is a choice.
- Never guess facts about them. If an answer is unclear, ask again. "Skip" is fine for optional items.
- Read their CV first (step 1) and pre-fill what you can, then ask them to **confirm** rather than retype.

## 1. CV (first)
Ask for the path to their CV.
- `.tex`: copy it to `cv/cv.tex` unchanged.
- `.pdf`: extract the text with `pdftotext -layout <file> -`. For `.docx`, `.doc` or `.rtf` on macOS use
  `textutil -convert txt -stdout <file>`. For `.md` or `.txt`, read it directly.
  Then build `cv/cv.tex` from `cv/template.tex` using ONLY content from their CV: same jobs, dates, bullets
  and skills, wording kept. Compile it with `scripts/build_cv.sh cv/cv.tex` and ask them to check the PDF
  (`cv/build/cv.pdf`) against their original. Never add, improve or invent anything at this step.
- Keep a copy of the original in `cv/original/`.

## 2. Questions (pre-fill from the CV where possible)
1. **Basics:** name, current/last degree, school(s), graduation date (or "already graduated"), city they live in,
   and the languages they can work in (ISO codes, e.g. en, fr, de).
2. **Target roles:** which job types (e.g. ML engineer, data analyst, product manager, nurse, accountant)?
   Level: graduate/entry, junior (1–2 yrs) or mid (3–5 yrs)? Max years of experience a posting may ask for?
3. **Start date:** earliest date they can start.
4. **Locations:** which regions from `config/regions.toml` (UK, EU/EEA/CH, US, Canada, Australia/NZ, Singapore,
   UAE)? Preferred cities (ranked highest; then each region's big hubs, then other major cities, then the
   rest)? OK with remote roles?
5. **Work rights, per accepted region:** "Can you work there without visa sponsorship?" → `free` or
   `needs_sponsorship`. Ask for anything relevant for the notes (visa type, post-study visa and its length,
   hours limits). Explain: a role is removed only if its description explicitly says it won't sponsor.
6. **Internships:** wanted? Any timing they must avoid (e.g. summer during a master's on a student visa)?
7. **PhD:** exclude PhD-only roles (default) or keep everything?
8. **Companies:** any already applied to (they stay listed, marked "already applied")? Dream companies?
   Companies to never show?
9. **Outreach:** do they want LinkedIn outreach drafts? Which schools should alumni matching prefer?
   (Needs Claude in Chrome and a signed-in LinkedIn. View-only, nothing is ever sent.)

## 3. Write the profile
- `[roles].families`: one entry per target role type with a title regex (case-insensitive) and a weight
  (their top priority 10, others 6–8). Test each pattern against 3–4 realistic titles before saving.
- `[roles].cv_keywords`: 15–40 lower-case skills and tools taken from THEIR CV only.
- `[filters].exclude_title_words`: start from the example; drop words that are actually their target
  (e.g. keep "manager" if they want manager roles; remove "consultant" if they want consulting).
  Add "never show" companies as exact phrases only if they ask.
- `[freehire].queries`: 3–5 queries for their role types, **max 5 OR alternatives per query** (API limit),
  `seniority` from ["intern", "junior", "middle", "senior"] matching their level. Include one query with
  `graduate OR "new grad" OR "early careers" OR "<grad year>"` if they're graduating.
- `[reed].queries`: only if they accept the UK; 3–4 short keyword phrases.
- `[ranking]` tiers: keep the example lists for tech roles; for other fields, ask for 5–10 respected employers.
- If their field isn't tech/finance, suggest companies whose job boards should go into `config/companies.toml`
  (Greenhouse/Lever/Ashby/Workday slugs, verified with a quick fetch). Ask before editing it.

## 4. Check it works
1. `python3 -m unittest discover tests`
2. `python3 -m jobagent run --dry-run` and show them the top 10 titles from `data/candidates/<date>.json`.
   Ask "Do these look like your kind of roles?" and adjust families, keywords or exclusions until they say yes.
3. Make sure `seen_jobs.json` exists (`{"jobs": {}}`).

## 5. Tell them how to use it (short)
- Full run: `claude --chrome` then `/job-run` (or `/job-run skip-outreach`).
- Daily free fetch: the launchd/cron steps in README.md.
- CV edits always go on branch `cv-edits` and need their approval.
