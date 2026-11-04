"""seen_jobs.json: every job ever reported, so reruns only show new ones.

A job counts as seen if EITHER its source id OR its fuzzy key (company + normalised
title) is already stored. The fuzzy key stops the same role coming back from a second
source (e.g. ATS feed vs a job board found by web search).
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path


def fuzzy_key(company: str, title: str) -> str:
    c = re.sub(r"\b(trading|technologies|technology|capital|group|ltd|limited|inc|llc|plc|labs|ai|"
               r"research|securities|markets|uk|early careers?|careers|jobs|systems|inc\.?)\b", " ", company.lower())
    c = re.sub(r"[^a-z0-9]+", "", c) or re.sub(r"[^a-z0-9]+", "", company.lower())
    t = re.sub(r"\(.*?\)|[-–—:|,]", " ", title.lower())
    t = re.sub(r"\b(20\d\d|start|grads?|graduate|new|london|uk|programme|program)\b", " ", t)
    t = re.sub(r"[^a-z0-9]+", "", t)
    return f"{c}::{t}"


class SeenStore:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"jobs": {}}
        if path.exists():
            self.data = json.loads(path.read_text() or '{"jobs": {}}')
        # recompute so key-format changes apply to old entries too
        self._fuzzy = {fuzzy_key(v["company"], v["title"]) for v in self.data["jobs"].values()}

    def seen(self, source_id: str, company: str, title: str) -> bool:
        return source_id in self.data["jobs"] or fuzzy_key(company, title) in self._fuzzy

    def add(self, source_id: str, company: str, title: str, url: str, status: str = "reported",
            run: str | None = None, extra: dict | None = None) -> None:
        """extra: optional details kept for tracking (deadline, location, region, families, source, fit)."""
        fk = fuzzy_key(company, title)
        old = self.data["jobs"].get(source_id, {})
        self.data["jobs"][source_id] = {
            **old, **(extra or {}),
            "company": company, "title": title, "url": url, "fuzzy": fk,
            "first_reported": old.get("first_reported") or run or date.today().isoformat(),
            "status": old.get("status", status),
        }
        self._fuzzy.add(fk)

    # reported = shown, no mark. The last four are application stages.
    STATUSES = ("reported", "interested", "not_interested", "applied", "interviewing", "offer", "rejected")
    APPLIED = ("applied", "interviewing", "offer", "rejected")

    def set_status(self, source_id: str, status: str, company: str = "", title: str = "", url: str = "",
                   note: str | None = None, extra: dict | None = None) -> None:
        """Your own tracking from the browser page. Keeps a dated history of every change."""
        if status not in self.STATUSES:
            raise ValueError(status)
        if source_id not in self.data["jobs"]:
            self.add(source_id, company, title, url, extra=extra)
        job = self.data["jobs"][source_id]
        for k, v in (extra or {}).items():
            job.setdefault(k, v)
        today = date.today().isoformat()
        if job.get("status") != status:
            job.setdefault("history", []).append([today, status])
            job["status"] = status
            job["status_date"] = today
            if status == "applied" and not job.get("applied_date"):
                job["applied_date"] = today
        if note is not None:
            job["note"] = note[:2000]

    def statuses(self) -> dict:
        return {k: v.get("status", "reported") for k, v in self.data["jobs"].items()}

    def applied_companies(self) -> set[str]:
        return {v["company"] for v in self.data["jobs"].values() if v.get("status") in self.APPLIED and v.get("company")}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n")
