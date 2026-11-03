"""Hard filters, sponsorship detection and heuristic scoring."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .sources import Job

# --------------------------------------------------------------------------- role families
FAMILY_PATTERNS = {
    "ml": r"machine learning|\bml\b|deep learning|\bmle\b|research engineer|applied scientist|nlp|computer vision",
    "ai": r"\bai\b|artificial intelligence|llm|genai|generative",
    "data_science": r"data scien|data analyst|analytics|statistic",
    "quant": r"quant|algorithm(ic)? develop|research(er)?\b",
    "software": r"software|developer|engineer|swe\b|backend|full[- ]?stack|platform|infrastructure",
}
ENTRY_WORDS = r"graduate|new grad|grads?\b|entry|junior|campus|early career|university|2027|class of|associate programme|graduate programme"

# CV keywords (lower-case). Matched in the description to explain fit.
CV_KEYWORDS = ["pytorch", "transformer", "hugging face", "llm", "large language model", "fine-tun",
               "nlp", "natural language", "evaluation", "vllm", "agent", "langchain", "langgraph",
               "python", "c++", "java", "sql", "aws", "docker", "slurm", "hpc", "distributed",
               "deep learning", "machine learning", "statistics", "probability", "algorithms",
               "data structures", "scikit", "pandas", "numpy", "research", "typescript", "rag",
               "reinforcement learning", "computer vision", "multimodal", "inference"]


@dataclass
class Verdict:
    keep: bool
    reasons: list[str] = field(default_factory=list)   # why excluded
    region: str = ""          # uk / eu / other
    sponsorship: str = ""     # human-readable status
    families: list[str] = field(default_factory=list)
    internship: bool = False
    score: float = 0.0
    why: str = ""
    flags: list[str] = field(default_factory=list)


def _has(pat: str, text: str) -> bool:
    return re.search(pat, text, re.I) is not None


def _any_word(words, text: str) -> bool:
    return any(re.search(rf"(?<![a-zà-ÿ]){re.escape(w)}(?![a-zà-ÿ])", text) for w in words)


NON_EU = r"\b(us|usa|united states|canada|apac|asia|india|brazil|mexico|san francisco|new york|seattle|nyc|sf|toronto|ca|ny|wa)\b"


def region_of(location: str, cfg: dict) -> str:
    """Whole-word match per listed location, so 'uk' doesn't hit 'Ukraine' and 'porto' doesn't hit
    'Porto Alegre, Brazil'. Multi-location strings ('London; New York') pass if any part is UK/EU."""
    parts = [p.strip() for p in re.split(r"[;/|]| or ", location.lower()) if p.strip()] or [""]
    regions = set()
    for loc in parts:
        if _any_word(cfg["locations"]["uk"], loc):
            regions.add("uk")
        elif _any_word(cfg["locations"]["eu"], loc) and not re.search(NON_EU, loc):
            regions.add("eu")
        elif "remote" in loc and not re.search(NON_EU, location.lower()):
            regions.add("eu")   # remote with no non-EU marker: keep, let Claude check
    return "uk" if "uk" in regions else "eu" if "eu" in regions else "other"


def years_required(text: str) -> int | None:
    """Smallest 'N+ years' / 'N-M years' / 'at least N years' experience demand found, else None."""
    mins = []
    for m in re.finditer(r"(\d{1,2})\s*(?:\+|-|–|to)?\s*(\d{1,2})?\s*\+?\s*years?(?:'|’)?\s*(?:of\s+)?"
                         r"(?:[\w/-]+\s+){0,4}?(?:experience|exp\b)", text, re.I):
        mins.append(int(m.group(1)))
    for m in re.finditer(r"(?:at least|minimum of|minimum)\s+(\d{1,2})\s+years", text, re.I):
        mins.append(int(m.group(1)))
    return min(mins) if mins else None


def sponsorship_status(text: str, region: str, company_on_register: bool | None) -> tuple[str, str]:
    """Returns (status, verdict) where verdict in {'yes','no','graduate_visa','unknown'}."""
    if region == "eu":
        return "EU role: no sponsorship needed (French passport)", "yes"
    t = text.lower()
    no = re.search(r"(unable|not able|cannot|can't|can not|do not|don't|will not|won't|not)\s+"
                   r"(to\s+)?(provide|offer|sponsor|support)\w*\s+(any\s+)?(visa|sponsorship|work permit|immigration)", t) \
        or re.search(r"(visa )?sponsorship (is )?not (available|provided|offered)", t) \
        or re.search(r"right to work in the uk without (the need for )?(visa )?sponsorship", t) \
        or re.search(r"(unrestricted|full) right to work .{0,60}(duration|programme|program)", t) \
        or re.search(r"right to work in the uk without (any )?restrictions?", t) \
        or re.search(r"(must|need to|should) (already )?have the right to work in the uk", t) \
        or re.search(r"no (visa )?sponsorship", t)
    yes = re.search(r"(visa )?sponsorship (is )?(available|provided|offered|considered)", t) \
        or re.search(r"(we|will|can|able to) (offer |provide )?(visa )?sponsor", t) \
        or re.search(r"skilled worker (visa )?sponsor", t)
    grad = re.search(r"graduate (route )?visa", t)
    if yes and not no:
        return "Sponsorship offered (stated)", "yes"
    if grad and not re.search(r"(not|no)\s+(accept|eligible).{0,30}graduate visa", t):
        return "Graduate visa mentioned/accepted (stated)", "graduate_visa"
    if no:
        return "No sponsorship (stated)", "no"
    reg = {True: "company IS on UK sponsor register", False: "company NOT found on UK sponsor register",
           None: "sponsor register not checked"}[company_on_register]
    return f"Not stated; {reg}", "unknown"


def evaluate(job: Job, cfg: dict, company_on_register: bool | None = None) -> Verdict:
    f = cfg["filters"]
    title = job.title
    tl = title.lower()
    text = f"{title}\n{job.description}"
    v = Verdict(keep=True)

    # --- role family
    v.families = [k for k, p in FAMILY_PATTERNS.items() if _has(p, title)]
    if not v.families:
        v.keep = False
        v.reasons.append("not a target role family")

    # --- seniority / PhD
    for w in f["exclude_title_words"]:
        if w.strip() and re.search(rf"(?<![a-z]){re.escape(w.strip())}(?![a-z])", tl):
            v.keep = False
            v.reasons.append(f"title contains '{w.strip()}'")
            break
    if re.search(r"phd (is )?(required|essential)|must (have|hold) a phd|(completed|pursuing|hold) a phd\b(?! or)|"
                 r"doctoral degree (is )?required", text, re.I) \
            and not re.search(r"phd (is )?(preferred|a plus|desirable|not required)|master'?s or phd|msc or phd", text, re.I):
        v.keep = False
        v.reasons.append("PhD required")

    yrs = years_required(job.description)
    if yrs is not None and yrs > f["max_years_experience"]:
        v.keep = False
        v.reasons.append(f"{yrs}+ years' experience required")

    # --- internships
    v.internship = _has(r"\bintern(ship)?\b|placement|industrial year|co-?op\b|working student|werkstudent", title)
    if v.internship:
        if f.get("exclude_summer_internships") and _has(r"summer|jun(e)?\s*[-–]|10[- ]week|12[- ]week", text) \
                and not _has(r"off[- ]cycle|part[- ]time", text):
            v.keep = False
            v.reasons.append("summer internship (student visa clash)")
        else:
            v.flags.append("internship: check it fits student-visa hours (20h/week in term)")

    for y in f.get("exclude_graduation_years", []):
        if re.search(rf"(graduat\w*|class of|grads?)\D{{0,25}}{y}|{y}\s*(grads?|graduates)", text, re.I) \
                and not re.search(r"2027", title):
            v.keep = False
            v.reasons.append(f"aimed at {y} graduates")
            break

    # --- location / work rights
    v.region = region_of(job.location, cfg)
    if v.region == "other":
        v.keep = False
        v.reasons.append("location outside UK/EU")
    status, sv = sponsorship_status(text, v.region, company_on_register)
    v.sponsorship = status
    if v.region == "uk" and sv == "no":
        v.keep = False
        v.reasons.append("UK role, no sponsorship and no Graduate visa")
    if v.region == "uk" and re.search(r"(two|2)[- ]year (graduate )?(programme|program|scheme)", text, re.I):
        v.flags.append("2-year programme: Graduate visa (18 months) may not cover it")

    if not v.keep:
        return v

    # --- scoring
    fam_w = cfg["ranking"]["families"]
    score = max(fam_w.get(fm, 0) for fm in v.families)
    if _has(ENTRY_WORDS, title):
        score += 6
    elif _has(ENTRY_WORDS + r"|recent graduate|no experience required|0-2 years|fellows|residen", job.description[:3000] + title):
        score += 3
    else:
        score -= 6
        v.flags.append("not labelled entry-level: check experience bar")
    # start date fit
    if _has(r"(september|autumn|fall|summer|august|2027)\s*(start|intake)?.{0,20}2027|2027 start|start(ing)? in 2027", text):
        score += 4
    if _has(r"immediate start|asap|start date:? (now|immediately)", text):
        score -= 3
    if _has(r"start\w*[^.]{0,40}\b(january|february|march|april|may|june)\s+2027|"
            r"\b(january|february|march|april|may|june)\s+2027\s+(start|cohort|intake)", text):
        score -= 8
        v.flags.append("starts before you graduate (Sept 2027)")
    # CV fit
    desc = job.description.lower()
    hits = [k for k in CV_KEYWORDS if k in desc or k in tl]
    score += min(len(hits), 12) * 0.75
    # sponsorship clarity
    score += {"yes": 3, "graduate_visa": 3, "unknown": 0}.get(sv, 0)
    if v.region == "uk" and company_on_register:
        score += 1
    # location preference
    if v.region == "uk" and not any(c in job.location.lower() for c in cfg["locations"]["uk_prefer"]):
        score -= 2
    # company quality
    comp = job.company.lower()
    if any(t.lower() in comp for t in cfg["ranking"]["tier1"]):
        score += 3
    elif any(t.lower() in comp for t in cfg["ranking"]["tier2"]):
        score += 1.5
    if v.internship:
        score -= 4

    v.score = round(score, 2)
    fam = "/".join(v.families[:2])
    v.why = f"{fam} role; matches CV on {', '.join(hits[:5]) or 'title only'}"
    return v


def is_applied(company: str, cfg: dict) -> bool:
    c = company.lower()
    return any(a.lower() in c for a in cfg["profile"]["already_applied"])


def title_prefilter(cfg: dict):
    """Cheap filter used before fetching Workday descriptions."""
    def ok(title: str) -> bool:
        return any(_has(p, title) for p in FAMILY_PATTERNS.values()) and not any(
            re.search(rf"(?<![a-z]){re.escape(w.strip())}(?![a-z])", title.lower())
            for w in cfg["filters"]["exclude_title_words"] if w.strip())
    return ok
