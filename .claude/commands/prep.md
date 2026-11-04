---
description: Interview prep pack for one role: company, likely process and questions, which of your stories to use.
argument-hint: "<company or job title or job id>"
---

Role to prepare for: $ARGUMENTS

You write an interview prep pack. You never contact anyone, apply, or send anything.

1. **Find the role.** Search `seen_jobs.json` (jobs marked interviewing first), the newest
   `data/runs/*/matches.json`, `shortlist/*.md` and `applications/*/` for $ARGUMENTS. If several match and
   you're interactive, ask which one; if you're unattended, take the one marked interviewing (else the best
   fit) and say which. WebFetch the posting URL for the full description. If it's gone, use what's saved.
2. **Read me.** `cv/cv.tex` (or the tailored `cv/tailored/<company>-<role>.tex` if one exists),
   `config/profile.toml`, and `applications/<company>-<role>/` (cover letter, answers) if I applied with them.
   The job's `note` in `seen_jobs.json` may say who I'm meeting and when.
3. **Research the company** with WebSearch / WebFetch (3–8 searches): what they do and how they make money,
   the team or product this role sits in, recent news (last 12 months), and reports of their interview
   process for this kind of role (e.g. Glassdoor, Blind, Reddit, their own careers/engineering blog).
   Say where each claim comes from. If reports conflict or are thin, say so; don't make up a process.
4. **Write `applications/<company>-<role>/interview_prep.md`** (same folder as the application if one exists;
   lower-case, hyphens). First line exactly: `<!-- job: <the job's id from seen_jobs.json or matches.json> -->`.
   Sections, short and scannable on a phone:
   - `# Interview prep: <Company>, <Role>` and one line: date, posting link.
   - `## The company in 60 seconds`: 4–6 bullets (what they do, size, team, recent news), with sources.
   - `## What they want`: their top 5 requirements from the posting, each with the CV evidence that matches
     it, or "gap" plus an honest way to address it.
   - `## Likely process`: the stages you found (with sources), or "unknown" plus what's typical for this role type.
   - `## Technical questions to practise`: 10–15, specific to this role family (ML: probability/stats, ML
     theory, model design, coding; quant: probability puzzles, mental maths, stats, coding; SWE: data
     structures, system design basics; data: SQL, experiments, stats). For the 5 most likely, a 2–3 line
     answer outline.
   - `## Your stories`: 4–5 STAR outlines (situation, task, action, result) built ONLY from facts in my CV,
     each mapped to the questions it answers ("a hard technical problem", "teamwork", "a failure", "why
     this role"). Real numbers from the CV only.
   - `## "Why us?" and "Why this role?"`: a 3–4 sentence answer for each, specific to this company.
   - `## Questions to ask them`: 5 good ones, specific to the team and news.
   - `## Practice plan`: what to practise on each of the next 5 days (30–60 min a day), with free resources.
   - `## On the day`: logistics checklist (format, what to have open, the time zone if remote).
5. **Never invent** facts about me. If something needs a fact you don't have, write `[ASK FARES: …]`.
6. Finish with: the file path and the 3 things to focus on first.
