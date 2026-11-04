# How to use it (simple version)

Your folder is `~/code/job-agent`. Every command below starts there: `cd ~/code/job-agent`.

## 0. One-time shortcut (recommended)
Add a `jobs` command to your Terminal:
```bash
echo 'alias jobs="~/code/job-agent/scripts/go.sh"' >> ~/.zshrc && source ~/.zshrc
```

## 1. Get new jobs: type `jobs`
That's it. It:
1. gets the latest version of the agent,
2. starts Claude with `/job-run` (approve the questions; it takes 20–40 minutes the first time, less later),
3. when Claude has finished, type `/exit`: your results are **saved and pushed to GitHub automatically**,
4. opens the job page.

`/job-run` fetches ~9,000 jobs, removes the ones that don't fit your rules, has Claude score every remaining
role against your CV, picks the best 15, checks what it might have missed, suggests CV changes and drafts
LinkedIn notes. By default `jobs` skips the LinkedIn **job search** (outreach still runs). Variants:
- `jobs full`: everything, including the LinkedIn job search.
- `jobs skip-linkedin skip-outreach`: no LinkedIn at all.
- `jobs skip-linkedin skip-cv skip-outreach`: just jobs and scores (fastest).

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
Keep that Terminal window open while you use the page; press Ctrl+C when done. Your marks and notes are
then **saved and pushed to GitHub automatically**. (Open it any time with `python3 -m jobagent view`.)

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

## 5b. Phone notifications (once)
1. Run `python3 -m jobagent notify-setup` and follow the 3 steps it prints (install the free **ntfy** app,
   subscribe to your private channel name, send a test).
2. After every scheduled run your phone gets "N new jobs picked" with the top 3 and any deadline reminders
   (high priority when something closes soon). Send one any time: `python3 -m jobagent notify`.

## 6. Saving
Automatic: after `jobs`, when you close the job page, and after the daily schedule. To save by hand at any
time: `python3 -m jobagent save`.

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
