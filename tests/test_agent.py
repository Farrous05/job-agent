"""Offline tests: python3 -m unittest discover tests"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobagent import filters, report, sources
from jobagent.__main__ import load_cfg
from jobagent.sources import Job
from jobagent.store import SeenStore, fuzzy_key

CFG, COMPANIES = load_cfg()


def job(title, desc="", loc="London, UK", company="Acme"):
    return Job("test", f"t:{title}", company, title, loc, "https://x/1", desc)


class FilterTests(unittest.TestCase):
    def test_keeps_graduate_ml(self):
        v = filters.evaluate(job("Graduate Machine Learning Engineer (2027 Start)",
                                 "PyTorch, LLM fine-tuning. Visa sponsorship is available."), CFG)
        self.assertTrue(v.keep, v.reasons)
        self.assertIn("ml", v.families)
        self.assertEqual(v.sponsorship, "Sponsorship offered (stated)")

    def test_excludes_senior(self):
        self.assertFalse(filters.evaluate(job("Senior Machine Learning Engineer"), CFG).keep)
        self.assertFalse(filters.evaluate(job("Staff Software Engineer"), CFG).keep)

    def test_excludes_years(self):
        v = filters.evaluate(job("Machine Learning Engineer", "You have 3+ years of experience in Python."), CFG)
        self.assertFalse(v.keep)
        v = filters.evaluate(job("Machine Learning Engineer", "0-2 years of industry experience."), CFG)
        self.assertTrue(v.keep, v.reasons)

    def test_excludes_phd_required(self):
        self.assertFalse(filters.evaluate(job("Research Scientist", "A PhD is required."), CFG).keep)
        self.assertTrue(filters.evaluate(job("Research Engineer", "MSc or PhD in ML."), CFG).keep)

    def test_uk_no_sponsorship_excluded(self):
        lseg = "Candidates should have the right to work in the UK without restrictions for the duration of the programme."
        self.assertFalse(filters.evaluate(job("Graduate Software Engineer", "We are unable to provide visa sponsorship."), CFG).keep)
        self.assertFalse(filters.evaluate(job("Engineering Graduate Programme (Backend)", lseg), CFG).keep)
        graphcore = "graduate opportunities are permanent positions, and we are unable to provide visa sponsorship."
        self.assertFalse(filters.evaluate(job("Graduate Machine Learning Engineer 2027", graphcore, "Bristol, UK"), CFG).keep)

    def test_eu_no_sponsorship_needed(self):
        v = filters.evaluate(job("Software Engineer, New Grad", "We cannot sponsor visas.", loc="Paris, France"), CFG)
        self.assertTrue(v.keep, v.reasons)
        self.assertEqual(v.region, "eu")

    def test_us_excluded(self):
        self.assertFalse(filters.evaluate(job("New Grad SWE", loc="New York, NY"), CFG).keep)

    def test_summer_intern_excluded_offcycle_kept(self):
        self.assertFalse(filters.evaluate(job("Quant Research Intern", "10-week summer internship 2027"), CFG).keep)
        v = filters.evaluate(job("Off-Cycle Quant Internship", "6-month off-cycle internship"), CFG)
        self.assertTrue(v.keep, v.reasons)
        self.assertTrue(v.internship)

    def test_ranking_prefers_ml_grad(self):
        a = filters.evaluate(job("Graduate ML Engineer 2027", "pytorch llm transformer python", company="DeepMind"), CFG)
        b = filters.evaluate(job("Software Developer", "java"), CFG)
        self.assertGreater(a.score, b.score)

    def test_years_parser(self):
        self.assertEqual(filters.years_required("at least 5 years of relevant experience"), 5)
        self.assertIsNone(filters.years_required("a 2027 start, 12-month programme"))


class SourceTests(unittest.TestCase):
    def test_greenhouse(self):
        payload = {"jobs": [{"id": 1, "title": "Graduate SWE", "location": {"name": "London"},
                             "absolute_url": "https://g/1", "content": "&lt;p&gt;Python&lt;/p&gt;", "updated_at": "x"}]}
        with mock.patch.object(sources, "_request", return_value=payload):
            js = sources.greenhouse("Acme", "acme")
        self.assertEqual(js[0].description, "Python")
        self.assertEqual(js[0].source_id, "gh:acme:1")

    def test_lever(self):
        payload = [{"id": "a", "text": "New Grad SWE", "hostedUrl": "https://l/a", "descriptionPlain": "Go",
                    "categories": {"location": "London", "allLocations": ["London", "Paris"]}, "lists": []}]
        with mock.patch.object(sources, "_request", return_value=payload):
            js = sources.lever("Acme", "acme")
        self.assertEqual(js[0].location, "London / Paris")

    def test_ashby(self):
        payload = {"jobs": [{"id": "z", "title": "AI Engineer", "location": "London", "jobUrl": "https://a/z",
                             "descriptionPlain": "LLMs", "secondaryLocations": [{"location": "Paris"}]}]}
        with mock.patch.object(sources, "_request", return_value=payload):
            js = sources.ashby("Acme", "acme")
        self.assertEqual(js[0].location, "London / Paris")

    def test_workday_pagination(self):
        page = {"total": 1, "jobPostings": [{"title": "Graduate ML Engineer", "externalPath": "/job/1",
                                             "locationsText": "London"}]}
        detail = {"jobPostingInfo": {"jobDescription": "<p>PyTorch</p>", "location": "London, UK"}}
        with mock.patch.object(sources, "_request", side_effect=[page, detail]):
            js = sources.workday("NV", "nv", host="nv.wd5.myworkdayjobs.com", site="Ext")
        self.assertEqual(js[0].description, "PyTorch")


class StoreTests(unittest.TestCase):
    def test_dedupe_across_sources(self):
        with tempfile.TemporaryDirectory() as d:
            s = SeenStore(Path(d) / "seen.json")
            s.add("manual:1", "Hudson River Trading", "Software Engineer (C++ or Python) - 2027 Grads", "u")
            s.save()
            s2 = SeenStore(Path(d) / "seen.json")
            self.assertTrue(s2.seen("gh:wehrtyou:99", "Hudson River Trading", "Software Engineer (C++ or Python) – 2027 Grads"))
            self.assertFalse(s2.seen("gh:wehrtyou:98", "Hudson River Trading", "Algorithm Developer - 2027 Grads"))

    def test_shortlist_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.md"
            report.write_shortlist(p, "2026-11-03", [{"source_id": "gh:a:1", "title": "T", "company": "C",
                                                       "location": "L", "url": "https://u", "why": "w"}], [])
            self.assertEqual(report.read_ids(p)[0]["id"], "gh:a:1")


class ConfigTests(unittest.TestCase):
    def test_boards_have_fetchers(self):
        for b in COMPANIES["board"]:
            self.assertIn(b["ats"], sources.FETCHERS, b)

    def test_seen_file_valid(self):
        root = Path(__file__).resolve().parent.parent
        json.loads((root / "seen_jobs.json").read_text())


if __name__ == "__main__":
    unittest.main()
