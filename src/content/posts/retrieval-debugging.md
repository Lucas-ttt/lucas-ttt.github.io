---
title: "原文有答案却没有命中：我怎样沿检索链路定位问题"
description: "固定同一输入，逐阶段观察解析、切片、索引、过滤与候选，用故障注入验证漏检原因。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-06-25T12:00:00+08:00
featured: true
draft: false
series: "AI Agent 开发实践"
seriesOrder: 3
noteType: 代码实操
tags: ["rag", "检索排错", "可观测性"]

modDatetime: 2026-11-03T13:03:44+00:00
---

排查知识库时，我最不愿意只盯着最终回答。“原文里有 `customer_id`，系统却说没有依据”可以由很多原因造成：文件没读进来、清洗删坏字段、索引缺资料、版本标错、候选被裁掉，或者正确证据根本没有进入最终上下文。它们表面上都像检索失败，修复位置却完全不同。

我因此给小型排障原型补了一组阶段轨迹。先固定问题、资料与版本，再一次只注入一个缺陷，保存每一步还能看见什么。这个实验不调用模型，目标是把生成前的问题找清楚；只有证据已经完整进入输入，才值得继续讨论生成环节。

## 目录

## 我从目标证据开始，逆向确认它经过哪里

这次查询固定为 `customer_id`，版本固定为 v2。原始资料里确实存在对应字段，正确目标是 `csv-v2`。我先找到这条目标，再顺着实际处理链检查：读取后的规范文本有没有它，当前索引有没有它，版本筛选是否保留它，词项检索是否返回它，组装上下文时是否采用了它。

这样做的前提是知道当前应该找回哪份资料。对于没有人工确认过的自然语言问题，不能看到空结果就先断定系统漏召回。我会先核对问题条件和原文位置，再写下期望证据；否则测试很容易变成依据实际输出不断修改解释。

我把排查顺序放在调参前面。目标资料根本没有进入索引时，调整 Top-K 不会把它变出来；目标字段在清洗时已经被删掉，换生成提示也无法恢复这个阶段丢失的信息。中间结果能帮助我先定位最早的差异，而不是在后面增加更多不相关的能力。

## 五个故障场景，只改变一个因素

| 场景 | 我注入的变化 | 需要看到的阶段差异 |
| --- | --- | --- |
| 正常基线 | 不修改任何阶段 | 证据从索引一直保留到上下文 |
| 索引缺失 | 移除当前索引里的目标记录 | 原资料存在，索引中没有目标 |
| 版本错误 | 将目标元数据标成 v1 | 正文仍在，v2 筛选把它排除 |
| 字段损坏 | 删除规范文本中的字段并重建词项 | 索引存在，但规范文本已经不完整 |
| 上下文丢失 | 检索成功后不采用命中资料 | 命中列表正确，上下文列表为空 |

这里有一个我特意处理的细节：字段损坏后，同步重建 `tokens` 和 `search_text`。如果只改显示正文却保留旧词项，查询仍可能命中，实验就变成一份内部不一致的数据，不能真实说明清洗造成的影响。故障注入也要尊重每个阶段的数据约定。

## 完整代码：把阶段证据留下来

将本脚本与第一篇的 `project_walkthrough.py` 放在同一目录。它们都只使用 Python 标准库。可以[下载排查脚本](/examples/agent-lab/retrieval_trace.py)，也可以复制下方代码保存为 `retrieval_trace.py`。

```python
import json  # 保留各阶段的实际观测结果。
import re  # 字段损坏实验需要同步重建词项。
from copy import deepcopy  # 变体只修改本次副本。
from project_walkthrough import DOCUMENTS, build_index, retrieve  # 使用同一组原始资料与真实索引。

def trace_case(fault):  # 一次只注入一种缺陷，便于验证因果。
    query, version = "customer_id", "v2"  # 固定问题和适用版本。
    original = next(row for row in DOCUMENTS if row["id"] == "csv-v2")  # 原始资料确实包含目标字段。
    index = deepcopy(build_index())  # 文件读取与入库在此实际执行。
    if fault == "index_missing":  # 模拟资料未进入当前索引。
        index = [row for row in index if row["id"] != "csv-v2"]  # 不修改原始资料。
    elif fault == "wrong_version":  # 模拟元数据标注错误。
        next(row for row in index if row["id"] == "csv-v2")["version"] = "v1"  # 正文仍在，但不符合本次筛选。
    elif fault == "parsed_field_lost":  # 模拟清洗时删坏字段。
        row = next(row for row in index if row["id"] == "csv-v2")  # 只改变目标记录。
        row["text"] = row["text"].replace("customer_id", "")  # 故意损坏规范文本。
        row["search_text"] = f"{row['error_code']} {row['text']}".lower()  # 索引必须对应损坏后的实际内容。
        row["tokens"] = sorted(set(re.findall(r"[a-z0-9_]+", row["search_text"])))  # 避免旧词项残留掩盖问题。
    target = next((row for row in index if row["id"] == "csv-v2"), None)  # 先检查入库而非直接调生成。
    version_ids = [row["id"] for row in index if row["version"] == version]  # 保存过滤后的候选身份。
    hits = retrieve(query, version, index=index)  # 真正执行本次变体上的检索。
    context = [] if fault == "context_dropped" else hits  # 模拟证据在组装上下文时丢失。
    if target is None:  # 依照链路顺序记录最早失败阶段。
        failed = "index_membership"  # 当前索引缺少目标资料。
    elif query not in target["text"]:  # 正文与原始资料不一致。
        failed = "normalized_text"  # 先修复提取或清洗。
    elif target["version"] != version:  # 内容正确但过滤条件不符。
        failed = "metadata_filter"  # 检查版本标注与请求条件。
    elif not hits:  # 资料和条件正确，再查评分与阈值。
        failed = "retrieval"  # 当前正常基线不会进入这里。
    elif not context:  # 命中了资料，下一阶段却没有采用。
        failed = "context_assembly"  # 生成模型尚未参与。
    else:  # 所有检查均保留了目标证据。
        failed = None  # 不宣称真实模型已经回答正确。
    return {"fault": fault, "source_has_field": query in original["text"], "indexed": target is not None, "version_ids": version_ids, "hit_ids": [row["id"] for row in hits], "context_ids": [row["id"] for row in context], "first_failed_stage": failed}  # 保留足够的中间证据。

if __name__ == "__main__":  # 五次实验互不污染。
    for fault in ("none", "index_missing", "wrong_version", "parsed_field_lost", "context_dropped"):  # 每次只改一个因素。
        print(json.dumps(trace_case(fault), ensure_ascii=False))  # 对比结果可直接定位最早差异。
```

## 代码逐段解析

每次实验重新执行 `build_index`，得到文件读取后真正建立的索引，再用深拷贝承载当前变体。这样前一条实验修改过的版本或正文不会污染下一条。原始资料始终保持不变，便于确认“源头确实有答案”这个前提仍然成立。

`target` 先检查目标记录是否属于当前索引。接下来的 `version_ids` 是过滤后仍可使用的候选，`hit_ids` 是实际检索返回，`context_ids` 是准备交给后续处理的证据。几个列表都使用同一套 ID，排查时可以直接比较，不需要凭自然语言相似程度猜测是不是同一段内容。

`first_failed_stage` 按链路顺序记录最早不满足预期的位置。它是本实验的定位结果，不是一个能自动识别所有故障的通用诊断器。真实系统可能同时存在多个错误，先修复一个阶段后，后续问题才会显现；这也是我保留完整轨迹，而不仅返回一个标签的原因。

正常分支最后记录空值，表示这几个生成前检查没有发现缺失。它没有检查真实模型是否忠于证据，也没有判断操作建议是否完整。对包含生成环节的系统，我会继续保存实际发送的消息、证据位置和最终回答，在这一层之后再核对引用支持与业务条件。

## 运行输出与定位结果

在同目录执行：

```powershell
python retrieval_trace.py # 顺序运行正常路径与四个独立故障变体。
```

本次 Python 3.12.14 的实际输出：

```text
{"fault": "none", "source_has_field": true, "indexed": true, "version_ids": ["csv-v2", "encoding-v2"], "hit_ids": ["csv-v2"], "context_ids": ["csv-v2"], "first_failed_stage": null}
{"fault": "index_missing", "source_has_field": true, "indexed": false, "version_ids": ["encoding-v2"], "hit_ids": [], "context_ids": [], "first_failed_stage": "index_membership"}
{"fault": "wrong_version", "source_has_field": true, "indexed": true, "version_ids": ["encoding-v2"], "hit_ids": [], "context_ids": [], "first_failed_stage": "metadata_filter"}
{"fault": "parsed_field_lost", "source_has_field": true, "indexed": true, "version_ids": ["csv-v2", "encoding-v2"], "hit_ids": [], "context_ids": [], "first_failed_stage": "normalized_text"}
{"fault": "context_dropped", "source_has_field": true, "indexed": true, "version_ids": ["csv-v2", "encoding-v2"], "hit_ids": ["csv-v2"], "context_ids": [], "first_failed_stage": "context_assembly"}
```

五行里 `source_has_field` 始终为真，说明原始资料一直有目标字段。索引缺失时，`indexed` 先变为假；版本错误时，索引仍有记录，却在 `version_ids` 中消失；字段损坏时，版本筛选保留目标，但规范文本检查先失败。最后一行甚至已经命中 `csv-v2`，只是上下文组装没有采用它。

这些对照让我能把“检索不到”拆成不同处理动作。入库缺失先查导入与更新记录；元数据错误先核对版本标注；规范文本丢失先回到解析和清洗；候选正确但上下文为空，先检查阈值、去重、预算和组装条件。只有资料、条件和当前索引都正确时，我才继续研究词项规则是否需要补同义表达或语义召回。

## 我会怎样把这个方法用到更大的资料库

数据量增加后，不适合把所有正文无差别打印到日志。我会保留请求标识、语料版本、目标证据 ID、过滤条件和阶段摘要；需要查看原文时，再通过受控方式回查。这样既能重放问题，也不会为了排错把敏感资料复制进普通日志。

排序阶段也要保留清楚的边界。候选已经存在但排名过低，可以研究重排、融合与截断；候选根本没有产生，重排模型无法凭空把它召回。版本和权限条件造成的排除，则需要先确认排除是否符合业务，不能为了提高命中率直接放宽所有过滤。

我最后会用相同输入复测修复，并补一条能够让错误实现失败的回归用例。一次正常输出只能证明那次输入走通，固定缺陷与修复前后轨迹才更容易说明变化来自哪里。这个习惯让后续的优化更有方向，也避免把每一个失败都归因于模型“不够聪明”。
