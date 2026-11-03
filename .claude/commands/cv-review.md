---
description: Review cv/cv.tex against the latest shortlist, propose edits on the cv-edits branch, write tailored CVs.
---

Inputs: `cv/cv.tex` and the newest `shortlist/*.md`.

Hard rules:
- NEVER edit `cv/cv.tex` on the main working branch. General edits go on the git branch `cv-edits` only.
  Don't merge it. I merge after I approve.
- NEVER invent experience, skills, results or metrics. If a bullet needs a number I haven't given you
  (e.g. the TODO in the Max Planck entry), add it to the "Questions for you" list in `cv/cv_feedback.md`.
- Every version must compile and fit on ONE page.

Steps:
1. **General review.** Compare the CV with the shortlisted roles' requirements. Find missing keywords
   (only ones that are true for me, based on the CV), weak or vague bullets, missing metrics, formatting
   issues and typos.
2. **General edits.** Run `git switch cv-edits` (create it from the current branch if it doesn't exist),
   edit `cv/cv.tex`, commit with one line per change, then switch back. Show me
   `scripts/cv_diff.sh --text` with a one-line reason per change, and tell me to run `scripts/cv_diff.sh` for the PDF.
3. **Tailored versions.** For each of the top-5 shortlisted roles I haven't already applied to, write
   `cv/tailored/<company>-<role>.tex` (lower-case, hyphens), based on the APPROVED `cv/cv.tex` from the
   current branch. Make 2–3 targeted tweaks only (reorder, reword, emphasise relevant skills), and list them
   in a `% TAILORING:` comment at the top of the file.
4. **Compile.** Run `scripts/build_cv.sh`. It compiles every .tex to `cv/build/` and fails if any PDF is
   longer than one page. If one overflows, tighten wording. Never drop true content silently.
5. **Feedback file.** Write `cv/cv_feedback.md`: the issues found, the edits made (with reasons), the
   tailoring per role, the top 3 changes, and the questions for me.
