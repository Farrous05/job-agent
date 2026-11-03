# Research: how to build a local job-search agent (Nov 2026)

## Recommendation

**A hybrid.** A small Python fetcher (standard library only) pulls public ATS JSON feeds on a local
launchd/cron schedule, filters them and remembers what it has reported in `seen_jobs.json`. A
**Claude Code slash command (`/job-run`)** then does the judgement work: checks company pages and UK
graduate boards by web search, ranks the roles, reviews the CV and drafts LinkedIn outreach through
**Claude in Chrome** in your own signed-in browser.

Why:
- **Reliable.** ATS JSON (Greenhouse, Lever, Ashby) is structured, needs no key and rarely changes. Scraping
  HTML graduate boards breaks often.
- **Cheap.** The scheduled fetch costs £0. The Claude steps run on your existing Claude plan, so there's no
  API key and no per-call billing.
- **Low maintenance.** About 700 lines of Python with no dependencies. Companies live in a config file, and
  broken board tokens are reported automatically in `data/source_status.json`.
- **Memory.** `seen_jobs.json` keys on both the source id and a fuzzy company+title key, so the same role
  from two sources isn't reported twice.
- The judgement steps (sponsorship wording, start-date fit, CV tailoring, choosing who to message) are where
  an LLM actually helps. The Agent SDK would mean writing the agent loop, browser control and permissions
  yourself. Claude Code already has all three.

## Build options

| Option | Reliability | Cost / run | Maintenance | Memory of reported jobs | Verdict |
|---|---|---|---|---|---|
| Plain script + cron/launchd | High for ATS feeds; no judgement | £0 | Low | Own JSON file | **Use for fetch/filter** |
| Claude Code + slash command (+ `claude -p` headless for schedule) | High; uses web search and browser | Included in Claude plan | Very low (Markdown prompts) | Same JSON file via script | **Use for ranking, CV, outreach** |
| Claude Agent SDK (Python) | High, but you build the loop and tools | API tokens (~£0.10–0.50/run est.) | Medium; SDK is 0.x and changing | Own code | Overkill for one user |
| MCP server for job data (community LinkedIn/Indeed MCPs) | Low–medium; mostly scrapers, ToS risk | £0–API fees | Medium; third-party, unmaintained risk | None built in | Skip |
| Paid scrapers (Apify actors for Greenhouse/Workday etc.) | Medium–high | ~$1.5–2.5 per 1k jobs | Low | None | Not needed; feeds are free |

## Data sources

**Live test (3 Nov 2026, after network access was opened):** 24 boards fetched without errors, 6,021 jobs.
Wayve is on Ashby, not Greenhouse. Google DeepMind, G-Research and Mistral have no usable public board, so they're
checked by web search. Workday (NVIDIA) works.

| Source | Access | Key? | Reliability | Coverage for you | Status |
|---|---|---|---|---|---|
| Greenhouse `boards-api.greenhouse.io/v1/boards/<t>/jobs?content=true` | Public JSON | No | High | HRT, IMC, XTX, DRW, Graphcore, Optiver, DeepMind, Anthropic… | Tokens seen in live URLs (HRT `wehrtyou`, IMC `imc`, XTX `xtxmarketstechnologies`, DRW `drweng`) |
| Lever `api.lever.co/v0/postings/<t>?mode=json` | Public JSON | No | High | Palantir, Mistral… | Palantir token confirmed in live URL |
| Ashby `api.ashbyhq.com/posting-api/job-board/<t>` | Public JSON | No | High | ElevenLabs, OpenAI, Cohere, Synthesia | ElevenLabs token confirmed |
| Workday `POST <tenant>.wdN.myworkdayjobs.com/wday/cxs/<t>/<site>/jobs` | Undocumented JSON, 20/page | No | Medium (can change; some tenants block bots) | NVIDIA, banks | Implemented, unverified |
| Company career sites (Jane Street, Revolut, Bloomberg, Two Sigma, PwC…) | HTML | No | Medium | Several top targets | Via `/job-run` web search |
| Bright Network / Gradcracker / TARGETjobs | HTML only; no API or RSS found | No | Low to scrape | Best for UK grad schemes and deadlines | Via `/job-run` web search (worked well in first run) |
| Reed.co.uk Jobseeker API | JSON | Free key | High | UK aggregator, grad filter | Optional (`REED_API_KEY`) |
| Adzuna API | JSON | Free key (app id + key) | High | UK/EU aggregator | Not wired in (Reed covers the UK) |
| GOV.UK Register of Licensed Sponsors (CSV) | Public CSV | No | Medium: name matching gave false hits (e.g. 'Alan' matched 21 firms) | Can sponsor ≠ will sponsor this role | Tried, then removed; only explicit statements in the job description are used |
| LinkedIn job search via your browser | Signed-in browser | — | Medium | Very broad | Optional; ToS bans scraping and bots, so keep it manual/low-volume |

## Things that matter for your filters
- The Graduate visa is **18 months** for applications made from 1 Jan 2027. You'll apply after Sept 2027, so
  2-year UK programmes that don't sponsor are risky. The agent flags these.
- A UK role is removed only if its description explicitly says there's no sponsorship. Wording like
  "right to work in the UK without restrictions" (e.g. LSEG) is kept and marked "check".
- Full-time off-cycle internships during the MSc (e.g. UBS April–Sept 2027) exceed student-visa hours, so they're
  excluded. Off-cycle roles starting **after** graduation (Graduate visa) are fine.

## Sources
- Greenhouse API: [Medium guide](https://medium.com/@sevicdev/integration-with-greenhouse-public-jobs-api-b548b23ad867), [Apify actor](https://apify.com/schnellscrapers/greenhouse-jobs-scraper)
- Lever/Ashby APIs: [DEV guide](https://dev.to/fecklesspleb/reading-greenhouse-lever-and-ashby-job-boards-from-their-public-json-endpoints-1651), [Ashby guide](https://dev.to/zsevic/integration-with-ashby-public-jobs-api-34n6), [cavuno overview](https://cavuno.com/blog/ats-platforms-public-job-posting-apis)
- Workday: [DEV: hidden JSON API](https://dev.to/udaninn/workday-job-boards-have-a-json-api-too-its-just-better-hidden-23fl), [DEV: scraper guide](https://dev.to/devil_scrapes/workday-jobs-scraper-how-to-pull-every-posting-from-any-workday-career-site-1dm0)
- Claude Code headless: [docs](https://docs.claude.com/en/docs/claude-code/headless)
- Claude in Chrome: [docs](https://code.claude.com/docs/en/chrome), [support article](https://support.claude.com/en/articles/12012173-claude-in-chrome)
- Claude Agent SDK: [Augment guide](https://www.augmentcode.com/guides/claude-agent-sdk-python), [Alex Cloudstar guide](https://alexcloudstar.com/blog/claude-agent-sdk-guide-2026/)
- Job MCP servers: [Glama LinkedIn MCP](https://glama.ai/mcp/servers/administrativetrick/linkedin-mcp), [openings-mcp](https://www.mdskills.ai/mcp-servers/openings-mcp)
- Reed API: [jobspipe write-up](https://jobspipe.dev/blog/reed-api), [reed-mcp](https://glama.ai/mcp/servers/soheilfallah/reed-mcp/tree)
- UK sponsor register: [GOV.UK CSV example](https://www.gov.uk/csv-preview/6a3917a2c6e94f095f3efb8c/2026-06-22_-_Worker_and_Temporary_Worker.csv)
- LinkedIn automation policy: [LinkedIn help: automated activity](https://www.linkedin.com/help/linkedin/answer/90586), [hiQ ruling blog](https://blog.linkedin.com/2022/november/4/update-hi-q-legal-proceeding)
- Graduate visa change: [Accenture 2027 listing / visa notes](https://www.jointheintake.com/graduate-schemes/software-engineering), [HRT 2027 grads aggregator](https://www.kadoa.com/quant/job/hudsonrivertrading-software-engineer-c-or-python-2027-grads-c9e7c316)
