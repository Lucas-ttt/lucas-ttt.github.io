---
title: "我给知识库建立了一份可复查的评测记录"
description: "人工整理问题与参考证据，分开开发和留出样例，用明确分母、失败明细与前后对照核查效果。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-02-02T12:00:00+08:00
featured: true
draft: false
tags: ["rag", "评测", "回归测试"]
series: "AI Agent 开发实践"
seriesOrder: 8
noteType: "代码实操"
modDatetime: 2026-11-03T13:03:44+00:00
---

知识库原型第一次返回正确的 `customer_id` 时，我并没有马上把它当成效果已经稳定。这个问题恰好带了精确错误码，资料也很短；把版本换掉、同时询问字段与编码，或者改成口语描述，可能出现完全不同的结果。我需要一份能重复运行、也能保留失败的记录，才能判断下一次修改究竟改善了什么。

我先围绕三份自编资料人工写了十条问题，并提前标出相关证据 ID 与必须出现的短字段。它们覆盖精确编号、跨版本、组合问题、口语改写和库外请求。数据量很小，不代表真实用户分布，但每条预期都能回到原文手工核对，适合当前阶段定位机制上的缺口。

## 目录

## 先固定参考依据，再运行系统

我把前三条作为开发样例，其余七条作为留出样例。开发集里有一条同时询问 `customer_id` 和 `UTF-8` 的请求，需要两份证据；它能暴露只取一个候选的覆盖问题。留出集换成错误码组合表达，并保留“上传时找不到客户字段”这样的自然语言改写，观察调整能解决什么、还有什么没有解决。

参考证据和字段在 `CASES` 中人工写定，不从实际检索结果生成。否则工具漏掉资料时，自动生成的“标准答案”也会跟着漏掉，系统就只是在确认自己与自己一致。每次查看留出结果以后，这批问题已经参与了我的认识和排错；后续如果继续用它们调规则，就应把它们当回归集，再补新的留出问题。

这份小数据也不是独立标注团队交付的测试集。程序检查开发与留出集合的完整问题、版本组合不重复，但它们来自同一份微型资料，近义表达仍有很强相关性，不能据此证明真实泛化。后续有实际使用场景时，需要在授权与脱敏前提下收集问题，统一相关性标注规则，并检查相近改写及同一文档变体是否跨集合泄漏。

## 我把检索、规则验收和无依据请求分开

检索层需要知道应该找到哪些证据。对一个问题，召回率等于实际找到的相关证据数除以全部参考相关证据数；精确率等于实际找到的相关证据数除以实际返回项数。本文选择后一个分母，返回不足 K 条时不强行补成 K；没有返回却应该有资料时，精确率记零，召回率也记零。

没有参考证据的请求不进入召回率平均，也不把除零视为满分。我单独检查这类请求是否确实没有返回资料。代码中的 `empty_correct` 是“正确空结果数/此类样例数”的计数，开发集没有这类样例时显示 `0/0`，表示没有样本，而不是一个可参与平均的指标值。

我还检查返回版本和预先标出的短字段。当前答案由命中的原文直接拼接，所以字段检查只验证这条确定性输出路径，不能代替开放文本的语义评审。真实接入模型后，还需要保存回答、引用对应关系和人工判断依据，检查主张是否受证据支持、是否遗漏适用条件。

## 可运行的评测记录

将[评测脚本](/examples/agent-lab/rag_evaluation.py)与[知识库原型](/examples/agent-lab/project_walkthrough.py)放在同一目录。脚本使用同一份实际索引和 `retrieve` 入口，不另造一套结果替代被测程序。环境为 Python 3.12，不需要密钥和外部服务。

```python
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
```

## 代码逐段解析

`evaluate` 先调用实际检索，再对证据 ID 求交集。只有参考集合非空的问题进入检索宏平均，每个问题权重相同。记录里同时保留实际 ID、单题指标、版本检查、规则验收和本机调用耗时，汇总以后仍然能找到具体失败输入。

`facts` 是预先标出的短字段，不是通用的答案评分器。例如组合问题必须同时包含 `customer_id` 与 `UTF-8`，只有其中一个时，即使检索到的那条资料本身相关，任务规则仍然不能通过。这个分层可以防止“返回项都相关”掩盖“只回答了半个问题”。

计时使用 `perf_counter` 包住检索调用，不包含离线入库和生成模型。耗时没有折算进质量分数，也没有用一次运行推算吞吐量。下一篇的分段实验会进一步把这些阶段拆开，这里先保留测量位置，避免以后不同配置把不同阶段混在一起比较。

## 只改变 Top-K，观察实际差异

```powershell
python rag_evaluation.py # 分别运行开发集和留出集，保留失败样例。
```

本次结果的主要部分如下，所有数值都对应这十条人工样例：

```text
top_k=1 dev {"passed": "2/3", "recall_macro": 0.833, "precision_macro": 1.0, "empty_correct": "0/0", "wrong_version": 0}
失败样例 d3 ['encoding-v2']
top_k=1 holdout {"passed": "5/7", "recall_macro": 0.625, "precision_macro": 0.75, "empty_correct": "3/3", "wrong_version": 0}
失败样例 h2 []
失败样例 h5 ['csv-v2']
top_k=2 dev {"passed": "3/3", "recall_macro": 1.0, "precision_macro": 1.0, "empty_correct": "0/0", "wrong_version": 0}
top_k=2 holdout {"passed": "6/7", "recall_macro": 0.75, "precision_macro": 0.75, "empty_correct": "3/3", "wrong_version": 0}
失败样例 h2 []
```

开发集的组合问题在 K 为一时只返回编码证据，单题召回为二分之一；两个单证据问题都找到，因此三个问题的宏平均约为零点八三三。增加到两个候选以后，开发组合问题和留出组合问题都拿到了两份资料。留出规则验收从七条中的五条变为六条，没有把这两个计数写成大模型准确率。

## 那条始终失败的口语问题更值得留下

“上传时找不到客户字段”在两种配置下都是空结果。相关资料确实存在，参考标注指向 `csv-v2`，但当前词项规则找不到与整段中文匹配的内容。增加候选上限不会制造一个本来没有得分的候选，因此这次调整无法解决它。

这个失败把下一步工作定位在问题表达与召回机制，而不是生成模型措辞。我会先记录拆出的词项、候选评分与过滤条件，再比较分词、别名或语义检索方案。改动以后既要检查这条问题，也要继续运行版本与库外样例，防止召回放宽以后把旧版本或无关资料一起带回来。

最终我希望保存的是一组可以解释的变化：哪类问题改善，哪类问题退化，代价是什么，还有哪些失败没有解决。当前的十条样例与两个配置已经能够展示这种记录方法；要证明真实系统有效，还需要扩展问题来源、标注审核和端到端回答验证。
