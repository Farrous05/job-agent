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
   - `cover_letter.md`: under 300 words, specific to this team and posting. Open with why this role and
     company, then 2 concrete pieces of evidence from my CV that match their top requirements, then
     availability (graduation date / start date) and a short close. No clichés ("I am writing to express…"),
     no flattery, no invented facts.
   - `answers.md`: draft answers for the questions the posting or its form asks (and, if unknown, the usual
     ones: why this company, why this role, a project you're proud of, right to work / sponsorship,
     notice period / start date, salary expectations). Right-to-work answers must match my profile exactly.
   - `checklist.md`: which CV file to attach (and its PDF in `cv/build/`), the deadline, the link, documents
     needed (transcript, references), and anything I must decide.
4. **Never invent.** If an answer needs a fact you don't have (salary expectation, grades not on the CV, a
   referee, a number), write `[ASK FARES: …]` in the draft and list these questions at the end of your reply.
5. If the role isn't marked yet, remind me to mark it Interested or Applied on the job page
   (`python3 -m jobagent view`). Finish with: the folder path, the 3 strongest points you used, and the questions.
