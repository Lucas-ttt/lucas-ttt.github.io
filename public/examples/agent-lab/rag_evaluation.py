import json  # 输出指标与失败明细。
from time import perf_counter  # 单独记录本机检索耗时。
from project_walkthrough import build_index, retrieve  # 评测与项目原型使用同一索引和检索入口。

CASES = [  # 问题、参考证据和关键事实在调用前人工写定。
    {"id": "d1", "split": "dev", "query": "E102", "version": "v2", "ids": ["csv-v2"], "facts": ["customer_id"]},  # 精确错误码基线。
    {"id": "d2", "split": "dev", "query": "E201", "version": "v2", "ids": ["encoding-v2"], "facts": ["UTF-8"]},  # 编码说明。
    {"id": "d3", "split": "dev", "query": "customer_id UTF-8", "version": "v2", "ids": ["csv-v2", "encoding-v2"], "facts": ["customer_id", "UTF-8"]},  # 开发集暴露单候选覆盖不足。
    {"id": "h1", "split": "holdout", "query": "E102", "version": "v1", "ids": ["csv-v1"], "facts": ["user_id"]},  # 旧版本必须独立取数。
    {"id": "h2", "split": "holdout", "query": "上传时找不到客户字段", "version": "v2", "ids": ["csv-v2"], "facts": ["customer_id"]},  # 保留词项基线无法理解的改写。
    {"id": "h3", "split": "holdout", "query": "E102", "version": "v9", "ids": [], "facts": []},  # 未知版本应无依据。
    {"id": "h4", "split": "holdout", "query": "退款", "version": "v2", "ids": [], "facts": []},  # 库外问题检查拒答。
    {"id": "h5", "split": "holdout", "query": "E102 E201", "version": "v2", "ids": ["csv-v2", "encoding-v2"], "facts": ["customer_id", "UTF-8"]},  # 留出组合表达。
    {"id": "h6", "split": "holdout", "query": "UTF-8", "version": "v1", "ids": [], "facts": []},  # 不能借用另一版本证据。
    {"id": "h7", "split": "holdout", "query": "UTF-8 文件编码", "version": "v2", "ids": ["encoding-v2"], "facts": ["UTF-8"]},  # 保留未与开发集重复的编码表达。
]  # 这是小型人工开发与留出样例，不是生产问题分布。

def evaluate(cases, index, top_k):  # 同一配置逐条保留原始结果。
    records = []  # 后续汇总不丢弃失败输入。
    for case in cases:  # 参考答案不从实际输出生成。
        started = perf_counter()  # 测量当前调用，不混入索引构建。
        hits = retrieve(case["query"], case["version"], top_k=top_k, index=index)  # 调用项目实际检索入口。
        elapsed_ms = (perf_counter() - started) * 1000  # 时间独立于质量分数。
        actual, expected = {row["id"] for row in hits}, set(case["ids"])  # 按证据身份去重再比较。
        overlap = len(actual & expected)  # 只计算被标注为相关的返回项。
        recall = overlap / len(expected) if expected else None  # 没有参考证据时不做除零或当作满分。
        precision = overlap / len(actual) if actual else 0.0  # 本文约定除以实际返回数量。
        text = "\n".join(row["text"] for row in hits)  # 用抽取原文检查这份确定性渲染路径。
        facts_ok = all(fact in text for fact in case["facts"])  # 只校验样例预先列出的短字段。
        version_ok = all(row["version"] == case["version"] for row in hits)  # 错误版本单独标记。
        passed = actual == expected and facts_ok and version_ok  # 不将事实缺失隐藏在平均召回里。
        records.append({"id": case["id"], "actual": sorted(actual), "recall": recall, "precision": precision, "passed": passed, "version_ok": version_ok, "elapsed_ms": elapsed_ms})  # 保存可复查明细。
    return records  # 调用方可将同样结构写入本地评测记录。

def summary(records):  # 为这组样例明确统计口径。
    positive = [row for row in records if row["recall"] is not None]  # 只有有参考证据的问题进入检索宏平均。
    negatives = [row for row in records if row["recall"] is None]  # 空参考样例单独检查无结果行为。
    return {"passed": f"{sum(row['passed'] for row in records)}/{len(records)}", "recall_macro": round(sum(row["recall"] for row in positive) / len(positive), 3), "precision_macro": round(sum(row["precision"] for row in positive) / len(positive), 3), "empty_correct": f"{sum(not row['actual'] for row in negatives)}/{len(negatives)}", "wrong_version": sum(not row["version_ok"] for row in records)}  # 指标不叫LLM准确率。

def main():  # 先固定开发配置，再观察留出问题。
    dev_inputs = {(case["query"], case["version"]) for case in CASES if case["split"] == "dev"}  # 检查输入本身，不只检查问题编号。
    holdout_inputs = {(case["query"], case["version"]) for case in CASES if case["split"] == "holdout"}  # 不把相同输入换编号后算作留出。
    assert dev_inputs.isdisjoint(holdout_inputs)  # 完整问题与版本的组合不能跨集合重复。
    index = build_index()  # 与被测项目共享同一份真实内存索引。
    for top_k in (1, 2):  # 唯一变化是候选数量，其他规则与语料保持不变。
        for split in ("dev", "holdout"):  # 两个集合分别报告，不混成一个漂亮总分。
            cases = [case for case in CASES if case["split"] == split]  # 不让同一个ID跨集合。
            records = evaluate(cases, index, top_k)  # 运行后仍保留逐条观测。
            print(f"top_k={top_k} {split}", json.dumps(summary(records), ensure_ascii=False))  # 展示真实通过数与分母。
            for row in records:  # 不只打印汇总指标。
                if not row["passed"]:  # 重点显示仍未解决的样例。
                    print("失败样例", row["id"], row["actual"])  # 对照人工预期可以继续定位原因。
    print("计时说明", "elapsed_ms逐条记录检索调用，不包含索引和模型；重复运行会变化")  # 不把一次小样本计时当性能结论。

if __name__ == "__main__":  # 导入时不自动运行整组评测。
    main()  # 不调用外部模型或网络。
