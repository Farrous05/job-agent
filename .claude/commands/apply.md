---
description: Draft a cover letter and application answers for one role (you review and submit yourself).
argument-hint: "<company or job title or job id>"
---

Role to prepare: $ARGUMENTS

You prepare application material. You NEVER submit, upload, send or click Apply. I do that.

1. **Find the role.** Search the newest `shortlist/*.md`, `data/runs/*/matches.json` and `seen_jobs.json`
   for $ARGUMENTS. If several match, list them and ask which one. Then WebFetch the posting URL for the
   full description (requirements, questions, deadline). If the posting is closed, say so and stop.
2. **Read me.** `cv/cv.tex` (or the tailored `cv/tailored/<company>-<role>.tex` if one exists),
   `config/profile.toml` (degree, graduation, work rights and `[work_rights].notes`), `cv/cv_feedback.md`.
3. **Write `applications/<company>-<role>/`** (lower-case, hyphens):
   - `cover_letter.tex`: copy `templates/cover_letter.tex` and replace EVERY `%% FILL ... %%` line (date in UK
     style, e.g. "4 November 2026"; company and team; exact job title; four short paragraphs). Under 300 words,
     specific to this team and posting: why this role and company; 2 concrete pieces of evidence from my CV
     that match their top requirements (with the CV's real numbers); availability (graduation / start date);
     a short close. No clichés ("I am writing to express…"), no flattery, no invented facts. Escape LaTeX
     special characters in text (`&` → `\&`, `%` → `\%`, `$` → `\$`, `#` → `\#`, `_` → `\_`).
     Then run `scripts/build_letter.sh applications/<company>-<role>` and fix anything it reports
     (placeholders left, compile error, more than 1 page).
   - `answers.md`: draft answers for the questions the posting or its form asks (and, if unknown, the usual
     ones: why this company, why this role, a project you're proud of, right to work / sponsorship, notice
     period / start date, salary expectations). Right-to-work answers must match my profile exactly.
   - `checklist.md`: which CV file to attach (and its PDF in `cv/build/`), the cover letter PDF, the deadline,
     the link, documents needed (transcript, references), and anything I must decide.
   **Visa / work rights:** they belong in `answers.md` (the form's right-to-work question), NOT in the cover
   letter or among the "strongest points". Exception: for a job located in the EU/EEA/Switzerland, one short
   clause in the letter is fine ("as a French citizen I can start without sponsorship"). For UK jobs, never
   mention visas or sponsorship in the letter unless the posting explicitly asks about it there.
4. **Never invent.** If an answer needs a fact you don't have (salary expectation, grades not on the CV, a
   referee, a number), write `[ASK FARES: …]` in the draft and list these questions at the end of your reply.
5. If the role isn't marked yet, remind me to mark it Interested or Applied on the job page
   (`python3 -m jobagent view`). Finish with: the folder path, the cover letter PDF path, the 3 strongest points
   you used (skills and experience only, not work rights), and the questions.
