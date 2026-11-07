"""标准库回归与十篇示例复验；不调用网络或真实模型。"""
import argparse
import io
import json
import os
import platform
import re
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile

from knowledge_tool import search_knowledge
from project_walkthrough import answer, build_index, retrieve
from rag_evaluation import CASES, evaluate, summary
from tool_safety import lookup_with_retry
from workflow_agent import fixed_workflow

FOLDER = Path(__file__).resolve().parent
ARTICLE_MAP = json.loads((FOLDER / "article-map.json").read_text(encoding="utf-8"))


class RetrievalRegression(unittest.TestCase):
    def test_error_code_and_field_fragments_do_not_become_evidence(self):
        for query in ("E10", "E1", "id", "customer"):
            with self.subTest(query=query):
                self.assertEqual(retrieve(query, "v2"), [])
                self.assertEqual(search_knowledge(query, "v2"), [])
                self.assertEqual(fixed_workflow(query, "v2")["status"], "no_evidence")

    def test_exact_identifiers_and_versions(self):
        for query, version, expected in (
            ("E102", "v1", ["csv-v1"]),
            ("e102", "v2", ["csv-v2"]),
            ("customer_id", " v2 ", ["csv-v2"]),
            ("user_id", "v2", []),
            ("E102", "v9", []),
            ("退款", "v2", []),
        ):
            with self.subTest(query=query, version=version):
                self.assertEqual([row["id"] for row in search_knowledge(query, version)], expected)

    def test_invalid_inputs_are_rejected_by_both_entries(self):
        for params in (
            {"query": "", "version": "v2"},
            {"query": None, "version": "v2"},
            {"query": "E102", "version": " "},
            {"query": "E102", "version": 2},
            *({"query": "E102", "version": "v2", "top_k": value}
              for value in (0, 6, True, "3")),
        ):
            for entry in (retrieve, search_knowledge):
                with self.subTest(entry=entry.__name__, params=params):
                    with self.assertRaises(ValueError):
                        entry(**params)

    def test_empty_index_does_not_silently_rebuild(self):
        self.assertEqual(retrieve("E102", "v2", index=[]), [])
        self.assertEqual(answer("E102", "v2", index=[])["status"], "insufficient_evidence")

    def test_project_and_tool_share_all_evaluation_results(self):
        index = build_index()
        for case in CASES:
            for top_k in (1, 2):
                with self.subTest(case=case["id"], top_k=top_k):
                    project_hits = retrieve(case["query"], case["version"], top_k=top_k, index=index)
                    expected = [{key: value for key, value in hit.items() if key != "score"}
                                for hit in project_hits]
                    self.assertEqual(search_knowledge(case["query"], case["version"], top_k), expected)

    def test_tool_preserves_public_schema_and_result_isolation(self):
        hit = search_knowledge("E102", "v2")[0]
        self.assertEqual(set(hit), {"id", "version", "error_code", "text", "source"})
        hit["text"] = "不应污染下次查询"
        self.assertIn("customer_id", search_knowledge("E102", "v2")[0]["text"])

    def test_no_evidence_stays_empty_through_retry_and_workflow(self):
        self.assertEqual(fixed_workflow("E102", "v9")["status"], "no_evidence")
        self.assertEqual(fixed_workflow("E102", None)["calls"], 0)
        self.assertEqual(lookup_with_retry({"query": "E10", "version": "v2"}, fail_first=True),
                         {"status": "ok", "attempts": 2, "ids": []})

    def test_evaluation_keeps_known_failure_visible(self):
        index = build_index()
        for split, expected in (("dev", "3/3"), ("holdout", "6/7")):
            records = evaluate([case for case in CASES if case["split"] == split], index, top_k=2)
            self.assertEqual(summary(records)["passed"], expected)
            self.assertEqual([row["id"] for row in records if not row["passed"]],
                             [] if split == "dev" else ["h2"])


def run_scripts():
    records = []
    scripts = [(item["script"], "current-series") for item in ARTICLE_MAP]
    scripts += [(name, "shared-tool") for name in
                ("knowledge_tool.py", "eval_tools.py", "retrieval_demo.py", "citation_checks.py")]
    for script, suite in scripts:
        completed = subprocess.run(
            [sys.executable, str(FOLDER / script)], cwd=FOLDER,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        record = {"command": f"python {script}", "suite": suite,
                  "exitCode": completed.returncode, "stdout": completed.stdout.rstrip()}
        if completed.stderr:
            record["stderr"] = completed.stderr.rstrip()
        records.append(record)
        print(f"{'PASS' if completed.returncode == 0 else 'FAIL'} {script}")
    return records


def check_assets():
    """仓库模式核查文章与下载包；解压运行示例时无需使用此选项。"""
    repo = FOLDER.parents[2]
    for item in ARTICLE_MAP:
        article = repo / "src/content/posts" / f"{item['slug']}.md"
        blocks = re.findall(r"^```python[^\n]*\n(.*?)^```", article.read_text(encoding="utf-8"), re.M | re.S)
        if len(blocks) != 1 or blocks[0].strip() != (FOLDER / item["script"]).read_text(encoding="utf-8").strip():
            raise ValueError(f"文章与脚本不一致: {item['slug']}")
    files = {path.relative_to(FOLDER).as_posix(): path for path in FOLDER.rglob("*")
             if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}
    with ZipFile(FOLDER.parent / "agent-lab.zip") as package:
        expected_names = {f"agent-lab/{name}" for name in files}
        if set(package.namelist()) != expected_names:
            raise ValueError("下载包文件列表与源目录不一致")
        for name, path in files.items():
            if package.read(f"agent-lab/{name}") != path.read_bytes():
                raise ValueError(f"下载包内容未同步: {name}")
    print(f"PASS {len(ARTICLE_MAP)} 篇文章代码与 {len(files)} 个打包文件一致")


def write_records(records):
    target = FOLDER / "verification.json"
    previous = json.loads(target.read_text(encoding="utf-8"))
    history = previous.get("historicalVerification") or {
        "verifiedDate": previous["verifiedDate"], "python": previous["python"],
        "packages": previous.get("packages", {}),
        "scope": "历史补充实验的原始记录；本次未重新安装或验证第三方框架。",
        "runs": [run for run in previous["runs"] if run.get("suite") == "earlier-experiments"],
    }
    now = datetime.now(timezone(timedelta(hours=8)))
    verification = {
        "verifiedDate": now.date().isoformat(), "verifiedAt": now.isoformat(timespec="seconds"),
        "python": platform.python_version(), "platform": platform.system(), "packages": {},
        "externalModelVerified": False,
        "scope": "当前十篇标准库入口、共享检索工具和边界回归已本机复验。无真实模型质量或生产性能结论。",
        "runs": records, "primarySeries": "AI Agent 开发实践", "primaryScriptCount": len(ARTICLE_MAP),
        "historicalVerification": history,
    }
    target.write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sections = [f"验证于 {verification['verifiedDate']} · Python {verification['python']} · {verification['platform']}"]
    for heading, runs in (("本次标准库复验", records), (f"历史补充实验（{history['verifiedDate']}，未在本次重跑）", history["runs"])):
        sections.append(f"\n# {heading}")
        for run in runs:
            sections.append(f"$ {run['command']}\n{run['stdout']}")
            if run.get("stderr"):
                sections.append(run["stderr"])
    (FOLDER / "verified-output.txt").write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="实际重跑后更新运行记录；随后需要重新生成ZIP")
    parser.add_argument("--check-assets", action="store_true", help="在仓库中核对文章代码与ZIP逐字节一致")
    args = parser.parse_args()
    if args.record and args.check_assets:
        parser.error("先用 --record 更新记录并重新打包，再使用 --check-assets 核查")
    records = run_scripts()
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RetrievalRegression))
    output = stream.getvalue().rstrip()
    print(output)
    records.append({"command": "python verify_examples.py", "suite": "retrieval-regression",
                    "exitCode": 0 if result.wasSuccessful() else 1, "stdout": output})
    if any(record["exitCode"] != 0 for record in records):
        raise SystemExit(1)
    if args.check_assets:
        check_assets()
    if args.record:
        write_records(records)
        print("已更新 verification.json 与 verified-output.txt；请同步下载ZIP。")


if __name__ == "__main__":
    main()
