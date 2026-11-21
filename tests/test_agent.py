import contextlib
import io
import re
import unittest
from contextlib import redirect_stdout

import agent
import backtest


class DataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = agent.load_parts()
        cls.estimates = agent.load_estimates()

    def test_sizes_and_ids(self):
        self.assertEqual(len(self.parts), 40)
        self.assertEqual(len(self.estimates), 60)
        self.assertTrue(all(re.fullmatch(r"PT-\d{4}", p["part_id"]) for p in self.parts))
        self.assertEqual(len({e["estimate_id"] for e in self.estimates}), 60)

    def test_estimates_reference_master(self):
        ids = {p["part_id"] for p in self.parts}
        for e in self.estimates:
            self.assertIn(e["part_id"], ids)
            self.assertGreater(e["unit_price"], 0)
            self.assertGreater(e["lead_time_days"], 0)


class RetrievalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = agent.load_parts()
        cls.estimates = agent.load_estimates()
        cls.retriever = agent.Retriever(cls.parts)

    def test_known_queries_return_expected_neighbour(self):
        cases = {
            "L bracket SUS304 t2.0 60x60": "PT-1004",
            "S45C shaft dia20 L250 keyway induction hardened": "PT-1013",
            "POM resin bushing ID10 OD14 L20": "PT-1019",
            "hex spacer M5 L20 SUS303 male-female": "PT-1024",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                hits = self.retriever.search(query, k=3)
                self.assertEqual(hits[0][1]["part_id"], expected)

    def test_same_family_ranks_above_other_families(self):
        hits = self.retriever.search("mounting plate A5052 120x90 t5 M5 tapped", k=3)
        self.assertTrue(all(p["category"] == "Plate" for _, p in hits))

    def test_unrelated_query_returns_nothing(self):
        self.assertEqual(self.retriever.search("zzzz qqqq", k=5), [])


class DraftCitationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = agent.load_parts()
        cls.estimates = agent.load_estimates()

    def assert_fully_cited(self, draft):
        hits = {h["estimate"]["estimate_id"]: h["estimate"] for h in draft["hits"]}
        self.assertTrue(draft["figures"])
        for fig in draft["figures"]:
            self.assertGreaterEqual(len(fig["sources"]), 1, fig["label"])
            for src in fig["sources"]:
                self.assertIn(src, hits)
            field = "lead_time_days" if "lead_time" in fig["label"] else "unit_price"
            self.assertIn(fig["value"], [hits[s][field] for s in fig["sources"]])

    def test_every_figure_cites_a_retrieved_source(self):
        for part in self.parts:
            with self.subTest(part=part["part_id"]):
                draft = agent.draft_estimate(agent.part_text(part), self.parts, self.estimates, qty=100)
                self.assert_fully_cited(draft)

    def test_range_brackets_suggested_price(self):
        draft = agent.draft_estimate("flange SUS304 OD80 t12", self.parts, self.estimates)
        values = {f["label"]: f["value"] for f in draft["figures"]}
        self.assertLessEqual(values["price_range_low"], values["suggested_unit_price"])
        self.assertLessEqual(values["suggested_unit_price"], values["price_range_high"])

    def test_printed_draft_has_no_uncited_figure_lines(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            agent.main(["L bracket SUS304 t2.0 60x60", "--qty", "100"])
        figure_lines = [l for l in buf.getvalue().splitlines() if l.startswith("- ")]
        self.assertEqual(len(figure_lines), 4)
        for line in figure_lines:
            self.assertRegex(line, r"<- EST-\d{4} \(PT-\d{4}, ")

    def test_cli_rejects_non_positive_numbers(self):
        for args in (["--qty", "-1"], ["--qty", "0"], ["-k", "-1"], ["-k", "0"]):
            with self.subTest(args=args), redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                agent.main(["L bracket SUS304 t2.0 60x60", *args])

    def test_excluded_estimates_are_not_used(self):
        hidden = next(e["estimate_id"] for e in self.estimates if e["part_id"] == "PT-1004")
        query = "L bracket SUS304 t2.0 60x60"
        full = agent.draft_estimate(query, self.parts, self.estimates)
        self.assertIn(hidden, [h["estimate"]["estimate_id"] for h in full["hits"]])
        draft = agent.draft_estimate(query, self.parts, self.estimates, exclude_ids={hidden})
        self.assertNotIn(hidden, [h["estimate"]["estimate_id"] for h in draft["hits"]])


class BacktestTest(unittest.TestCase):
    def test_backtest_hit_rate_and_determinism(self):
        first = backtest.run_backtest()
        second = backtest.run_backtest()
        self.assertEqual(first["cases"], 60)
        self.assertGreaterEqual(first["hit_rate"], 0.5)
        self.assertEqual(first, second)

    def test_backtest_cli_prints_metrics(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            backtest.main([])
        out = buf.getvalue()
        for text in ("cases:", "median absolute % error:", "hit rate within +/-20%:"):
            self.assertIn(text, out)


if __name__ == "__main__":
    unittest.main()
