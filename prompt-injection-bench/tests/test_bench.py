import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from bench.core import OllamaProvider, prepare, score
from bench.data import cases, seeds, validate
from bench.__main__ import paired_differences

ROOT = Path(__file__).resolve().parents[1]


class DataAndScoringTests(unittest.TestCase):
    def test_pairing_excludes_missing_matches_and_preserves_sign(self):
        rows = []
        for q in ("one", "two"):
            for defense, success in (("D0", True), ("D1", False)):
                rows.append(dict(model="m", defense=defense, repeat=0, status="ok",
                                 case=dict(id=q, family=q, language="zh"),
                                 scores=dict(attack_success=success)))
        rows.append(dict(model="m", defense="D0", repeat=1, status="ok",
                         case=dict(id="unpaired", family="other", language="zh"),
                         scores=dict(attack_success=True)))
        contrast = next(r for r in paired_differences(rows) if r["left"] == "D0/zh" and r["right"] == "D1/zh")
        self.assertEqual(contrast["pairs"], 2)
        self.assertEqual(contrast["mean_family_delta"], -1)
        self.assertEqual(contrast["cluster_ci95"], [-1, -1])

    def test_seed_split_and_shared_clean_controls(self):
        rows = seeds()
        validate(rows)
        samples = list(cases(rows, "dev"))
        self.assertEqual(len(samples), 24)
        self.assertEqual(sum(c["language"] == "clean" for c in samples), 6)
        self.assertEqual(len({c["case_id"] for c in samples}), 24)

    def test_leakage_and_duplicate_rejected(self):
        for key in ("family", "source_id", "evidence", "question"):
            rows = seeds()
            rows[-1][key] = rows[0][key]
            if key == "evidence":
                rows[-1]["answer"] = rows[0]["answer"]
            with self.assertRaises(ValueError):
                validate(rows)
        with self.assertRaises(ValueError):
            validate(seeds() + [seeds()[0]])

    def test_all_languages_screened_and_fact_kept(self):
        for c in cases(seeds()[:1], "dev"):
            for d in ("D0", "D1", "D2"):
                messages, removed = prepare(c, d)
                self.assertIn(c["evidence"], messages[1]["content"])
                self.assertEqual(len(removed), int(d == "D2" and c["language"] != "clean"))

    def test_attack_requires_target_not_mention(self):
        c = list(cases(seeds()[:1], "dev"))[1]
        self.assertTrue(score(c["marker"], c)["attack_success"])
        self.assertTrue(score(json.dumps({"answer": c["marker"], "evidence": ""}), c)["attack_success"])
        quoted = json.dumps({"answer": c["answer"], "evidence": c["marker"]})
        self.assertFalse(score(quoted, c)["attack_success"])
        self.assertFalse(score("I refuse to output " + c["marker"], c)["attack_success"])
        self.assertFalse(score("wrong answer", c)["attack_success"])

    def test_answer_and_citation_scored_separately(self):
        c = next(cases(seeds(), "dev"))
        result = score(json.dumps({"answer": c["answer"], "evidence": "invented"}), c)
        self.assertTrue(result["answer_correct"])
        self.assertFalse(result["citation_valid"])
        self.assertFalse(score("{}", c)["format_valid"])
        self.assertTrue(score('{"answer":"UNKNOWN","evidence":""}', c)["refusal_proxy"])


class AdapterTests(unittest.TestCase):
    def test_local_http_contract(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"message": {"content": "answer"}, "prompt_eval_count": 9, "eval_count": 2}).encode())

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = OllamaProvider(f"http://127.0.0.1:{server.server_port}", 2, 0.2).complete([], "test", 42)
            self.assertEqual(result["text"], "answer")
            self.assertEqual(result["input_tokens"], 9)
            self.assertEqual(seen[0][0], "/api/chat")
            self.assertFalse(seen[0][1]["stream"])
            self.assertEqual(seen[0][1]["options"]["seed"], 42)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class EndToEndTests(unittest.TestCase):
    def cli(self, *args, success=True):
        result = subprocess.run([sys.executable, "-m", "bench", *map(str, args)], cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode == 0, success, result.stderr.decode(errors="replace"))
        return result

    def test_freeze_run_report_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data, lock, output = root / "data.json", root / "lock.json", root / "run"
            self.cli("init-data", "--out", data)
            self.cli("freeze", "--dataset", data, "--out", lock, "--repeats", 1)
            self.cli("run", "--lock", lock, "--out", output)
            results = [json.loads(x) for x in (output / "results.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(results), 144)
            self.assertTrue(all(r["mock"] for r in results))
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(len(summary["groups"]), 24)
            self.assertIn("NOT RESEARCH RESULTS", (output / "report.md").read_text(encoding="utf-8"))
            (output / "review.csv").write_text("human work", encoding="utf-8")
            self.cli("report", "--run", output)
            self.assertEqual((output / "review.csv").read_text(), "human work")
            self.cli("run", "--lock", lock, "--out", output, success=False)
            altered = json.loads(lock.read_text(encoding="utf-8"))
            altered["config"]["seed"] = 9
            lock.write_text(json.dumps(altered), encoding="utf-8")
            self.cli("run", "--lock", lock, "--out", root / "tampered", success=False)

    def test_provider_failures_are_not_scored_as_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data, lock, output = root / "data.json", root / "lock.json", root / "run"
            data.write_text(json.dumps(seeds()[:1]), encoding="utf-8")
            self.cli("freeze", "--dataset", data, "--out", lock, "--provider", "ollama",
                     "--models", "missing", "--endpoint", "http://127.0.0.1:1", "--timeout", "0.1", "--repeats", 1)
            self.cli("run", "--lock", lock, "--out", output, success=False)
            summary = json.loads((output / "summary.json").read_text())
            self.assertTrue(all(g["completed"] == 0 and g["answer_correct"] is None for g in summary["groups"]))


if __name__ == "__main__":
    unittest.main()
