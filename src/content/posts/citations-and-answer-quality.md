---
title: 给 Agent 的引用加校验：本次证据、版本与语义边界
description: 运行标准库引用检查器，拒绝未知ID、跨请求证据和版本冲突，再用错误建议说明合法引用不能保证语义正确。
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-04-27T12:00:00+08:00
featured: true
draft: false
series: AI Agent 代码实操
seriesOrder: 4
noteType: 代码实操
tags:
  - rag
  - 可靠性
  - 设计笔记
---

Agent 工具返回了 `csv-v2`，回答却引用 `csv-v1`，程序能否在展示前拦住？这篇直接写一个检查器，输入是引用 ID、本次工具结果和用户版本，输出是错误清单。它不调用模型，也不假装自动判断一句话是否完全正确；配套脚本已在 Python 3.12.14 执行。

## 目录

## 白名单来自本次调用，不是整个知识库

沿用三份自编资料。用户问 v2 的 E102 时，本次检索只应得到 `csv-v2`。虽然 `csv-v1` 确实存在于演示库，它仍不属于这次请求的依据。因此检查器先用本次结果建立 `id → document` 映射，引用不能绕过这份映射直接生成可信链接。

第二步再核对版本。这看似和上游过滤重复，却能发现另一类问题：检索、缓存或证据组装环节误把旧版本文档传给了生成环节。ID 在本次集合内，仅说明记录存在，不说明它适合当前用户。

## 文件与运行方式

将[知识工具](/examples/agent-lab/knowledge_tool.py)与[引用检查器](/examples/agent-lab/citation_checks.py)放在同一目录。执行环境是已配置 Python 3.12 的终端，不需要安装第三方包。

```bash
python citation_checks.py  # 运行五种引用输入和一个语义边界例子。
```

## 完整检查器

```python
from knowledge_tool import search_knowledge  # 取得本次调用实际返回的证据。

def check_citations(citation_ids: list[str], documents: list[dict], version: str) -> list[str]:  # 只校验来源与版本。
    if not citation_ids:  # 回答没有给出任何引用时先报告缺失。
        return ["缺少引用"]  # 这不是对答案语义的判定。
    evidence = {document["id"]: document for document in documents}  # 为本次检索建立白名单。
    errors = []  # 汇总检查结果，交给调用方决定如何反馈。
    for citation_id in citation_ids:  # 对回答中的每一个引用标识执行相同检查。
        if citation_id not in evidence:  # 全库存在的ID也不能代替本次检索证据。
            errors.append(f"不属于本次检索: {citation_id}")  # 记录越出证据集合的引用。
            continue  # 缺少本次证据时不再访问对应字典。
        document = evidence[citation_id]  # 取到实际被检索到的文档。
        if document["version"] != version:  # 防止上游检索混入其他版本资料。
            errors.append(f"版本不符: {citation_id}")  # 版本冲突与引用不存在分别报告。
    return errors  # 空列表表示这两项校验通过，不表示答案必然正确。

def main() -> None:  # 演示四种结构问题和一个语义边界。
    current = search_knowledge("E102", "v2")  # 当前用户明确使用v2。
    legacy = search_knowledge("E102", "v1")  # 仅用于模拟上游误传旧版本证据。
    cases = [  # 每个样例给出本次证据集合与待检查引用。
        ("正常引用", ["csv-v2"], current),  # ID与版本都对应本次请求。
        ("旧版 ID", ["csv-v1"], current),  # 全库有此ID，但本次没有检索到它。
        ("未知 ID", ["made-up"], current),  # 模拟模型生成了不存在的标识。
        ("混入旧证据", ["csv-v1"], legacy),  # ID在集合内，但版本仍然错误。
        ("没有引用", [], current),  # 没有引用需要单独反馈。
    ]  # 结束五种检查输入。
    for label, citation_ids, documents in cases:  # 用相同函数检查每种情况。
        errors = check_citations(citation_ids, documents, "v2")  # 请求版本始终是v2。
        print(label + ":", errors or "通过")  # 通过只指ID与版本两项条件。
    bad_answer = "请在 CSV 表头添加 user_id"  # 故意给出不适用于v2的错误建议。
    errors = check_citations(["csv-v2"], current, "v2")  # 合法引用仍能附在错误建议后面。
    print("错误建议的 ID 检查:", errors or "通过")  # 复现结构校验无法覆盖语义的问题。
    print("仍需核查:", bad_answer, "；v2 原文要求 customer_id")  # 提醒逐条核对结论支持关系。

if __name__ == "__main__":  # 保证导入校验函数时不会执行示例。
    main()  # 开始本地确定性演示。
```

函数返回错误列表而非只返回真假，调用方才能区分“没有引用”“引用不在本次集合”“引用版本不符”。这里没有自动重试，也不会把失败引用替换成另一份资料；在展示之前，可以要求重新生成、澄清版本或直接返回适用原文。

## 实际输出

```text
正常引用: 通过
旧版 ID: ['不属于本次检索: csv-v1']
未知 ID: ['不属于本次检索: made-up']
混入旧证据: ['版本不符: csv-v1']
没有引用: ['缺少引用']
错误建议的 ID 检查: 通过
仍需核查: 请在 CSV 表头添加 user_id ；v2 原文要求 customer_id
```

第三行模拟不存在的 ID；第四行故意把旧版证据作为“本次结果”传入。两者错误原因不同，输出也不同。最后两行是有意保留的反例：合法的 `csv-v2` ID 仍能跟在“添加 user_id”的错误建议后面，结构校验会通过，但 v2 原文要求的是 `customer_id`。

## 删除版本检查会发生什么

在本文件中，将版本比较那一行临时改成下面这样，再运行演示：

```python
if False:  # 故意关闭版本冲突分支，只用于观察错误行为。
```

本地对照运行时，“混入旧证据”从 `['版本不符: csv-v1']` 变成了“通过”。其他未知 ID 仍会报错，说明第一层检查还在，第二层已经失效。观察到这个差异后，应恢复原判断；不要把一个仍能执行完的脚本当成逻辑正确。

## 哪些问题还需要另查

这份检查器只处理 ID 来源和版本，不检查断言是否被原文支持，也不判断操作步骤是否完整。下一步应把回答拆成可核查建议，逐条对照原文、适用条件和预期行为。来源能打开、引用没越界、结论有依据，是三个需要分别验证的事实。

如果一次回答引用多份资料，本例会逐个检查；没有引用也会报告缺失。重复 ID、文档更新后 ID 是否失效、片段位置怎样回查，不在当前函数内；增加这些规则时，应同时补固定样例，避免把检查器写成无法解释的一长串条件。

## 中文原文与技术依据

- 幻想offer的牛牛：[《一个 Agent 到底如何与 DeepSeek 通信？从 Message 到 Tool Call 的》](https://www.nowcoder.com/discuss/921906577349545984)。原文用订单查询的消息与 Tool Call JSON 展开请求、执行和回传；适合对照“模型给出标识，程序负责关联实际结果”的边界。
- [LangChain 官方 Tools 说明](https://docs.langchain.com/oss/python/langchain/tools)：核对工具的输入、返回值与运行时上下文职责。

中文原文提供阅读线索，本站检查器为独立实现；上述运行结果只描述这一离线示例。
