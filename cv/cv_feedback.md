# CV feedback: 2026-11-03

Reviewed `cv/cv.tex` against the 2026-11-03 shortlist (ML/AI eng, quant research/dev, SWE).
General edits are on branch **`cv-edits`** (not merged). Review them with
`git diff claude/exciting-gates-89chfl..cv-edits -- cv/cv.tex`. Every version compiles to 1 page.

## Top 3 changes
1. **Add the Max Planck result as a number.** This is your strongest entry, but the result bullet is
   qualitative. A before/after figure (e.g. detection accuracy or recovery rate) is the single biggest win.
   I need the number from you (question 1).
2. **Say when you graduate.** The profile now says "graduating September 2027" and UCL shows
   "Sep 2026 – Sep 2027 (expected)". Graduate screeners filter on this first.
3. **Tighten structure.** Velora-Dev moves to Experience (it's a role with dates, not a project), the weak
   "Wrote the prompts" bullet is merged into the agent bullet, and the format is now A4 with British spelling for UK/EU.

## Edits on `cv-edits` (one line each)
| Change | Reason |
|---|---|
| `letterpaper` → `a4paper`, side margins 0.55in → 0.45in | UK/EU standard; margins keep entry headers on one line |
| Phone `+44 74 54 76 84 53` → `+44 7454 768453` | Standard UK mobile format |
| Profile adds "(graduating September 2027)" | Start-date fit is the first screen for grad roles |
| UCL `2026 -- 2027` → `Sep 2026 -- Sep 2027 (expected)` | Makes the graduation date explicit |
| `Said Foundation` → `Saïd Foundation` | Correct spelling of the foundation's name |
| `Full time` / `Part time` → `Full-time` / `Part-time` | Hyphenation typo |
| "Designed the methodology and timeline" → "Designed the methodology" | "Timeline" adds nothing |
| LLM-judge bullet → "Added an LLM-as-a-judge evaluation pipeline … ran inference with vLLM" | Clearer about what you built |
| `Agentic Engineer , To Ai` → `Agentic Engineer, To Ai` | Stray space before the comma |
| Merged "Wrote the prompts…" into the agent bullet | Was the weakest bullet on its own |
| behavior/visualizes/HONORS → behaviour/visualises/HONOURS | Consistent British spelling for UK/EU |
| Velora-Dev moved from Projects to Experience | It's a co-founder role with dates; Projects mixed dates and tech stacks in the right column |

## Other issues found (not changed: they need your input)
- **Missing metrics:** Max Planck result, To Ai scale, captioning BLEU, tennis accuracy. See the questions below.
- **ATP Tennis project** has one thin bullet. Add the metric and the model used, or drop it for something stronger.
- **"Top 10 student, two consecutive years"**: of what cohort size, and where? Without that it reads vague.
- **Missing keywords the shortlist asks for, which you may have:** statistics/probability, data structures,
  Linux, CI/CD, distributed training, RAG. I added none of them. Tell me which are true.
- **UCL modules** aren't listed. Quant roles (Optiver, HRT, Jane Street) look for probability, statistics and
  optimisation modules.
- **"To Ai"**: check the company's official capitalisation ("To AI"?).
- **EU applications:** consider adding "French citizen (EU right to work)" for IMC, Mistral, Bloomberg Dublin
  and Revolut EU offices. You stated this, so it's safe to add if you want it.

## Tailored versions (`cv/tailored/`, rebuilt from the APPROVED `cv-edits` version)
G-Research is #2 on the shortlist but skipped because you've already applied. The top 5 not yet applied are:
| File | Tweaks |
|---|---|
| `revolut-applied-ai-engineer.tex` | Profile → shipping LLM product features; ML skills lead with agents/fine-tuning/eval; Velora bullet leads with AI agents |
| `hudson-river-trading-algorithm-developer.tex` | Profile → ML/statistical modelling for trading; tennis prediction above captioning; Python, C++ first |
| `optiver-graduate-quantitative-researcher.tex` | Profile → academic ranking + research method; tennis project first; quantitative coursework first |
| `jane-street-quantitative-researcher.tex` | OCaml first in languages; profile names OCaml/Python/C++; tennis project first |
| `palantir-software-engineer-new-grad.tex` | Profile leads with shipped production software; Languages/Infra before ML; To Ai backend bullet first |

Approved on 2026-11-03 and tailored files rebuilt. Tracked-changes PDF: `cv/cv-changes.pdf` (red = removed, blue = added).

## Questions for you
1. Max Planck: what's the measurable result? (e.g. collapse-detection accuracy on held-out conversations,
   recovery rate before vs after fine-tuning, or the judge score change)
2. To Ai: any scale numbers? (number of client businesses or agents deployed, messages/events per day,
   response-time or conversion improvements)
3. Image captioning: BLEU-4 score (and dataset, e.g. Flickr8k/COCO)?
4. ATP prediction: accuracy vs a baseline (e.g. higher-ranked player wins)?
5. "Top 10 student, two consecutive years": which programme, and out of how many?
6. Which UCL MSc modules are you taking?
7. Velora-Dev: how many client projects have you delivered?

## Run 3 (2026-11-03, `shortlist/2026-11-03-run3.md`)
New general edit on local branch `cv-edits` (not merged; the older remote `cv-edits` is already merged, so push with care):
| Change | Reason |
|---|---|
| Header adds "French citizen (EU right to work)" | 8 of the 15 new roles are in the EU/Switzerland (ARM, Ericsson, UBS, Reply Munich, Techwolf, Dassault, WTW, Arista, Stripe); screeners see right to work first |

Tailored versions (top 5 not already applied; Reply may overlap Data Reply, which you applied to):
| File | Tweaks |
|---|---|
| `reply-graduate-ai-ml-engineer.tex` | Profile → LLM agents on AWS for clients; LangChain/LangGraph first; AWS/Docker first |
| `anthropic-research-resident.tex` | Profile → mode-collapse research + LLM evaluation; fine-tuning/judge/vLLM first; SLURM first |
| `hudson-river-trading-research-engineer.tex` | Profile → ML research engineering at scale; Python, C++ first; SLURM first |
| `arm-graduate-machine-learning-engineer.tex` | Profile → ML engineering (PyTorch, vLLM) with C/C++; Python, C++, C first; PyTorch first |
| `arm-graduate-ml-software-engineer.tex` | Profile → ML software engineering in Python/C++; Python, C++, C first; Docker/Git first |

## 2026-11-04 run
No new general edits: `cv/cv.tex` already contains the earlier edits, so there is nothing new on `cv-edits`.
Still open: question 1 (a before/after number for the Max Planck result) is the single biggest CV win.

Tailored (profile line + skills order only, nothing invented; all compile to 1 page):
- `jane-street-machine-learning-researcher.tex`: research-led profile.
- `techwolf-junior-ai-engineer.tex`: LLM agents, fine-tuning and evaluation in the profile.
- `ubs-ai-engineer-graduate.tex`: Python/production framing, Languages first.
- `squarepoint-graduate-software-developer.tex`: SWE framing, Languages and Infrastructure before ML.
- Arm: existing `arm-graduate-machine-learning-engineer.tex` reused.
