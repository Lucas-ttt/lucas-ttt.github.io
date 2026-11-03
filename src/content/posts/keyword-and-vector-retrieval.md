---
title: 先把 Agent 检索工具做对：错误码、版本与空结果
description: 用可下载的标准库脚本对照版本混用与正确检索，实际观察E102、E201、未知版本及参数错误的返回。
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-06-25T12:00:00+08:00
featured: false
draft: false
series: AI Agent 代码实操
seriesOrder: 3
noteType: 代码实操
tags:
  - rag
  - 检索设计
  - 开源研读
---

用户说“v2 导入报 E102”，Agent 应该查询哪份资料？先别急着接模型、换向量库。下面直接调用工具，用一组固定输入确认返回值是否符合契约。配套脚本已在 Python 3.12.14 运行，数据是三条自编说明，整个演示不需要 API Key。

## 目录

## 把预期结果写在调用前面

演示库包含三份资料：`csv-v1` 对应 v1 的 E102，要求 `user_id`；`csv-v2` 对应 v2 的同一错误码，要求 `customer_id`；`encoding-v2` 对应 v2 的 E201，要求 UTF-8。它们的来源、版本和错误码是三个不同字段，不能用“内容看起来相关”代替条件判断。

我们先规定：E102＋v2 只应返回 `csv-v2`；E102＋v1 只应返回 `csv-v1`。未知 v9 返回空列表，表示没有适用资料；空版本则抛出参数错误，表示调用条件不完整。这两种结果需要 Agent 采取不同后续动作：前者说明证据不足，后者先补齐条件。

## 下载与运行

将[知识检索工具](/examples/agent-lab/knowledge_tool.py)和[检索对照脚本](/examples/agent-lab/retrieval_demo.py)保存到同一目录。工具使用标准库关键词匹配，先过滤版本，再按命中词数量排序；它不是 Embedding、BM25 或向量检索的效果演示。

执行环境：终端中的 `python` 应指向 Python 3.12，当前目录包含以上两个文件。

```bash
python --version  # 先确认解释器版本。
python retrieval_demo.py  # 执行正常、空结果和错误参数的对照。
```

## 完整对照代码

```python
from knowledge_tool import search_knowledge  # 复用同目录中的只读检索工具。

def evidence_ids(documents: list[dict]) -> list[str]:  # 只展示稳定的证据标识，方便比较。
    return [document["id"] for document in documents]  # 返回资料ID，不把排序分数当答案可信度。

def search_without_version(query: str) -> list[dict]:  # 故意构造错误版本：合并两个版本的结果。
    documents = []  # 保存尚未按用户版本隔离的候选。
    for version in ("v1", "v2"):  # 逐个查询后直接混合，会丢失用户的版本条件。
        documents.extend(search_knowledge(query, version))  # 这里是本例要暴露的错误设计。
    return documents  # 调用方可能得到同错误码的两套处理方法。

def main() -> None:  # 用同一套演示资料观察正常、空结果与错误参数。
    mixed = search_without_version("E102")  # 先复现未限制版本的候选混入。
    print("未限定版本:", evidence_ids(mixed))  # 输出两份版本不同的证据。
    cases = [  # 以下各项只改问题或版本，便于逐项核查。
        ("限定 v2", "E102", "v2"),  # 新版E102应命中新版字段说明。
        ("限定 v1", "E102", "v1"),  # 旧版E102应保留旧版处理方法。
        ("编码错误", "E201", "v2"),  # 换错误码后应命中编码说明。
        ("未知版本", "E102", "v9"),  # 没有该版本资料时，应得到空列表。
    ]  # 结束固定的四组调用。
    for label, query, version in cases:  # 依次执行，保留标签便于对照输出。
        hits = search_knowledge(query, version)  # 正常调用显式传入用户的产品版本。
        print(label + ":", evidence_ids(hits))  # 把实际结果打印出来，不写预设的通过结论。
    try:  # 单独检查版本缺失的行为。
        search_knowledge("E102", "")  # 空版本不能被静默替换成最新版本。
    except ValueError as error:  # 工具契约用ValueError报告参数问题。
        print("空版本:", error)  # 明确区分参数错误和无匹配资料。
    try:  # 再检查返回数量的边界。
        search_knowledge("E102", "v2", top_k=0)  # 零条不在工具允许的1到5范围内。
    except ValueError as error:  # 参数非法时，不应继续执行检索。
        print("错误 top_k:", error)  # 输出真实校验信息。

if __name__ == "__main__":  # 作为脚本运行时才开始演示。
    main()  # 普通导入不会自动打印或执行演示。
```

`search_without_version()` 故意查询两个版本并合并结果，用来复现条件丢失。正常工具没有这种跨版本合并：调用方必须显式传版本。脚本只打印资料 ID，便于看清“候选出现了什么”，不让自然语言答案掩盖取数差异。

## 实际输出

```text
未限定版本: ['csv-v1', 'csv-v2']
限定 v2: ['csv-v2']
限定 v1: ['csv-v1']
编码错误: ['encoding-v2']
未知版本: []
空版本: version 必须是非空字符串
错误 top_k: top_k 必须是 1 到 5 的整数
```

前两行是关键对照：相同错误码不限定版本时得到两条，限定 v2 后只剩一条。E201 则命中编码说明。这里没有使用“召回更多就是更好”的判断，因为多出来的 v1 资料恰好是不适用于当前请求的候选。

## 改坏一处，看看哪里变了

把正常的 v2 调用替换为下面两行，仍在本脚本中运行：

```python
hits = search_without_version("E102")  # 故意丢掉用户给出的v2条件。
print(evidence_ids(hits))  # 实际会得到csv-v1与csv-v2两条证据。
```

这个错误容易被误判为“检索覆盖更广”。真正要检查的是调用参数是否传到了执行层，以及返回结果是否仍满足它。之后即使换成向量库，也应先保留版本过滤，再讨论语义召回；过滤条件本身错误，重排模型无法补回业务约束。

这一小例只验证词项和版本的行为。真实资料里的同义说法、跨片段问题、混合检索与重排，需要另建问题集比较；不能用这三条演示数据宣称知识库问答效果已经达标。

## 中文原文与技术依据

- 张高兴：[《张高兴的大模型开发实战：（二）使用 LangChain 构建本地知识库应用》](https://www.cnblogs.com/zhanggaoxing/p/18778949)。原文有 JSON 加载、元数据、Chroma 检索和问答代码，适合对照“内容字段与筛选条件怎样分开”。
- [LangChain 官方 Retrieval 说明](https://docs.langchain.com/oss/python/deepagents/retrieval)：核对已有知识库作为 Agent 工具或问答上下文的使用位置。

本文代码是独立编写的标准库示例，中文原文作为阅读入口；示例输出来自配套脚本，不代表原文项目或企业系统的运行成绩。
