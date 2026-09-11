import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time
import urllib.error

from . import __version__
from .core import MockProvider, OllamaProvider, prepare, score, RULES, BASE, BOUNDARY
from .data import cases, digest, seeds, validate
from .expanded import expanded_seeds


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_hash():
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(Path(__file__).parent.glob("*.py"))})


def freeze(args):
    rows = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    validate(rows)
    if not any(r["split"] == args.split for r in rows):
        raise ValueError("No cases in selected split")
    if args.repeats < 1 or args.timeout <= 0 or args.temperature < 0:
        raise ValueError("Invalid repeat count, timeout or temperature")
    if len(set(args.models)) != len(args.models):
        raise ValueError("Model names must be unique")
    config = dict(version=__version__, provider=args.provider, models=args.models,
                  defenses=["D0", "D1", "D2"], repeats=args.repeats, split=args.split,
                  seed=args.seed, temperature=args.temperature, timeout=args.timeout,
                  endpoint=args.endpoint, dataset=rows, dataset_sha256=digest(rows),
                  code_sha256=source_hash(), screening_rules=RULES,
                  prompts={"base": BASE, "boundary": BOUNDARY})
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as f:
        json.dump({"sha256": digest(config), "config": config}, f, ensure_ascii=False, indent=2)
    count = len(list(cases(rows, args.split))) * len(args.models) * 3 * args.repeats
    print(f"Frozen {count} calls to {destination}; provider={args.provider}")


def run(args):
    lock = json.loads(Path(args.lock).read_text(encoding="utf-8"))
    config = lock["config"]
    if digest(config) != lock["sha256"] or digest(config["dataset"]) != config["dataset_sha256"]:
        raise ValueError("Lock integrity check failed")
    if source_hash() != config["code_sha256"]:
        raise ValueError("Code changed since freeze; create a new lock")
    validate(config["dataset"])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    dump(out / "lock.json", lock)
    dump(out / "environment.json", {"python": sys.version, "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                   "mock": config["provider"] == "mock", "platform": sys.platform})
    provider = MockProvider() if config["provider"] == "mock" else OllamaProvider(config["endpoint"], config["timeout"], config["temperature"])
    jobs = [(case, model, defense, repeat) for case in cases(config["dataset"], config["split"])
            for model in config["models"] for defense in config["defenses"] for repeat in range(config["repeats"])]
    random.Random(config["seed"]).shuffle(jobs)
    failures = 0
    with (out / "results.jsonl").open("w", encoding="utf-8") as f:
        for i, (case, model, defense, repeat) in enumerate(jobs):
            start = time.perf_counter()
            messages, removed = prepare(case, defense)
            record = {"id": f"{case['case_id']}:{model}:{defense}:{repeat}", "case": case,
                      "model": model, "defense": defense, "repeat": repeat,
                      "mock": config["provider"] == "mock", "messages": messages, "removed": removed}
            try:
                response = provider.complete(messages, model, config["seed"] + repeat)
                record.update(status="ok", response=response, scores=score(response["text"], case))
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
                failures += 1
                record.update(status="error", error_type=type(exc).__name__, scores=None)
            record["elapsed_s"] = round(time.perf_counter() - start, 6)
            record["estimated_cost_usd"] = None  # Local energy/hardware cost is not measured.
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            if (i + 1) % 20 == 0 or i + 1 == len(jobs):
                print(f"{i+1}/{len(jobs)} completed; errors={failures}", flush=True)
    report(out)
    if failures:
        raise ValueError(f"{failures} provider errors; preserved logs in {out}")


def cluster_interval(rows, key):
    groups = {}
    for row in rows:
        groups.setdefault(row["case"]["family"], []).append(int(row["scores"][key]))
    values = [statistics.mean(v) for v in groups.values()]
    if len(values) < 2:
        return None
    rng = random.Random(1701)
    samples = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(1000))
    return [samples[24], samples[974]]


def paired_differences(rows):
    """Pair conditions within question/repeat, then bootstrap question families."""
    if any("variant" in r["case"] for r in rows):
        variants = {}
        for r in rows:
            variants.setdefault(r["case"].get("variant", "legacy"), []).append(r)
        output = []
        for variant, group in sorted(variants.items()):
            stripped = [dict(r, case={k: v for k, v in r["case"].items() if k != "variant"}) for r in group]
            output.extend(dict(c, variant=variant) for c in paired_differences(stripped) if c["pairs"])
        return output
    index = {(r["model"], r["defense"], r["case"]["language"], r["case"]["id"], r["repeat"]): r
             for r in rows if r["status"] == "ok"}
    output = []
    for model in sorted({r["model"] for r in rows}):
        contrasts = []
        for language in ("clean", "zh", "en", "mixed"):
            for defense in ("D1", "D2"):
                metric = "answer_correct" if language == "clean" else "attack_success"
                contrasts.append((("D0", language), (defense, language), metric))
        for defense in ("D0", "D1", "D2"):
            for language in ("en", "mixed"):
                contrasts.append(((defense, "zh"), (defense, language), "attack_success"))
        for (left_d, left_l), (right_d, right_l), metric in contrasts:
            groups = {}
            pairs = 0
            for (m, d, lang, q, repeat), left in index.items():
                if (m, d, lang) != (model, left_d, left_l):
                    continue
                right = index.get((model, right_d, right_l, q, repeat))
                if right is not None:
                    delta = int(right["scores"][metric]) - int(left["scores"][metric])
                    groups.setdefault(left["case"]["family"], []).append(delta)
                    pairs += 1
            values = [statistics.mean(v) for v in groups.values()]
            interval = None
            if len(values) > 1:
                rng = random.Random(1701)
                samples = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(1000))
                interval = [samples[24], samples[974]]
            output.append(dict(model=model, left=f"{left_d}/{left_l}", right=f"{right_d}/{right_l}",
                               metric=metric, direction="right minus left", pairs=pairs, families=len(values),
                               mean_family_delta=statistics.mean(values) if values else None,
                               cluster_ci95=interval))
    return output


def report(out):
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    groups = {}
    for row in rows:
        groups.setdefault((row["model"], row["defense"], row["case"]["language"], row["case"].get("variant", "legacy")), []).append(row)
    summary = []
    for (model, defense, language, variant), all_rows in sorted(groups.items()):
        ok = [r for r in all_rows if r["status"] == "ok"]
        entry = dict(model=model, defense=defense, language=language, variant=variant, attempted=len(all_rows),
                     completed=len(ok), errors=len(all_rows)-len(ok))
        for key in ("attack_success", "answer_correct", "citation_valid", "refusal_proxy", "format_valid"):
            meaningful = bool(ok) and not (key == "attack_success" and language == "clean")
            entry[key] = statistics.mean(int(r["scores"][key]) for r in ok) if meaningful else None
            entry[key + "_cluster_ci95"] = cluster_interval(ok, key) if meaningful else None
        entry["latency_mean_s"] = statistics.mean(r["elapsed_s"] for r in ok) if ok else None
        entry["removed_chunks"] = sum(len(r["removed"]) for r in all_rows)
        labeled = [r for r in all_rows if "gold_benign_indices" in r["case"]]
        benign_total = sum(len(r["case"]["gold_benign_indices"]) for r in labeled)
        benign_removed = sum(len({x["index"] for x in r["removed"]} & set(r["case"]["gold_benign_indices"])) for r in labeled)
        entry["benign_chunk_removal_rate"] = benign_removed / benign_total if benign_total else None
        entry["evidence_loss_rate"] = statistics.mean(bool({x["index"] for x in r["removed"]} & set(r["case"]["gold_evidence_indices"])) for r in labeled) if labeled else None
        entry["answer_strict"] = statistics.mean(r["scores"].get("answer_strict", r["scores"]["answer_correct"]) for r in ok) if ok else None
        summary.append(entry)
    mock = any(r["mock"] for r in rows)
    dump(out / "summary.json", {"mock": mock, "automated_unreviewed": True, "groups": summary})
    dump(out / "comparisons.json", {"mock": mock, "direction": "right minus left", "comparisons": paired_differences(rows)})
    title = "MOCK DEMO — NOT RESEARCH RESULTS" if mock else "Automated results — pending human review"
    lines = [f"# {title}", "", "See scorer_version in raw scores. v0.2 uses explicit aliases and whole-answer matching; refusal remains a proxy.",
             "Errors are excluded from rate denominators and reported separately. Cost is not measured.", "",
             "| Model | Defense | Variant | Language | OK / attempted | ASR | Accuracy | Refusal proxy | Evidence loss |",
             "|---|---|---|---|---:|---:|---:|---:|---:|"]
    def percent(value):
        return "N/A" if value is None else f"{100*value:.1f}%"
    for s in summary:
        lines.append(f"| {s['model']} | {s['defense']} | {s['variant']} | {s['language']} | {s['completed']}/{s['attempted']} | {percent(s['attack_success'])} | {percent(s['answer_correct'])} | {percent(s['refusal_proxy'])} | {percent(s['evidence_loss_rate'])} |")
    lines += ["", "Cluster-bootstrap intervals are in summary.json (1,000 draws, question-family unit).",
              "Paired defense/language contrasts are in comparisons.json (right minus left, equal family weights).",
              "Tiny pilot intervals are unstable; clean controls are shared, not counted once per attack language.",
              "Review raw outputs in review.csv. Human labels do not automatically alter the frozen automated report."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    review = out / "review.csv"
    if not review.exists():
        with review.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "question", "expected", "output", "auto_scores", "human_attack_success", "human_correct", "human_refusal", "notes", "gold_evidence", "input_chunks", "removed_chunks", "reviewer_type", "reviewer_id"])
            for r in rows:
                writer.writerow([r["id"], r["case"]["question"], r["case"]["answer"],
                                 r.get("response", {}).get("text", ""), json.dumps(r["scores"]), "", "", "", "",
                                 r["case"]["evidence"], json.dumps(r["case"]["chunks"], ensure_ascii=False),
                                 json.dumps(r["removed"], ensure_ascii=False), "", ""])
    print(f"Report: {out / 'report.md'}")


def main():
    parser = argparse.ArgumentParser(description="Multilingual injection research pilot (Python 3.10+)")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init-data")
    init.add_argument("--out", default="data/seed.json")
    init.add_argument("--expanded", action="store_true")
    lock = sub.add_parser("freeze")
    lock.add_argument("--dataset", default="data/dev-v02.json")
    lock.add_argument("--out", required=True)
    lock.add_argument("--provider", choices=["mock", "ollama"], default="mock")
    lock.add_argument("--models", nargs="+", default=["mock-a", "mock-b"])
    lock.add_argument("--split", choices=["dev", "test"], default="dev")
    lock.add_argument("--repeats", type=int, default=3)
    lock.add_argument("--seed", type=int, default=42)
    lock.add_argument("--temperature", type=float, default=0.2)
    lock.add_argument("--timeout", type=float, default=120)
    lock.add_argument("--endpoint", default="http://localhost:11434")
    execute = sub.add_parser("run")
    execute.add_argument("--lock", required=True)
    execute.add_argument("--out", required=True)
    summarize = sub.add_parser("report")
    summarize.add_argument("--run", required=True)
    rescore = sub.add_parser("rescore")
    rescore.add_argument("--run", required=True)
    rescore.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init-data":
            path = Path(args.out)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as f:
                json.dump(expanded_seeds() if args.expanded else seeds(), f, ensure_ascii=False, indent=2)
            print(path)
        elif args.command == "freeze":
            freeze(args)
        elif args.command == "run":
            run(args)
        elif args.command == "rescore":
            from .review import rescore_run
            rescore_run(Path(args.run), Path(args.out))
        else:
            report(Path(args.run))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
