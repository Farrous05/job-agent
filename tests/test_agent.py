"""Offline tests: python3 -m unittest discover tests"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobagent import filters, pipeline, report, sources, tracker
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
        for loc in ["Hamburg", "Lyon", "Eindhoven", "Bucharest", "Zug", "Aarhus, Denmark", "Remote, Europe",
                    "Berlin, DE", "Lisbon, PT", "Madrid, ES"]:
            self.assertEqual(filters.region_of(loc, CFG), "eu", loc)
        for loc in ["Kyiv, Ukraine", "Porto Alegre, Brazil", "Belgrade, Serbia", "Toronto", "Vienna, VA",
                    "Paris, TX"]:
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

    def test_html_view(self):
        with tempfile.TemporaryDirectory() as d:
            md, data = Path(d) / "s.md", Path(d) / "data"
            (data / "candidates").mkdir(parents=True)
            (data / "candidates" / "x.json").write_text(json.dumps({"candidates": [
                {"source_id": "gh:a:1", "description": "About Acme. We are a company that does many things. " * 3
                 + "About the role: build ML models in PyTorch."}]}))
            report.write_shortlist(md, "2026-11-03", [{"source_id": "gh:a:1", "title": "ML Eng", "company": "Acme",
                                                        "location": "London", "url": "https://u", "why": "4/5: fits"}], [])
            out = Path(d) / "s.html"
            self.assertEqual(report.write_html(md, data, out, [md]), 1)
            page = out.read_text()
            self.assertIn('href="https://u"', page)
            self.assertIn("4/5 fit", page)
            self.assertIn("About the role: build ML models", page)

    def test_status_tracking(self):
        with tempfile.TemporaryDirectory() as d:
            st = SeenStore(Path(d) / "seen.json")
            st.set_status("gh:a:1", "applied", "Acme", "ML Eng", "https://u")      # unknown id gets added
            st.set_status("gh:a:2", "interested", "Beta", "SWE", "https://v")
            st.save()
            st2 = SeenStore(Path(d) / "seen.json")
            self.assertEqual(st2.statuses()["gh:a:1"], "applied")
            self.assertEqual(st2.applied_companies(), {"Acme"})
            page = report.applications_html(st2.data["jobs"])
            self.assertIn("Applied, waiting (1)", page)
            self.assertIn("Interested, not applied yet (1)", page)
            with self.assertRaises(ValueError):
                st2.set_status("gh:a:1", "hacked")

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


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.data = self.d / "data"
        self.short = self.d / "shortlist"
        self.short.mkdir()
        self.store = SeenStore(self.d / "seen.json")
        self.rd = pipeline.run_dir(self.data, "2026-11-03")
        jobs = [job("Graduate ML Engineer", "PyTorch LLM python " * 5, "London", company=f"Co{i}") for i in range(30)]
        for i, j in enumerate(jobs):
            j.source_id = f"t:{i}"
        jobs.append(job("Senior ML Engineer", "", "London", company="Old"))
        kept, rows, excl = pipeline.evaluate_all(jobs, CFG, self.store, set())
        pipeline.save_run(self.rd, kept, rows, excl, [])

    def tearDown(self):
        self.tmp.cleanup()

    def _score_all(self, fit_of=lambda i: 4):
        files = pipeline.make_batches(self.rd, pipeline.load_cache(self.data), size=12)
        for f in files:
            ids = [l[len("## id: "):] for l in f.read_text().splitlines() if l.startswith("## id: ")]
            out = self.rd / "scores" / (f.stem + ".jsonl")
            out.write_text("\n".join(json.dumps({"id": i, "fit": fit_of(int(i.split(":")[1])), "reason": "r"})
                                      for i in ids))
        return files

    def test_all_kept_roles_are_candidates(self):
        self.assertEqual(len(pipeline.load_candidates(self.rd)), 30)          # not capped at a top N
        rows = (self.rd / "all.jsonl").read_text().splitlines()
        self.assertEqual(len(rows), 31)
        self.assertIn("senior", json.loads(rows[-1])["reason"])

    def test_batches_merge_and_cache(self):
        files = self._score_all(lambda i: 5 if i < 3 else 2 if i > 20 else 3)
        self.assertEqual(len(files), 3)                                       # 30 roles / 12 per batch
        res = pipeline.merge_scores(self.rd, self.data, CFG, self.store, self.short)
        self.assertEqual(res["matches"], 30)
        self.assertEqual(res["unscored"], [])
        self.assertEqual(res["shortlisted"], 15)                               # fit>=3: 21 roles, cap 15
        m = json.loads((self.rd / "matches.json").read_text())["matches"]
        self.assertEqual([x["fit"] for x in m[:3]], [5, 5, 5])
        self.assertTrue(self.store.seen("t:0", "Co0", "Graduate ML Engineer"))
        # cached: a second batches call has nothing left to score
        self.assertEqual(pipeline.make_batches(self.rd, pipeline.load_cache(self.data), 12), [])

    def test_shortlist_merges_duplicates(self):
        c = pipeline.load_candidates(self.rd)
        for x in c[:3]:                                   # same company + title in 3 places
            x["company"], x["title"] = "Mako", "Graduate Software Engineer"
        (self.rd / "candidates.json").write_text(json.dumps({"candidates": c, "excluded_counts": {}}))
        self._score_all()
        pipeline.merge_scores(self.rd, self.data, CFG, self.store, self.short)
        rows = report.parse_shortlist(next(self.short.glob("*.md")))
        self.assertEqual(sum(1 for r in rows if r["company"] == "Mako"), 1)
        self.assertEqual(len(rows), 15)                   # still fills 15 distinct roles

    def test_remerge_updates_same_shortlist(self):
        self._score_all()
        a = pipeline.merge_scores(self.rd, self.data, CFG, self.store, self.short)["shortlist"]
        b = pipeline.merge_scores(self.rd, self.data, CFG, self.store, self.short)["shortlist"]
        self.assertEqual(a, b)
        self.assertEqual(len(list(self.short.glob("*.md"))), 1)
        # a new fetch (save_run without append) starts a new shortlist file
        pipeline.save_run(self.rd, pipeline.load_candidates(self.rd), [], {}, [])
        c = pipeline.merge_scores(self.rd, self.data, CFG, self.store, self.short)["shortlist"]
        self.assertNotEqual(a, c)

    def test_seen_roles_stay_in_all_matches_not_shortlist(self):
        self.store.add("t:0", "Co0", "Graduate ML Engineer", "u")      # shown in an earlier shortlist
        jobs = [job("Graduate ML Engineer", "PyTorch LLM python " * 5, "London", company=f"Co{i}") for i in range(3)]
        for i, j in enumerate(jobs):
            j.source_id = f"t:{i}"
        kept, rows, excl = pipeline.evaluate_all(jobs, CFG, self.store, set())
        pipeline.save_run(self.rd, kept, rows, excl, [])
        self.assertEqual(len(pipeline.load_candidates(self.rd)), 3)     # seen one still a candidate
        self._score_all()
        res = pipeline.merge_scores(self.rd, self.data, CFG, self.store, self.short)
        m = json.loads((self.rd / "matches.json").read_text())["matches"]
        self.assertEqual(len(m), 3)                                     # All matches shows it
        self.assertTrue(any(x.get("seen") for x in m))
        ids = {r["id"] for r in report.parse_shortlist(res["shortlist"])}
        self.assertNotIn("t:0", ids)                                    # Top picks doesn't

    def test_bad_score_lines_reported(self):
        (self.rd / "scores").mkdir(exist_ok=True)
        (self.rd / "scores" / "x.jsonl").write_text('{"id": "t:0", "fit": 9}\nnot json\n{"id": "t:1", "fit": 4}')
        scores, problems = pipeline.read_scores(self.rd)
        self.assertEqual(list(scores), ["t:1"])
        self.assertEqual(len(problems), 2)

    def test_import_filters_and_dedupes(self):
        items = [{"company": "Webco", "title": "Graduate Data Scientist", "location": "Paris", "url": "https://w/1"},
                 {"company": "Webco", "title": "Senior Data Scientist", "location": "Paris", "url": "https://w/2"},
                 {"company": "Co1", "title": "Graduate ML Engineer", "location": "London", "url": "https://dup"},
                 {"company": "NoLoc", "title": "Junior ML Engineer", "location": "", "url": "https://w/3"}]
        res = pipeline.import_jobs(items, CFG, self.store, set(), self.rd)
        self.assertEqual(res["added"], 2)                                      # dup + senior dropped
        c = {x["company"]: x for x in pipeline.load_candidates(self.rd)}
        self.assertIn("location not stated: check", c["NoLoc"]["flags"])
        again = pipeline.import_jobs(items, CFG, self.store, set(), self.rd)
        self.assertEqual(again["added"], 0)

    def test_recall_prefers_kept_copy(self):
        with (self.rd / "all.jsonl").open("a") as fh:
            fh.write(json.dumps({"id": "x:syd", "company": "Co7", "title": "Graduate ML Engineer", "location": "Sydney",
                                 "url": "", "source": "t", "kept": False, "reason": "location outside UK/EU"}) + "\n")
        res = pipeline.recall(self.rd, [{"company": "Co7", "title": "Graduate ML Engineer"}])
        self.assertEqual(len(res["found"]), 1)

    def test_recall(self):
        self._score_all()
        pipeline.merge_scores(self.rd, self.data, CFG, self.store, self.short)
        res = pipeline.recall(self.rd, [
            {"company": "Co5 Ltd", "title": "Graduate Machine Learning Engineer"},   # wording differs
            {"company": "Co6", "title": "Graduate ML Engineer"},
            {"company": "Old", "title": "Senior ML Engineer"},
            {"company": "Nowhere", "title": "Graduate ML Engineer"}])
        self.assertEqual(len(res["missing"]), 1)          # only Nowhere
        self.assertEqual(len(res["excluded"]), 1)         # Old: filtered (senior)
        self.assertEqual(len(res["found"]), 2)            # Co5 matched despite "Ltd" and "Machine Learning" wording
        self.assertTrue((self.rd / "recall_report.md").exists())


class TrackerTests(unittest.TestCase):
    def test_reminders_and_stats(self):
        with tempfile.TemporaryDirectory() as d:
            st = SeenStore(Path(d) / "seen.json")
            from datetime import date, timedelta
            soon = (date.today() + timedelta(days=4)).strftime("%d %b %Y")
            st.add("a", "Acme", "ML Eng", "u", extra={"deadline": soon, "families": ["ml"], "region": "uk"})
            st.set_status("a", "interested")
            st.add("b", "Beta", "SWE", "u", extra={"families": ["software"], "region": "eu", "source": "freehire"})
            st.set_status("b", "applied")
            st.data["jobs"]["b"]["status_date"] = (date.today() - timedelta(days=20)).isoformat()
            st.add("c", "Gamma", "DS", "u", extra={"families": ["data_science"], "region": "uk"})
            st.set_status("c", "applied")
            st.set_status("c", "interviewing", note="call Tue")
            rem = tracker.reminders(st)
            self.assertTrue(any(r.startswith("Closes in 4 days: Acme") for r in rem), rem)
            self.assertTrue(any("No reply for 20 days: Beta" in r for r in rem), rem)
            s = tracker.stats(st)
            self.assertEqual(s["applied_total"], 2)
            self.assertEqual(s["interview_total"], 1)
            self.assertEqual(s["by"]["family"]["data_science"]["interviews"], 1)
            self.assertEqual(st.data["jobs"]["c"]["note"], "call Tue")
            self.assertEqual([h[1] for h in st.data["jobs"]["c"]["history"]], ["applied", "interviewing"])
            self.assertIn("Stats", report.stats_html(s))


class CleanupTests(unittest.TestCase):
    def test_aliases_and_recruiters(self):
        j = job("Software Engineer - Python", company="Wehrtyou")
        pipeline.normalize_company(j, COMPANIES)
        self.assertEqual(j.company, "Hudson River Trading")
        r = job("Junior Data Scientist", "python", company="Harnham - Data & Analytics Recruitment")
        pipeline.normalize_company(r, COMPANIES)
        c = pipeline.candidate(filters.evaluate(r, CFG), r, CFG, SeenStore(Path(tempfile.mkdtemp()) / "s.json"), set())
        self.assertTrue(any("recruiter" in f for f in c["flags"]))

    def test_role_text_skips_boilerplate(self):
        t = "About Acme. " + "We are a great company with values. " * 10 + "What you'll do: train models."
        self.assertTrue(pipeline.role_text(t).startswith("What you'll do"))


class GitSaveTests(unittest.TestCase):
    def test_save_in_temp_repo(self):
        import subprocess
        from jobagent import gitsave
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
            subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
            self.assertEqual(gitsave.save(Path(d), "x"), "nothing new to save")
            (Path(d) / "a.txt").write_text("hi")
            self.assertEqual(gitsave.save(Path(d), "x", push=False), "saved locally")
            (Path(d) / "b.txt").write_text("hi")
            self.assertIn("push failed", gitsave.save(Path(d), "x"))      # no remote: reported, not raised


class NotifyTests(unittest.TestCase):
    def test_summary_text(self):
        from jobagent import notify
        rows = [{"title": "ML Researcher (New Grad)", "company": "Jane Street", "why": "5/5: deep learning"},
                {"title": "Junior AI Engineer", "company": "techwolf", "why": "4/5: LLM features"}]
        title, msg, prio = notify.run_summary(None, rows, ["Closes in 3 days: Citi: Junior SWE"])
        self.assertEqual(title, "2 new jobs picked")
        self.assertIn("Jane Street (5/5)", msg)
        self.assertIn("Closes in 3 days", msg)
        self.assertEqual(prio, "high")
        self.assertEqual(notify.run_summary(None, [], [])[1], "Nothing new today.")

    def test_send_posts_to_ntfy(self):
        from jobagent import notify
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config").mkdir()
            notify.setup(Path(d))
            class Resp:
                status = 200
                def __enter__(self): return self
                def __exit__(self, *a): return False
            with mock.patch.object(notify.urllib.request, "urlopen", return_value=Resp()) as u:
                self.assertEqual(notify.send(Path(d), "Title", "Body é"), "sent")
            req = u.call_args[0][0]
            self.assertTrue(req.full_url.startswith("https://ntfy.sh/jobagent-"))
            self.assertEqual(req.data, "Body é".encode())

    def test_send_retries_rate_limit(self):
        from jobagent import notify
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config").mkdir()
            notify.setup(Path(d))
            err = notify.urllib.error.HTTPError("u", 429, "Too Many", {}, None)
            class Resp:
                status = 200
                def __enter__(self): return self
                def __exit__(self, *a): return False
            with mock.patch.object(notify.urllib.request, "urlopen", side_effect=[err, Resp()]), \
                 mock.patch.object(notify.time, "sleep"):
                self.assertEqual(notify.send(Path(d), "T", "m"), "sent")

    def test_telegram_setup_and_send(self):
        from jobagent import notify
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config").mkdir()
            calls = []
            def fake(token, method, params):
                calls.append((method, params))
                if method == "getMe":
                    return {"ok": True, "result": {"username": "fares_jobs_bot"}}
                if method == "getUpdates":
                    return {"ok": True, "result": [{"message": {"chat": {"id": 42, "type": "private",
                                                                          "first_name": "Fares"}}}]}
                return {"ok": True}
            with mock.patch.object(notify, "_tg", side_effect=fake):
                self.assertIn("Saved", notify.telegram_setup(Path(d), " 123:abc "))
                self.assertEqual(notify.send(Path(d), "3 new jobs picked", "• A"), "sent (Telegram)")
            self.assertEqual(calls[-1], ("sendMessage", {"chat_id": 42, "text": "3 new jobs picked\n• A",
                                                         "disable_web_page_preview": "true"}))
            self.assertEqual(json.loads((Path(d) / "config" / "telegram.json").read_text())["chat_id"], 42)

    def test_telegram_no_message_yet(self):
        from jobagent import notify
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config").mkdir()
            fake = lambda t, m, p: {"ok": True, "result": {"username": "b"}} if m == "getMe" else {"ok": True, "result": []}
            with mock.patch.object(notify, "_tg", side_effect=fake):
                self.assertIn("send any message", notify.telegram_setup(Path(d), "x"))

    def test_no_topic(self):
        from jobagent import notify
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config").mkdir()
            self.assertIn("notify-setup", notify.send(Path(d), "t", "m"))


class ResetTests(unittest.TestCase):
    def test_reset_archives_and_keeps_marked(self):
        import shutil, subprocess, sys
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name in ("jobagent", "config"):
                shutil.copytree(root / name, d / name, ignore=shutil.ignore_patterns("__pycache__", "ntfy_topic", "telegram.json"))
            (d / "shortlist").mkdir()
            (d / "shortlist" / "2026-11-04.md").write_text("# x\n")
            (d / "data" / "runs" / "2026-11-04").mkdir(parents=True)
            (d / "data" / "score_cache.json").write_text("{}")
            st = SeenStore(d / "seen_jobs.json")
            st.add("a", "A", "T", "u"); st.add("b", "B", "T", "u"); st.set_status("b", "applied"); st.save()
            r = subprocess.run([sys.executable, "-m", "jobagent", "reset", "--yes"], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(list(json.loads((d / "seen_jobs.json").read_text())["jobs"]), ["b"])
            self.assertEqual(list((d / "shortlist").glob("*.md")), [])
            self.assertFalse((d / "data" / "score_cache.json").exists())
            arch = next((d / "archive").iterdir())
            self.assertTrue((arch / "shortlist" / "2026-11-04.md").exists())
            self.assertTrue((arch / "score_cache.json").exists())
