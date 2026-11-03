# How to use it (simple version)

## Where are my jobs?
- Run `python3 -m jobagent view`. Your browser opens the job page: one card per job with title, company,
  city, deadline, sponsorship, fit score, why it fits, a short description and an **Apply** button.
- Under each job, click **✓ Applied**, **★ Interested** or **✕ Not for me**. Click again to undo.
  Your clicks are saved in `seen_jobs.json`. Tick "hide not for me" to hide those.
- **My applications** (link at the top) lists everything you marked Applied or Interested, with dates.
- Leave the Terminal window open while you use the page. Press Ctrl+C there when you're done.
- Then save your marks to GitHub: `git add -A && git commit -m "Applications" && git push`.
- Quick look without buttons: double-click `shortlist/LATEST.html`.

## Where are my CVs?
- Tailored CVs (one per top job): `cv/build/<company>-<role>.pdf`.
- Your main CV: `cv/build/cv.pdf`.
- If the PDFs aren't there, run `scripts/build_cv.sh`.

## Where are the LinkedIn messages?
- `outreach/<date>.md`: who to contact, their profile link, and a message ready to copy.
  Nothing is sent. You send them yourself.

## Every time you want new jobs
1. Open Terminal.
2. Type `cd ~/job-agent && git pull && claude --chrome` and press Enter. (If your folder is elsewhere,
   e.g. `~/code/job-agent`, use that path instead.)
3. Type `/job-run` and press Enter.
4. Say yes when it asks for permission. Wait 15–25 minutes.
5. Your browser opens the job page. Read it and click **Apply** on the jobs you like.
6. Use the matching tailored CV from `cv/build/` when you apply.
7. When you're done, save everything to GitHub:
   ```bash
   git add -A && git commit -m "Job run" && git push
   ```

## If it suggests changes to your main CV
1. See them: `git diff HEAD..cv-edits -- cv/cv.tex`.
2. If you like them: `git merge cv-edits && git push`.
3. If not: do nothing. Your CV stays as it is.

## Only want one part?
In Claude, type one of these instead of `/job-run`:
- `/job-run skip-outreach` = jobs and CVs, no LinkedIn.
- `/outreach` = only LinkedIn messages.
- `/cv-review` = only CV work.

## Something went wrong?
- "No shortlist yet" → run `/job-run` first.
- Chrome not connected → in Claude type `/chrome` and follow the steps (Claude extension installed and signed in).
- LinkedIn shows a warning or CAPTCHA → the agent stops by itself. Wait a day before running outreach again.
