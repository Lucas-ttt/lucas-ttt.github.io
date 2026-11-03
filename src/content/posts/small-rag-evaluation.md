---
title: 给 Agent 检索工具跑 8 条回归：证据 ID 与错误分支
description: 用八条固定输入和预期结果检查检索工具，展示8/8通过及关闭版本过滤后5/8的真实对照，明确不是LLM准确率。
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-04-06T12:00:00+08:00
featured: false
draft: false
series: AI Agent 代码实操
seriesOrder: 5
noteType: 代码实操
tags:
  - rag
  - 评估
  - 开源研读
---

手动问一次 E102，返回了正确资料，还不能确认工具契约完整。版本换掉会怎样？问题为空时会不会继续检索？数量参数传成文本会怎样？下面把这些问题写成八条可重复运行的用例，用实际输出检查工具，而不是凭一次演示判断“效果很好”。

## 目录

## 先决定每个输入应该得到什么

演示库仍是三条自编资料。前三个用例分别期待 `csv-v1`、`csv-v2` 和 `encoding-v2`；未知 v9 应得到空列表；空问题、空版本、零条候选和字符串数量应抛出 `ValueError`。这些预期在调用前就写定，不能看完实际结果再改成“通过”。

证据 ID 完全匹配适合检查这个确定性小工具。如果将来增加多路召回、同分候选或资料更新，要重新明确允许的顺序与证据集合；本例的精确匹配规则不能不加区分地用于所有检索系统。

## 文件与执行环境

将[知识工具](/examples/agent-lab/knowledge_tool.py)和[回归脚本](/examples/agent-lab/eval_tools.py)放在同一目录。下面结果来自 Python 3.12.14；只有标准库和配套模块，没有调用模型、网络或真实企业数据库。

```bash
python eval_tools.py  # 逐条打印实际结果，并以退出码表示是否全部通过。
```

## 完整回归脚本

```python
from knowledge_tool import search_knowledge  # 本例只测工具契约，不调用LLM。

CASES = [  # 每条样例明确输入和预期证据ID或异常类型。
    {"name": "v1 的 E102", "params": {"query": "E102", "version": "v1"}, "ids": ["csv-v1"]},  # 旧版字段说明。
    {"name": "v2 的 E102", "params": {"query": "E102", "version": "v2"}, "ids": ["csv-v2"]},  # 新版字段说明。
    {"name": "v2 的 E201", "params": {"query": "E201", "version": "v2"}, "ids": ["encoding-v2"]},  # 编码错误说明。
    {"name": "未知版本", "params": {"query": "E102", "version": "v9"}, "ids": []},  # 没有适用资料属于正常空结果。
    {"name": "空问题", "params": {"query": "", "version": "v2"}, "error": "ValueError"},  # 不接受空输入。
    {"name": "空版本", "params": {"query": "E102", "version": ""}, "error": "ValueError"},  # 不能猜测用户版本。
    {"name": "零条候选", "params": {"query": "E102", "version": "v2", "top_k": 0}, "error": "ValueError"},  # 检查数量下界。
    {"name": "文本数量", "params": {"query": "E102", "version": "v2", "top_k": "3"}, "error": "ValueError"},  # 不默默接受错误类型。
]  # 结束八条固定回归用例。

def run_case(case: dict) -> tuple[bool, str]:  # 每个用例返回通过状态与实际结果。
    try:  # 参数错误是本例需要观察的正常检查分支。
        documents = search_knowledge(**case["params"])  # 原样传入用例中的参数。
    except ValueError as error:  # 只捕获工具契约声明的异常。
        expected = case.get("error") == "ValueError"  # 不把所有异常都当作通过。
        return expected, f"ValueError: {error}"  # 保留真实异常信息供排错。
    actual = [document["id"] for document in documents]  # 只比较明确定义的证据标识。
    passed = "error" not in case and actual == case["ids"]  # 若预期异常却正常返回，也判失败。
    return passed, str(actual)  # 回传实际值，而非只打印一个汇总分数。

def main() -> None:  # 固定顺序执行并报告结果。
    passed_count = 0  # 通过数量从零累计。
    for case in CASES:  # 每条用例独立验证，不依赖前面的结果。
        passed, actual = run_case(case)  # 调用工具并对比预期。
        passed_count += int(passed)  # 将布尔结果转换为通过数量。
        status = "PASS" if passed else "FAIL"  # 用简短状态标记方便查找失败行。
        print(f"{status} {case['name']}: {actual}")  # 同时显示问题和实际输出。
    print(f"工具回归通过: {passed_count}/{len(CASES)}")  # 分母是这八个固定用例。
    raise SystemExit(0 if passed_count == len(CASES) else 1)  # 任一失败都会返回非零退出码。

if __name__ == "__main__":  # 仅直接运行时执行回归。
    main()  # 该结果不是LLM回答准确率或生产质量结论。
```

这里有两个细节：一是预期异常的用例如果正常返回，也要判失败；二是只捕获契约声明的 `ValueError`。其他异常会直接暴露，不被统统吞掉并算作“无结果”。最后的非零退出码，方便后续在提交检查中阻止带着回归问题继续发布。

## 实际输出：八条工具用例通过

```text
PASS v1 的 E102: ['csv-v1']
PASS v2 的 E102: ['csv-v2']
PASS v2 的 E201: ['encoding-v2']
PASS 未知版本: []
PASS 空问题: ValueError: query 必须是非空字符串
PASS 空版本: ValueError: version 必须是非空字符串
PASS 零条候选: ValueError: top_k 必须是 1 到 5 的整数
PASS 文本数量: ValueError: top_k 必须是 1 到 5 的整数
工具回归通过: 8/8
```

`8/8` 的分母就是代码里的八个用例。它不是大模型回答准确率、用户问题成功率，也不说明系统已经具备生产质量。这里仅检查了这组输入下的参数校验、版本过滤、关键词命中和空结果行为。

## 故意关掉版本过滤，再看回归是否能报警

在 `knowledge_tool.py` 中，把版本过滤条件临时改成下面这一行：

```python
if False:  # 故意跳过版本筛选，观察回归能否发现跨版本结果。
```

这次本地对照确实出现三条失败：v1 的 E102 和 v2 的 E102 都返回两份资料；未知 v9 也拿到了已有版本的结果。回归汇总变为：

```text
FAIL v1 的 E102: ['csv-v1', 'csv-v2']
FAIL v2 的 E102: ['csv-v1', 'csv-v2']
FAIL 未知版本: ['csv-v1', 'csv-v2']
工具回归通过: 5/8
```

错误版本的退出码是 `1`。恢复条件后重新运行，才回到 `8/8`。这个对照的价值是确认用例能抓住目标缺陷，而不只是确认脚本每次都能打印绿色结果。

## 从工具回归走向问答评估

下一层可以增加完整问题、参考片段、实际回答和人工判定，把证据覆盖、引用支持与答案适用性分别记录。新问题先作为补充样例，不要把已参与修改的八条用例又说成完全未见过的留出集。

这个小集合也没有覆盖中文分词、同义表达、超时、持久化索引或权限。每加入一项能力，先写清预期行为，再补能让错误实现失败的样例。数字的用途是定位差异，而不是给简历制造一个没有口径的高分。

## 中文原文与技术依据

- 幻想offer的牛牛：[《一个 Agent 到底如何与 DeepSeek 通信？从 Message 到 Tool Call 的》](https://www.nowcoder.com/discuss/921906577349545984)。原文提供工具参数、返回状态与消息关联的 JSON 和后端代码片段，可对照本文怎样把这些约定变成固定用例。
- Chenxu：[《RAG检索优化：从 68% 到 82.2%》](https://www.chenxutalk.top/posts/study/ai/rag/retrieval-eval/)。作者记录了数据集、候选池和时延等条件，适合阅读其对照方法；本文的八条工具回归与原文实验属于不同口径。
- [Ragas 官方 Context Recall 说明](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/)：证据覆盖评估需要参考信息；它和这里的工具契约回归不是同一个指标。

本站脚本为独立实现。本文保留实际通过数、错误实现的失败信号与示例范围，便于读者下载后复核。
