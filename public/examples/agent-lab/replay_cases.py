"""Run the project and fault scenarios used by the portfolio replay."""

import argparse
import json
from pathlib import Path

from project_walkthrough import DOCUMENTS, answer, build_index
from retrieval_trace import trace_case


def project_replay():
    index = build_index()
    sources = {row["id"]: row for row in DOCUMENTS}
    cases = []
    for version in ("v2", "v1", "v9"):
        result = answer("E102", version, index=index)
        expected = {"v2": ["csv-v2"], "v1": ["csv-v1"], "v9": []}[version]
        actual = [row["id"] for row in result["sources"]]
        assert actual == expected, (version, result)
        cases.append({
            "id": version,
            "query": "E102",
            "version": version,
            "status": result["status"],
            "expected_ids": expected,
            "answer": result["answer"],
            "trace": {
                "version_ids": [row["id"] for row in index if row["version"] == version],
                "hit_ids": actual,
                "context_ids": actual,
                "first_failed_stage": None,
            },
        })
    for fault, stage in (("wrong_version", "metadata_filter"), ("context_dropped", "context_assembly")):
        trace = trace_case(fault)
        assert trace["first_failed_stage"] == stage, trace
        assert trace["indexed"] and trace["source_has_field"] and not trace["context_ids"], trace
        cases.append({
            "id": fault,
            "query": "customer_id",
            "version": "v2",
            "status": "injected_failure",
            "expected_ids": ["csv-v2"],
            "answer": "本次上下文没有保留预期证据。",
            "trace": trace,
        })
    return {"cases": cases, "sources": sources}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--case", choices=("v2", "v1", "v9", "wrong_version", "context_dropped"))
    group.add_argument("--write", action="store_true", help="Refresh the checked-in replay results")
    group.add_argument("--check", action="store_true", help="Check the saved results against a fresh run")
    args = parser.parse_args()
    report = project_replay()
    output = Path(__file__).with_name("replay_cases.json")
    if args.check:
        if json.loads(output.read_text(encoding="utf-8")) != report:
            parser.exit(1, "Saved replay results are stale. Run replay_cases.py --write.\n")
        print(f"PASS {len(report['cases'])} replay scenarios")
    elif args.write:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved {len(report['cases'])} replay scenarios")
    else:
        result = next(case for case in report["cases"] if case["id"] == args.case) if args.case else report
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
