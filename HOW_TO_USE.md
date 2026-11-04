# How to use it (simple version)

Your folder is `~/code/job-agent`. Every command below starts there: `cd ~/code/job-agent`.

## Set up once (about 30 minutes, most of it downloads)
Do these in order in Terminal on your Mac. Each box is one command: copy it, paste it, press Enter.

**1. Homebrew** (installs the other tools). Skip if `brew --version` already works.
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
At the end it prints 2 "Next steps" commands: run them too.

**2. Tools:** Python 3.11+, git, GitHub login, PDF tools.
```bash
brew install python git gh poppler
```
**3. LaTeX** for the CV and cover-letter PDFs (big download, about 5 GB):
```bash
brew install --cask mactex-no-gui
```
Then **close Terminal and open a new one** so it finds the new tools.

**4. Log in to GitHub** (so your results are saved automatically). Choose GitHub.com, HTTPS, "Login with a web browser":
```bash
gh auth login
```
```bash
gh auth setup-git
```

**5. Claude Code**, then sign in with your Claude account (no API key):
```bash
curl -fsSL https://claude.ai/install.sh | bash
```
```bash
claude
```
Sign in in the browser it opens, then type `/exit`.

**6. Get the agent** (skip the clone if `~/code/job-agent` already exists):
```bash
mkdir -p ~/code && git clone https://github.com/Farrous05/job-agent.git ~/code/job-agent
```
```bash
cd ~/code/job-agent && git checkout claude/exciting-gates-89chfl && git pull
```
Check it works (should end with `OK`):
```bash
python3 -m unittest discover tests
```

**7. The `findjobs` shortcut:**
```bash
echo 'alias findjobs="~/code/job-agent/scripts/go.sh"' >> ~/.zshrc && source ~/.zshrc
```

**8. Telegram bot (your phone remote).**
1. On your phone, install Telegram and open a chat with **@BotFather**.
2. Send `/newbot`, give it any name, then a username ending in `bot` (e.g. `fares_jobs_bot`).
3. BotFather replies with a token like `123456:ABC-def...`. Open the link to your new bot and send it `hi`.
4. On the Mac:
   ```bash
   python3 -m jobagent notify-setup --telegram
   ```
   Paste the token when asked. You get a test message on your phone straight away.

**9. Switch on everything that runs by itself:**
```bash
scripts/install_mac.sh
```
It starts 3 things:
- **Daily job search at 08:40:** fetch, Claude scores every role, then a summary with buttons on Telegram.
- **The Telegram bot, always on:** answers your commands (below).
- **The job page, always on:** http://127.0.0.1:8765 on the Mac. On your phone (home Wi-Fi) it's the private
  link the script prints. You can also send `/page` to the bot.

If macOS asks to allow incoming connections for Python, click **Allow**. On your phone, open the link in Safari,
then Share → **Add to Home Screen** to get an app icon.

**10. First search:** send `/run` to the bot (about 20–40 min, then the summary arrives), or type `findjobs` on
the Mac to watch it run.

**Check it's all working:** send `/help` to the bot (it replies), open the job page link on your phone, and
tomorrow at about 08:45 a summary should arrive.

**Optional extras**
- **LinkedIn search and outreach drafts:** install the Claude extension in Chrome, sign in to the same Claude
  account, and sign in to LinkedIn in that Chrome. Then use `findjobs full`.
- **Reed (more UK jobs):** get a free key at https://www.reed.co.uk/developers/jobseeker, then:
  ```bash
  echo 'export REED_API_KEY=your_key_here' >> ~/.zshrc && source ~/.zshrc
  ```
- **Renew the Claude login** when it asks (`claude`, then `/login`): the daily run needs it.
- **Start again from zero:** `python3 -m jobagent reset` (keeps your marked jobs; `--all` forgets them too).
  To stop the background services: `scripts/install_mac.sh --uninstall`.

## Your normal week (almost no typing)
- **Each morning:** Telegram shows the new jobs. Tap **✓** (applied), **★** (interested) or **✕** (not for me).
- **To apply:** send the bot `/apply <company>`. A few minutes later you get the cover letter PDF and the
  form answers. Read them, apply on the company's site, then tap ✓.
- **CV changes:** send `/changes` to get the red/blue PDF with **Accept** and **Reject** buttons (also on the job
  page's **CV** tab).
- **Anything else:** `/jobs` top picks · `/all` best unmarked roles · `/cv` your CV · `/tailored` tailored CVs ·
  `/letter <company>` a drafted letter · `/run` search now · `/page` job-page link · `/reminders` · `/stats`
- Everything is saved to GitHub automatically.

## Telegram bot commands
| Send | You get |
|---|---|
| `/jobs` | today's top picks with ✓ ★ ✕ buttons |
| `/all` | best unmarked roles from All matches (fit 4+) |
| `/apply resonance` | Claude drafts the application; you receive the cover letter PDF, answers and checklist |
| `/changes` | suggested CV changes (PDF) with Accept / Reject buttons |
| `/cv`, `/tailored`, `/letter <company>` | the PDFs |
| `/run` | a full job search now (about 20 min), then the summary |
| `/page` | the private job-page link for your phone |
| `/reminders`, `/stats`, `/help` | deadlines, numbers, the command list |

## By hand on the Mac (optional)

### Shortcut
Add a `findjobs` command to your Terminal (not `jobs`: that name is taken by zsh):
```bash
echo 'alias findjobs="~/code/job-agent/scripts/go.sh"' >> ~/.zshrc && source ~/.zshrc
```

## 1. Get new jobs: type `findjobs`
That's it. It:
1. gets the latest version of the agent,
2. starts Claude with `/job-run` (approve the questions; it takes 20–40 minutes the first time, less later),
3. when Claude has finished, type `/exit`: your results are **saved and pushed to GitHub automatically**,
4. opens the job page.

`/job-run` fetches ~9,000 jobs, removes the ones that don't fit your rules, has Claude score every remaining
role against your CV, picks the best 15, checks what it might have missed, suggests CV changes and drafts
LinkedIn notes. By default `findjobs` skips the LinkedIn **job search** (outreach still runs). Variants:
- `findjobs full`: everything, including the LinkedIn job search.
- `findjobs skip-linkedin skip-outreach`: no LinkedIn at all.
- `findjobs skip-linkedin skip-cv skip-outreach`: just jobs and scores (fastest).

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
   - `cover_letter.tex` and `cover_letter.pdf` (same style as your CV, checked to fit on one page)
   - `answers.md` (answers to the form questions, including right to work)
   - `checklist.md` (which CV to attach, the deadline)
   It never invents anything: where it needs a fact from you it writes `[ASK FARES: …]`.
3. Read and edit the drafts. If you edit `cover_letter.tex`, rebuild the PDF with
   `scripts/build_letter.sh applications/<folder>`. Attach the CV from `cv/build/` and the cover letter PDF,
   and submit on the company's site yourself.
4. Mark the job **✓ Applied** on the job page.

## 4. Your CV
- Tailored CVs (one per top job): `cv/build/<company>-<role>.pdf`. Main CV: `cv/build/cv.pdf`.
  If they're missing (e.g. on a new computer), run `scripts/build_cv.sh`.
- Suggested changes to your main CV: run `scripts/cv_diff.sh` (a PDF opens: red = removed, blue = added).
  To accept: `git merge cv-edits && git push`. To reject: do nothing.

## 5. LinkedIn messages
`outreach/<date>.md`: who to contact, their profile link, a message ready to copy. You send them yourself.

## 5b. Phone notifications (once)
**Telegram (recommended, reliable on iPhone):** run `python3 -m jobagent notify-setup --telegram` and follow
the steps: create a bot with @BotFather, send your bot "hi", paste the token. You get a test message straight away.
After every scheduled run you get "N new jobs picked" with the top 3 and any deadline reminders.
Send one any time: `python3 -m jobagent notify`. (Alternative: `notify-setup` without `--telegram` uses the
ntfy app, but its iPhone notifications can be unreliable.)

## 6. Saving
Automatic: after `findjobs`, when you close the job page, and after the daily schedule. To save by hand at any
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
- `claude: command not found` → open a new Terminal, or rerun step 5.
- No Telegram messages → check the bot log: `tail -20 data/logs/com.fares.jobagent.bot.log`, then rerun step 8.
- Results not saved to GitHub → rerun step 4, then `python3 -m jobagent save`.
- The daily run didn't happen → `tail -40 data/logs/com.fares.jobagent.log`.
- Chrome not connected → in Claude type `/chrome` and follow the steps.
- LinkedIn shows a warning or CAPTCHA → the agent stops by itself. Wait a day before LinkedIn steps again.
