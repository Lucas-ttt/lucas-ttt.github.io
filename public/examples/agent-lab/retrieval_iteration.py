"""在固定小样本上对照词项检索与受限的字段别名补召回。"""

import argparse
import json
import re
from pathlib import Path

from project_walkthrough import build_index, retrieve
from rag_evaluation import CASES


TOP_K = 2
REPORT_PATH = Path(__file__).with_name("retrieval_iteration_results.json")

# 只为手册定义过的 CSV 必填字段提供版本内的术语映射。
FIELD_ALIASES = {
    "v1": ("user_id", ("用户字段", "用户编号", "用户标识")),
    "v2": ("customer_id", ("客户字段", "客户编号", "客户标识")),
}
EXPLICIT_TERM = re.compile(
    r"(?<![a-z0-9_])(?:e[0-9]+|id|[a-z][a-z0-9_]*_id)(?![a-z0-9_])",
    re.IGNORECASE | re.ASCII,
)
IMPORT_CONTEXT = re.compile(r"上传|导入|表头|CSV", re.IGNORECASE)
AMBIGUOUS_CONTEXT = re.compile(
    r"不缺|未缺|没有缺|无需|不需要|不是|并非|并不|不一定|不确定|未必|"
    r"退款|支付|发票|订单状态|含义|定义|说明文档"
)
MISSING_BEFORE = r"(?:缺少|缺了|找不到|没有|未找到)(?:必填的?|对应的?)?"
MISSING_AFTER = r"(?:缺失|没找到|找不到|不存在)"

# 新人工对照组先写下证据标注，再对同一索引运行两种方法。
# 编号用于报告定位，不参与规则选择。
CONTROL_CASES = [
    {"id": "c01", "query": "导入表格时，提示缺少客户编号", "version": "v2", "ids": ["csv-v2"]},
    {"id": "c02", "query": "上传模板后显示客户标识缺失", "version": "v2", "ids": ["csv-v2"]},
    {"id": "c03", "query": "导入文件时找不到用户编号", "version": "v1", "ids": ["csv-v1"]},
    {"id": "c04", "query": "导入后提示客户那列没了", "version": "v2", "ids": ["csv-v2"]},
    {"id": "c05", "query": "上传时找不到客户编号", "version": "v1", "ids": []},
    {"id": "c06", "query": "导入时缺少客户标识", "version": "v9", "ids": []},
    {"id": "c07", "query": "上传时并不是缺少客户字段", "version": "v2", "ids": []},
    {"id": "c08", "query": "退款申请时找不到客户编号", "version": "v2", "ids": []},
    {"id": "c09", "query": "客户标识是什么意思", "version": "v2", "ids": []},
    {"id": "c10", "query": "上传 E10 时找不到客户字段", "version": "v2", "ids": []},
    {"id": "c11", "query": "上传 id 后找不到客户字段", "version": "v2", "ids": []},
    {"id": "c12", "query": "E102 E201", "version": "v1", "ids": ["csv-v1"]},
    {"id": "c13", "query": "导入 E10 时找不到客户字段", "version": "v2", "ids": []},
    {"id": "c14", "query": "导入 id 找不到客户字段", "version": "v2", "ids": []},
]


def alias_expansion(query, version):
    """仅为同一分句内的导入缺列请求给出一个可解释的标准词项。"""
    if version not in FIELD_ALIASES or EXPLICIT_TERM.search(query):
        return None

    field, aliases = FIELD_ALIASES[version]
    for sentence in re.split(r"[。？！；!?;\n]+", query):
        if not IMPORT_CONTEXT.search(sentence) or AMBIGUOUS_CONTEXT.search(sentence):
            continue
        for alias in aliases:
            term = re.escape(alias)
            pattern = rf"{MISSING_BEFORE}{term}(?!定义|说明|文档)|{term}{MISSING_AFTER}"
            if re.search(pattern, sentence):
                return {"alias": alias, "field": field}
    return None


def retrieve_with_alias(query, version, *, top_k=TOP_K, index=None):
    """保留基线有结果的请求，空结果时尝试同版本内的一个标准词项。"""
    rows = build_index() if index is None else index
    baseline = retrieve(query, version, top_k=top_k, index=rows)
    expansion = alias_expansion(query, version.strip()) if not baseline else None
    if expansion is None:
        return baseline, None
    expanded = retrieve(expansion["field"], version, top_k=top_k, index=rows)
    return expanded, expansion


def assess(hits, expected, version):
    actual = [row["id"] for row in hits]
    wrong_version = any(row["version"] != version for row in hits)
    return {
        "ids": actual,
        "passed": set(actual) == set(expected) and not wrong_version,
        "wrong_version": wrong_version,
    }


def summarize(rows, variant):
    negatives = [row for row in rows if not row["expected_ids"]]
    return {
        "passed": sum(row[variant]["passed"] for row in rows),
        "total": len(rows),
        "wrong_version": sum(row[variant]["wrong_version"] for row in rows),
        "expected_empty": len(negatives),
        "correct_empty": sum(not row[variant]["ids"] for row in negatives),
    }


def evaluate_group(label, samples, index):
    rows = []
    for sample in samples:
        query, version, expected = sample["query"], sample["version"], sample["ids"]
        baseline = retrieve(query, version, top_k=TOP_K, index=index)
        improved, expansion = retrieve_with_alias(query, version, index=index)
        rows.append({
            "id": sample["id"],
            "query": query,
            "version": version,
            "expected_ids": expected,
            "baseline": assess(baseline, expected, version),
            "improved": assess(improved, expected, version),
            "expansion": expansion,
        })

    return {
        "label": label,
        "baseline": summarize(rows, "baseline"),
        "improved": summarize(rows, "improved"),
        "cases": rows,
    }


def run_experiment():
    prior_inputs = {(case["query"], case["version"]) for case in CASES}
    control_inputs = {(case["query"], case["version"]) for case in CONTROL_CASES}
    assert len(control_inputs) == len(CONTROL_CASES)
    assert not prior_inputs.intersection(control_inputs), "新对照不能重复已有输入"

    index = build_index()
    regression = evaluate_group("原评测回归组", CASES, index)
    control = evaluate_group("新人工对照组", CONTROL_CASES, index)
    rows = {row["id"]: row for group in (regression, control) for row in group["cases"]}
    assert rows["h2"]["baseline"]["ids"] == []
    assert rows["h2"]["improved"]["ids"] == ["csv-v2"]
    assert rows["c04"]["improved"]["ids"] == [], "保留别名覆盖之外的漏检案例"
    for case_id in ("c13", "c14"):
        assert rows[case_id]["baseline"]["ids"] == rows[case_id]["improved"]["ids"], "记录混合输入中的基线误召"
    assert all(rows[case_id]["expansion"] is None for case_id in ("c07", "c10", "c11"))
    assert not any(row["baseline"]["passed"] and not row["improved"]["passed"] for row in rows.values())
    assert not any(row["improved"]["wrong_version"] for row in rows.values())

    return {
        "corpus_size": len(index),
        "top_k": TOP_K,
        "method": "同一索引与版本过滤，词项基线无结果才按导入缺列语境扩展一个字段词项",
        "scope": "三份自编短手册上的人工小样本。原评测已看过，新对照和词表由同一作者设计。",
        "metric": "证据 ID 集合与人工标注完全一致且无错版本时计为通过。应为空样例单独统计。",
        "groups": [regression, control],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--record", action="store_true", help="写入可下载的逐条评测报告")
    actions.add_argument("--check", action="store_true", help="复验已签入的报告与当前代码一致")
    args = parser.parse_args()

    report = run_experiment()
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.record:
        REPORT_PATH.write_text(rendered, encoding="utf-8")
    elif args.check and REPORT_PATH.read_text(encoding="utf-8") != rendered:
        raise SystemExit("评测报告与当前实验不一致，请运行 --record 后核对差异。")

    for group in report["groups"]:
        before, after = group["baseline"], group["improved"]
        total = after["total"]
        print(f"{group['label']} 通过 {before['passed']}/{total} → {after['passed']}/{total}")
        print(f"别名补召回后错版本 {after['wrong_version']}，应空 {after['correct_empty']}/{after['expected_empty']}")
        for row in group["cases"]:
            if row["baseline"]["ids"] != row["improved"]["ids"] or not row["improved"]["passed"]:
                print(row["id"], row["query"], row["baseline"]["ids"], "→", row["improved"]["ids"], "预期", row["expected_ids"])


if __name__ == "__main__":
    main()
