"""Non-destructive scorer comparison; never overwrites original scores or labels."""
import hashlib
import json
from .core import score


def rescore_run(source, destination):
    raw = (source / "results.jsonl").read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    rescored = []
    for row in rows:
        new = score(row["response"]["text"], row["case"]) if row["status"] == "ok" else None
        old = row["scores"]
        changed = [key for key in ("attack_success", "answer_correct", "citation_valid", "refusal_proxy", "format_valid")
                   if old is not None and new is not None and old[key] != new[key]]
        rescored.append(dict(id=row["id"], old_scores=old, new_scores=new, changed_metrics=changed))
    value = dict(source_sha256=hashlib.sha256(raw).hexdigest(), reviewer_type="automated_rescore",
                 human_review_complete=False, records=rescored)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
