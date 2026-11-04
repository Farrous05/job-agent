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
    "quant": r"\bquant(itative)?\b(?! surveyor)|algorithm(ic)? develop|\bresearch(er)?\b",
    "software": r"software|developer|\bswe\b|back[- ]?end|front[- ]?end|full[- ]?stack|platform engineer|infrastructure engineer|data engineer|devops|\bsre\b|site reliability|systems engineer|(c\+\+|java|python|rust|go|cloud|backend|frontend) engineer|engineering graduate|graduate engineer",
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


NON_EU = (r"\b(us|usa|united states|canada|apac|asia|india|brazil|mexico|san francisco|new york|seattle|nyc|sf|"
          r"toronto|ca|ny|wa)\b|,\s*(va|ma|tx|il|nj|ga|nc|md|fl|pa|oh|mi|mn|az|ut|dc|ct|wi|tn|mo|ok|la|nv|ia|ks|"
          r"ne|sc|al|ar|ky|or|id|nm|ri|nh|vt|me|ms|ne|wv|wy|mt|sd|nd|hi|ak)\b")


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


def years_range(text: str) -> tuple[int, int | None] | None:
    """Smallest experience demand as (min, max-or-None): '3+ years' -> (3, None), '2-3 years' -> (2, 3)."""
    best = None
    for m in re.finditer(r"(\d{1,2})\s*(?:(\+)|(?:-|–|to)\s*(\d{1,2}))?\s*\+?\s*years?(?:'|’)?\s*(?:of\s+)?"
                         r"(?:[\w/-]+\s+){0,4}?(?:experience|exp\b)", text, re.I):
        lo, hi = int(m.group(1)), (int(m.group(3)) if m.group(3) else None)
        if best is None or lo < best[0]:
            best = (lo, hi)
    for m in re.finditer(r"(?:at least|minimum of|minimum)\s+(\d{1,2})\s+years", text, re.I):
        lo = int(m.group(1))
        if best is None or lo < best[0]:
            best = (lo, None)
    return best


def years_required(text: str) -> int | None:
    r = years_range(text)
    return r[0] if r else None


def too_much_experience(text: str, max_years: int) -> str | None:
    """'3+ years' with max 2 -> too much. A range starting AT the max and going above it ('2-3 years')
    also counts, since that's what experienced hires are asked for; '1-3 years' is fine."""
    r = years_range(text)
    if not r:
        return None
    lo, hi = r
    if lo > max_years or (hi is not None and lo == max_years and hi > max_years):
        return f"{lo}{'-' + str(hi) if hi else '+'} years' experience required"
    return None


# --------------------------------------------------------------------------- language
_STOP = {
    "en": "the and with you our for are will your this that have team work",
    "fr": "les des et vous nous pour une avec dans sur est sont votre poste équipe",
    "de": "und die der mit sie wir für das ist eine bei unsere auf zu ihre",
    "es": "los las con para una que por del nuestro equipo sus como más",
    "it": "il della con per una che sono nel nostro gli delle alla",
    "nl": "het een van voor met zijn wij jouw onze bij naar ook",
    "pt": "para com uma que dos das nossa você equipe são mais",
    "pl": "się oraz jest dla nas w na z do pracy jako",
    "sv": "och att med för vi som är på din våra av",
    "da": "og at med for vi som er på din vores af",
}
_STOP = {k: set(v.split()) for k, v in _STOP.items()}
LANG_NAMES = {"en": "English", "fr": "French", "de": "German", "es": "Spanish", "it": "Italian", "nl": "Dutch",
              "pt": "Portuguese", "pl": "Polish", "sv": "Swedish", "da": "Danish"}


def posting_language(text: str) -> str | None:
    words = re.findall(r"[a-zà-ÿäöüßąęłńśźż]+", text.lower()[:3000])
    if len(words) < 40:
        return None
    counts = {lang: sum(w in sw for w in words) for lang, sw in _STOP.items()}
    lang = max(counts, key=counts.get)
    return lang if counts[lang] >= 8 else None


def languages_required(text: str) -> list[str]:
    """Languages a posting explicitly asks for (fluent/native/business-level X, X required)."""
    out = []
    for code, name in LANG_NAMES.items():
        n = name.lower()
        if re.search(rf"(fluent|fluency|native|business[- ]level|proficien\w*|excellent|strong|very good)\s+"
                     rf"(in\s+)?(written and spoken\s+)?{n}|{n}\s+(is\s+)?(required|mandatory|essential|"
                     rf"\(c1|\(c2|c1|c2|native)|{n}\s+(fluent|fluency)", text, re.I):
            out.append(code)
    return out


def sponsorship_status(description: str, region: str) -> tuple[str, str]:
    """Reads the job DESCRIPTION only. Returns (status, verdict); verdict in
    {'yes', 'no', 'mixed', 'graduate_visa', 'unknown'}. Only an explicit 'no sponsorship'
    statement gives 'no' (the only verdict that removes a job)."""
    if region == "eu":
        return "EU role: no sponsorship needed (French passport)", "yes"
    t = description.lower()
    no = re.search(r"(unable|not able|cannot|can't|can not|do not|don't|will not|won't|not)\s+"
                   r"(to\s+)?(provide|offer|sponsor|support)\w*\s+(any\s+)?(work\s+)?(visa|sponsorship|work permit|immigration)", t) \
        or re.search(r"without (requiring|needing|the need for|need of) (a |any )?(visa )?sponsorship", t) \
        or re.search(r"(visa )?sponsorship (is )?not (available|provided|offered)", t) \
        or re.search(r"right to work in the uk without (the need for )?(visa )?sponsorship", t) \
        or re.search(r"no (visa )?sponsorship(?! (is )?(required|needed))", t)
    yes = re.search(r"(visa )?sponsorship (is )?(available|provided|offered|considered)", t) \
        or re.search(r"\b(we|will|can|able to) (offer |provide )?(visa )?sponsor", t) \
        or re.search(r"skilled worker (visa )?sponsor", t)
    grad = re.search(r"graduate (route )?visa", t) and not re.search(r"(not|no)\s+(accept|eligible).{0,30}graduate visa", t)
    if yes and no:
        return "Mixed statements: check", "mixed"
    if yes:
        return "Sponsorship offered (stated)", "yes"
    if grad:
        return "Graduate visa accepted (stated)", "graduate_visa"
    if no:
        return "No sponsorship (stated)", "no"
    if re.search(r"right to work in the uk", t):
        return "Not stated (asks for UK right to work: check)", "unknown"
    return "Not stated", "unknown"


def evaluate(job: Job, cfg: dict) -> Verdict:
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
    # PhD: drop only PhD-only roles. Any Master's alternative nearby keeps the role.
    MASTERS = r"master|msc|m\.sc|\bms\b|mres|mphil|meng"
    def phd_only(t: str) -> bool:
        for m in re.finditer(r"ph\.?d|doctora|postdoc|post-doc", t, re.I):
            window = t[max(0, m.start() - 40): m.end() + 40]
            if not re.search(MASTERS, window, re.I):
                return True
        return False
    if re.search(r"ph\.?d|postdoc|post-doc", title, re.I) and phd_only(title):
        v.keep = False
        v.reasons.append("PhD-only role (title)")
    elif re.search(r"(phd|ph\.d|doctoral degree|doctorate)\s+(is\s+)?(required|essential|mandatory)|"
                   r"must (have|hold) a (phd|doctorate)|(currently )?(pursuing|enrolled in) a (phd|doctora)",
                   job.description, re.I) and phd_only(job.description) \
            and not re.search(r"phd (is )?(preferred|a plus|desirable|not required)", job.description, re.I):
        v.keep = False
        v.reasons.append("PhD required")

    exp = too_much_experience(job.description, f["max_years_experience"])
    if exp:
        v.keep = False
        v.reasons.append(exp)

    # --- internships
    v.internship = _has(r"\bintern(ship)?\b|placement|industrial year|co-?op\b|working student|werkstudent|praktikant|praktikum|stagiaire|\bstage\b|alternan|tirocinio|prácticas|becario", title)
    if _has(r"\b(sc|dv|nv)[- ]?clear(ed|ance)\b|security clearance", text):
        v.flags.append("needs UK security clearance (usually years of UK residency)")
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
    status, sv = sponsorship_status(job.description, v.region)
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
    # sponsorship: only an explicit statement counts; "not stated" changes nothing
    score += {"yes": 3, "graduate_visa": 3}.get(sv, 0)
    # location preference
    # city size / importance: preferred > hub > major > other (others are kept, just lower)
    score += city_bonus(job.location, cfg)
    # language: posting written in, or asking for, a language you don't speak
    spoken = set(cfg["profile"].get("languages", ["en"]))
    lang = posting_language(job.description)
    if lang and lang not in spoken:
        score -= 5
        v.flags.append(f"posting is in {LANG_NAMES[lang]}")
    else:
        need = [l for l in languages_required(job.description) if l not in spoken]
        if need:
            score -= 3
            v.flags.append("asks for " + "/".join(LANG_NAMES[l] for l in need))
    # company quality
    comp = job.company.lower()
    def named(names):
        return any(re.search(rf"(?<![a-z0-9]){re.escape(t.lower())}(?![a-z0-9])", comp) for t in names)
    if named(cfg["ranking"]["tier1"]):
        score += 3
    elif named(cfg["ranking"]["tier2"]):
        score += 1.5
    if v.internship:
        score -= 4

    v.score = round(score, 2)
    fam = "/".join(v.families[:2])
    v.why = f"{fam} role; matches CV on {', '.join(hits[:5]) or 'title only'}"
    return v


def city_bonus(location: str, cfg: dict) -> float:
    """Best city tier among a posting's locations. Weights in profile [locations.city_tiers]."""
    loc = location.lower()
    tiers = cfg["locations"].get("city_tiers", {})
    w = cfg["locations"].get("city_weights", {"preferred": 2.0, "hub": 1.5, "major": 0.5, "other": -1.0})
    def hit(cities):
        return any(re.search(rf"(?<![a-zà-ÿ]){re.escape(c)}(?![a-zà-ÿ])", loc) for c in cities)
    for tier in ("preferred", "hub", "major"):
        if hit(tiers.get(tier, [])):
            return w[tier]
    return 0.0 if "remote" in loc else w["other"]


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
