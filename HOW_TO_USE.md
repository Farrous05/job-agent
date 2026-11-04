# How to use it (simple version)

Your folder is `~/code/job-agent`. Every command below starts there: `cd ~/code/job-agent`.

## 1. Get new jobs (about 20–40 minutes)
1. Open Terminal and type `cd ~/code/job-agent && git pull && claude --chrome`.
2. Type `/job-run` and press Enter. Say yes to permission questions.
3. What it does:
   - Fetches ~9,000 jobs from 42 company boards and freehire, plus web search and LinkedIn (read-only).
   - Removes the ones that don't fit your rules (senior, 3+ years, PhD-only, wrong country…).
   - **Claude reads and scores every remaining role (1–5) against your CV**, not just the top few.
     Scores are saved, so next time only new roles are read (much faster).
   - Picks the best 15, checks what it might have missed (recall check), suggests CV changes,
     drafts LinkedIn notes.
4. Quick versions: `/job-run skip-outreach`, `/job-run skip-cv`, `/job-run skip-linkedin`.

## 2. Look at the jobs
Type `python3 -m jobagent view`. Your browser opens the job page with 4 tabs:
- **Top picks:** the best 15. Each card has an **Apply** button, fit score, deadline countdown,
  sponsorship and why it fits.
- **All matches:** every role Claude scored. Filter by fit (3+, 4+, 5), search, sort by deadline.
- **My applications:** everything you marked. Change the stage (Applied → Interviewing → Offer / Rejected)
  and write notes (who you spoke to, next step).
- **Stats:** how many applications, replies and interviews, and which kinds of roles reply.

On any job, click **✓ Applied**, **★ Interested** or **✕ Not for me**. A yellow box at the top reminds
you of deadlines closing soon and applications with no reply for 2 weeks.
Keep that Terminal window open while you use the page; press Ctrl+C when done.

## 3. Apply to a job
1. In Claude, type `/apply <company>` (e.g. `/apply techwolf`).
2. It writes `applications/<company>-<role>/`:
   - `cover_letter.md`
   - `answers.md` (answers to the form questions)
   - `checklist.md` (which CV to attach, the deadline)
   It never invents anything: where it needs a fact from you it writes `[ASK FARES: …]`.
3. Read and edit the drafts, attach the CV from `cv/build/`, and submit on the company's site yourself.
4. Mark the job **✓ Applied** on the job page.

## 4. Your CV
- Tailored CVs (one per top job): `cv/build/<company>-<role>.pdf`. Main CV: `cv/build/cv.pdf`.
  If they're missing (e.g. on a new computer), run `scripts/build_cv.sh`.
- Suggested changes to your main CV: run `scripts/cv_diff.sh` (a PDF opens: red = removed, blue = added).
  To accept: `git merge cv-edits && git push`. To reject: do nothing.

## 5. LinkedIn messages
`outreach/<date>.md`: who to contact, their profile link, a message ready to copy. You send them yourself.

## 6. Save everything
`git add -A && git commit -m "Job run" && git push`

## Handy commands
- `python3 -m jobagent reminders`: deadlines closing soon and follow-ups due.
- `python3 -m jobagent stats`: your application numbers in the terminal.
- `python3 -m jobagent status`: did any job source fail last time?

## How good is it? (recall check)
Each `/job-run` checks itself against real postings from other job boards and writes
`data/runs/<date>/recall_report.md`: what it found, what a filter removed, and what no source returned.
On 4 Nov 2026 the feeds alone found 11 of 15 known graduate postings (73%). The rest (e.g. Revolut,
Jane Street's new-grad page) come from the web-search step.

## Something went wrong?
- "No shortlist yet" → run `/job-run` first.
- `ModuleNotFoundError: tomllib` → you need Python 3.11+: `brew install python`, then open a new Terminal.
- Chrome not connected → in Claude type `/chrome` and follow the steps.
- LinkedIn shows a warning or CAPTCHA → the agent stops by itself. Wait a day before LinkedIn steps again.
