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

    def test_phd_or_masters_kept(self):
        for title, desc in [("Quantitative Researcher (PhD/Masters) 2027", ""), ("ML Engineer (MSc/PhD)", ""),
                            ("Graduate ML Engineer", "You hold a PhD/MSc in machine learning."),
                            ("Graduate ML Engineer", "PhD or Master's degree in ML required.")]:
            self.assertTrue(filters.evaluate(job(title, desc), CFG).keep, title + desc)
        for title, desc in [("Algorithm Developer - 2027 PhDs", ""), ("Research Scientist", "A PhD is required."),
                            ("Research Intern", "You are currently pursuing a PhD in ML.")]:
            self.assertFalse(filters.evaluate(job(title, desc), CFG).keep, title + desc)

    def test_uk_no_sponsorship_excluded(self):
        lseg = "Candidates should have the right to work in the UK without restrictions for the duration of the programme."
        self.assertFalse(filters.evaluate(job("Graduate Software Engineer", "We are unable to provide visa sponsorship."), CFG).keep)
        v = filters.evaluate(job("Engineering Graduate Programme (Backend)", lseg), CFG)
        self.assertTrue(v.keep, v.reasons)   # right-to-work wording alone is not an explicit "no sponsorship"
        self.assertIn("check", v.sponsorship)
        real = ("Applicants must already have the right to work in the UK for the full duration of the programme, "
                "without requiring visa sponsorship. We are unable to sponsor work visas for our Early Careers op")
        self.assertFalse(filters.evaluate(job("Graduate Machine Learning Engineer 2027", real, "Bristol, UK"), CFG).keep)
        graphcore = "graduate opportunities are permanent positions, and we are unable to provide visa sponsorship."
        self.assertFalse(filters.evaluate(job("Graduate Machine Learning Engineer 2027", graphcore, "Bristol, UK"), CFG).keep)

    def test_not_stated_or_mixed_kept(self):
        self.assertTrue(filters.evaluate(job("Graduate Software Engineer", "Python."), CFG).keep)
        v = filters.evaluate(job("Graduate Software Engineer",
                                 "We sponsor visas for full-time roles. We cannot sponsor visas for internships."), CFG)
        self.assertTrue(v.keep, v.reasons)
        self.assertEqual(v.sponsorship, "Mixed statements: check")

    def test_title_ignored_for_sponsorship(self):
        self.assertTrue(filters.evaluate(job("Graduate SWE (no sponsorship)", "Python."), CFG).keep)

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

    def test_live_run_regressions(self):
        self.assertFalse(filters.evaluate(job("Research Engineer", loc="Remote-Friendly (Travel-Required) | San Francisco, CA"), CFG).keep)
        self.assertFalse(filters.evaluate(job("Algorithm Developer (Quant Research & Trading) – 2027 PhDs"), CFG).keep)
        self.assertFalse(filters.evaluate(job("Equity Options Trader", loc="Amsterdam"), CFG).keep)
        self.assertTrue(filters.evaluate(job("Quantitative Trader/Researcher Graduate Programme 2027"), CFG).keep)
        v = filters.evaluate(job("Research Engineer, Pretraining", "Build large models."), CFG)
        self.assertIn("not labelled entry-level: check experience bar", v.flags)

    def test_europe_locations(self):
        for loc in ["Hamburg", "Lyon", "Eindhoven", "Bucharest", "Zug", "Aarhus, Denmark", "Remote, Europe"]:
            self.assertEqual(filters.region_of(loc, CFG), "eu", loc)
        for loc in ["Kyiv, Ukraine", "Porto Alegre, Brazil", "Belgrade, Serbia", "Toronto"]:
            self.assertEqual(filters.region_of(loc, CFG), "other", loc)
        self.assertEqual(filters.region_of("London, United Kingdom", CFG), "uk")

    def test_early_start_flag(self):
        v = filters.evaluate(job("Graduate ML Engineer", "the next cohort expected to start in January 2027"), CFG)
        self.assertIn("starts before you graduate (Sept 2027)", v.flags)

    def test_experience_ranges(self):
        self.assertTrue(filters.too_much_experience("2-3 years of full-time professional work experience", 2))
        self.assertTrue(filters.too_much_experience("3+ years of experience", 2))
        self.assertIsNone(filters.too_much_experience("1-3 years of experience", 2))
        self.assertIsNone(filters.too_much_experience("2+ years of experience", 2))

    def test_city_priority(self):
        b = lambda loc: filters.city_bonus(loc, CFG)
        self.assertGreater(b("London, UK"), b("Paris, France"))
        self.assertGreater(b("Paris, France"), b("Lisbon, Portugal"))
        self.assertGreater(b("Lisbon, Portugal"), b("Aachen, Germany"))
        self.assertEqual(b("Bristol; London"), b("London"))            # best location wins
        hub = filters.evaluate(job("Graduate ML Engineer", "pytorch", "Amsterdam"), CFG).score
        small = filters.evaluate(job("Graduate ML Engineer", "pytorch", "Assen, Netherlands"), CFG)
        self.assertTrue(small.keep)                                    # smaller cities still shown
        self.assertGreater(hub, small.score)

    def test_language(self):
        de = ("Wir suchen eine Person für unser Team. Sie arbeiten mit der Gruppe und die Kunden. " * 6)
        fr = ("Nous cherchons une personne pour notre équipe. Vous travaillez avec les clients et des données. " * 6)
        v_de = filters.evaluate(job("Junior Machine Learning Engineer", de, "Berlin"), CFG)
        v_fr = filters.evaluate(job("Junior Machine Learning Engineer", fr, "Paris"), CFG)
        self.assertIn("posting is in German", v_de.flags)
        self.assertFalse(any("posting is in" in f for f in v_fr.flags))   # French is spoken
        v = filters.evaluate(job("Graduate ML Engineer", "Fluent German is required. " + "The team works with you. " * 20, "Munich"), CFG)
        self.assertIn("asks for German", v.flags)

    def test_tier_whole_word(self):
        a = filters.evaluate(job("Graduate Data Scientist", "python", "London", company="ARM"), CFG).score
        b = filters.evaluate(job("Graduate Data Scientist", "python", "London", company="Pharma Ltd"), CFG).score
        self.assertGreater(a, b)

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


class FreehireTests(unittest.TestCase):
    def test_freehire_maps_and_skips_blank_company(self):
        page = {"data": [{"public_slug": "ml-eng-ramblr-1", "company": "ramblr", "title": "ML Engineer",
                          "location": "Munich", "url": "https://x/1?utm_source=freehire.me", "description": "PyTorch",
                          "source": "personio"},
                         {"public_slug": "x-2", "company": "", "title": "ML Engineer", "location": "Assen"}],
                "meta": {"total": 2}}
        with mock.patch.object(sources, "_request", return_value=page):
            js = sources.freehire(CFG)
        self.assertEqual([j.company for j in js], ["ramblr"])
        self.assertEqual(js[0].url, "https://x/1")

    def test_non_tech_engineers_dropped(self):
        for t in ["Graduate Quantity Surveyor", "Graduate Civil Engineer", "Graduate Structural Engineer"]:
            self.assertFalse(filters.evaluate(job(t), CFG).keep, t)
        for t in ["Graduate Software Engineer", "Junior AI Engineer", "Graduate Machine Learning Engineer",
                  "Quantitative Researcher", "Research Engineer", "Junior Data Engineer", "C++ Engineer"]:
            self.assertTrue(filters.evaluate(job(t), CFG).keep, t)

    def test_foreign_internship_words(self):
        self.assertTrue(filters.evaluate(job("Machine Learning Engineer H/F - Stage", loc="Paris"), CFG).internship)


class StoreTests(unittest.TestCase):
    def test_dedupe_across_sources(self):
        with tempfile.TemporaryDirectory() as d:
            s = SeenStore(Path(d) / "seen.json")
            s.add("manual:1", "Hudson River Trading", "Software Engineer (C++ or Python) - 2027 Grads", "u")
            s.save()
            s2 = SeenStore(Path(d) / "seen.json")
            self.assertTrue(s2.seen("gh:wehrtyou:99", "Hudson River Trading", "Software Engineer (C++ or Python) – 2027 Grads"))
            self.assertFalse(s2.seen("gh:wehrtyou:98", "Hudson River Trading", "Algorithm Developer - 2027 Grads"))

    def test_company_alias(self):
        self.assertEqual(fuzzy_key("IMC Trading", "Graduate Software Engineer (2027)"),
                         fuzzy_key("IMC", "Graduate Software Engineer (2027)"))

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
