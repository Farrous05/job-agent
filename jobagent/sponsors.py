"""UK Register of Licensed Sponsors (Workers), from GOV.UK.

The CSV link changes with every update, so we read the publication page, find the
latest CSV asset and cache it in data/sponsors.csv for 7 days.
"""
from __future__ import annotations

import csv
import re
import time
import urllib.request
from pathlib import Path

PAGE = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
UA = "job-agent/1.0 (personal job search script)"
_SUFFIX = re.compile(r"\b(ltd|limited|llp|plc|inc|llc|uk|u\.k\.|group|holdings|technologies|technology|"
                     r"services|international|europe|the|&|and|co)\b\.?", re.I)


def norm(name: str) -> str:
    n = _SUFFIX.sub(" ", name.lower())
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def load(data_dir: Path, max_age_days: int = 7) -> set[str] | None:
    """Return normalised sponsor names, or None if the register is unavailable."""
    path = data_dir / "sponsors.csv"
    try:
        if not path.exists() or time.time() - path.stat().st_mtime > max_age_days * 86400:
            page = _get(PAGE).decode("utf-8", "replace")
            m = re.search(r'href="(https://assets\.publishing\.service\.gov\.uk/[^"]+\.csv)"', page)
            if not m:
                raise RuntimeError("CSV link not found on GOV.UK page")
            path.write_bytes(_get(m.group(1)))
    except Exception as e:  # noqa: BLE001 - network or page changes; register is optional
        if not path.exists():
            print(f"  [sponsors] register unavailable: {e}")
            return None
    names = set()
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            name = row.get("Organisation Name") or next(iter(row.values()), "")
            if name:
                names.add(norm(name))
    return names


def on_register(company: str, names: set[str] | None) -> bool | None:
    if names is None:
        return None
    n = norm(company)
    if not n:
        return None
    if n in names:
        return True
    # prefix match handles "Hudson River Trading" vs "Hudson River Trading Europe Ltd"
    return any(s.startswith(n + " ") or s == n for s in names)
