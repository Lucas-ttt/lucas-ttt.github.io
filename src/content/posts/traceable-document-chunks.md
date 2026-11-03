---
title: 先把 Agent 工具写对：按版本查询 E102 排障资料
description: 一个标准库可运行的只读检索工具：三份演示资料、严格版本过滤、关键词评分、参数校验与真实输出，先验证工具再接模型。
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-11-01T12:00:00+08:00
featured: false
draft: false
series: AI Agent 代码实操
seriesOrder: 1
noteType: 代码实操
tags:
  - rag
  - python
  - 实践记录
---

用户问“v2 导入 CSV 报 E102，应该检查什么”，工具却找出了 v1 的 `user_id` 说明。模型即使逐字转述，答案也会选错版本。本篇先把这个问题收敛成一个可以直接运行的 Python 函数，再把它交给后续 Agent 调用。

这里采用三份自编资料，分别表示 v1 的 `user_id`、v2 的 `customer_id` 和 v2 的 UTF-8 编码要求。实现只使用标准库，不需要模型密钥、向量数据库或网络连接。它是关键词检索工具，不是完整的向量 RAG 系统。

## 目录

## 先约定工具的输入输出

入口为 `search_knowledge(query, version, top_k=3)`。问题和版本必须是非空字符串，返回数量只能为 1 到 5 的真正整数。返回列表中的每一项保留资料标识、版本、错误码、正文与来源，调用方可以继续组装证据，不能只拿一段没有出处的答案。

查找时先过滤版本，再对英文词、错误码和连续中文片段做简单子串计分。没有命中就返回空列表；未知版本也不借用旧版本。得分只是本例的关键词计数，不能当成答案正确的概率。

## 完整代码

执行环境：Python 3.10 及以上。将代码保存为 `knowledge_tool.py`；也可直接[下载脚本](/examples/agent-lab/knowledge_tool.py)。下方每个非空代码行都有中文说明。

```python
import re  # 使用标准库拆出英文词、错误码与连续中文片段。

DOCUMENTS: list[dict] = [  # 演示资料全部为自编内容，不代表企业真实文档。
    {  # 第一份资料说明旧版本的字段要求。
        "id": "csv-v1", "version": "v1", "error_code": "E102",  # 标识、版本与错误码共同限定适用范围。
        "text": "CSV 导入缺少 user_id 列，检查首行表头。",  # v1 使用 user_id 字段。
        "source": "demo/csv-v1.md",  # 这是演示来源标识，不会尝试打开本机文件。
    },  # 结束第一条演示资料。
    {  # 第二份资料使用相同错误码，但属于新版本。
        "id": "csv-v2", "version": "v2", "error_code": "E102",  # 同错误码不能代替版本过滤。
        "text": "CSV 导入缺少 customer_id 列，检查首行表头。",  # v2 的处理依据改为 customer_id。
        "source": "demo/csv-v2.md",  # 返回来源信息，便于显示依据。
    },  # 结束第二条演示资料。
    {  # 第三份资料覆盖编码问题。
        "id": "encoding-v2", "version": "v2", "error_code": "E201",  # 编码错误使用独立错误码。
        "text": "文件应使用 UTF-8 编码，避免出现乱码。",  # 保留英文编码名称与中文说明。
        "source": "demo/encoding-v2.md",  # 同样使用自编来源标识。
    },  # 结束第三条演示资料。
]  # 结束演示资料列表。

def search_knowledge(query: str, version: str, top_k: int = 3) -> list[dict]:  # 定义只读关键词检索工具。
    if not isinstance(query, str) or not query.strip():  # 拒绝空问题与错误类型。
        raise ValueError("query 必须是非空字符串")  # 明确给出参数错误。
    if not isinstance(version, str) or not version.strip():  # 版本必须显式给出。
        raise ValueError("version 必须是非空字符串")  # 不暗中采用其他版本。
    if type(top_k) is not int or not 1 <= top_k <= 5:  # 真正的整数才可使用，布尔值也拒绝。
        raise ValueError("top_k 必须是 1 到 5 的整数")  # 限制返回规模。
    version = version.strip()  # 清理版本两侧空白，但不猜测版本兼容关系。
    english = re.findall(r"[a-z0-9_]+", query.lower())  # 提取英文词、字段名与错误码。
    chinese = re.findall(r"[\u4e00-\u9fff]+", query)  # 提取连续中文词段，按子串匹配。
    terms = set(english + chinese)  # 去重，避免重复输入人为放大得分。
    ranked = []  # 保存有关键词命中的候选。
    for document in DOCUMENTS:  # 在小型演示资料中逐条查找。
        if document["version"] != version:  # 先按版本过滤，再计算相关分数。
            continue  # 其他版本即使同错误码也不会进入候选。
        content = f"{document['error_code']} {document['text']}".lower()  # 建立可匹配文本。
        score = sum(term in content for term in terms)  # 每个命中词记一分，这不是向量相似度。
        if score > 0:  # 没有关键词命中就不返回资料。
            ranked.append((score, document))  # 同时保留得分与原始资料。
    ranked.sort(key=lambda item: (-item[0], item[1]["id"]))  # 按得分降序，标识用于稳定打破同分。
    return [dict(document) for _, document in ranked[:top_k]]  # 返回副本，避免调用方改动演示库。

if __name__ == "__main__":  # 直接执行时演示三个独立问题。
    for version in ("v2", "v1", "v9"):  # 比较新版本、旧版本与未知版本。
        hits = search_knowledge("E102", version)  # 相同错误码必须受版本约束。
        print(version, [item["id"] for item in hits])  # 输出实际命中的资料标识。
```

## 运行与实际输出

以下命令在保存脚本的目录执行，适用于 Windows PowerShell；其他系统使用对应的 Python 解释器。

```powershell
python knowledge_tool.py # 运行三个版本的 E102 查询，不会调用模型或修改文件。
```

本次运行得到：

```text
v2 ['csv-v2']
v1 ['csv-v1']
v9 []
```

相同错误码在 v1 与 v2 下得到不同资料，v9 没有适用资料。将问题改为“编码”，版本设为 v2，实际返回 `encoding-v2`。这几个输出比一段“支持可靠检索”的介绍更容易核对。

## 排错：为什么 True 不能作为返回数量

Python 中 `bool` 是 `int` 的子类；只用 `isinstance(top_k, int)` 会把 `True` 放过。代码因此使用 `type(top_k) is int`，并检查上下界。本次分别尝试空问题、空版本、`True`、0 和 6，都得到明确的 `ValueError`，而不是悄悄改成默认值。

另一种容易误判的现象是“字段不见了”没有匹配到资料。本例没有分词、Embedding 或同义词扩展，连续中文片段只有原样包含才计分。先检查拆出的关键词、版本过滤与资料内容，再决定是否需要语义检索，避免把每个空结果都归因给模型。

## 接入 Agent 前再检查三件事

确认调用记录携带了版本；保留返回项中的来源；将空列表作为证据不足状态处理。当前函数返回字典副本，避免调用方修改原始演示库，但这不等于已经完成认证、权限隔离或数据库检索。

下一步可以让模型提交工具名和参数，由程序校验后调用此函数。模型没有真正执行工具的能力；返回工具请求与产生实际检索结果，应在日志中分别观察。本文只验收这个独立工具的行为，不把它描述成企业上线成果。

## 中文原文与一手资料

- [LucaJu：DeepAgents 人工介入实战](https://www.cnblogs.com/jucunqi/p/19956619)：原文将查询和高风险动作拆成不同工具，适合继续阅读工具边界与执行控制。本文代码为围绕自编资料编写的独立示例，没有转载原文代码。
- [LangChain 官方 Tools 文档](https://docs.langchain.com/oss/python/langchain/tools)：核对工具输入定义与应用侧执行的职责，接框架时再按锁定版本注册函数。
