---
title: "先拆开耗时，再决定缓存和预算：我的性能成本实验"
description: "分阶段记录耗时与演示用量，对照缓存和上下文预算，检查优化前后的证据与失败状态。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-01-13T12:00:00+08:00
featured: false
draft: false
tags: ["agent", "性能优化", "成本分析"]
series: "AI Agent 开发实践"
seriesOrder: 9
noteType: 代码实操
modDatetime: 2026-11-03T13:03:44+00:00
---

在知识库原型里，我没有先把“慢”归因于模型，也没有通过砍掉一半上下文就宣布优化完成。我先给解析、检索、重排和生成分别加上计时，再用同一条问题比较冷路径、证据缓存和预算裁剪。这样至少能看清，省下的是哪一段等待，减少费用的同时是否也丢掉了必要依据。

这次实验仍然使用本地知识库的真实检索入口，外部阶段则用异步等待替身模拟。它不连接真实模型，打印的时间是本机运行这段程序实际经过的时间；用量和单价另有明确的演示设定。我用它验证观测位置、缓存条件与质量检查，不能据此推算线上模型延迟或真实账单收益。

## 目录

## 我先给一次请求分段计时

只看总耗时，很难判断应该减少文档处理、调整检索，还是控制生成长度。我分别记录四个阶段，并另外保存端到端总时间。真实接入时，还应继续区分模型首个响应和完整输出，记录排队、连接重用、重试与取消；离线入库则单独统计，不能混进普通查询延迟。

这里用 `perf_counter` 记录实际时间，异步等待只是制造可观察的阶段差异。Windows 的调度粒度会让几毫秒的等待实际经历更久，因此我不会把 `sleep(0.003)` 直接当成测量结果。重复实验需要预热、足够样本与相同配置，再看中位数、尾部耗时和失败请求，而不是只保留一次最快的输出。

同样，日志需要足够定位，又不能无差别保存用户正文和密钥。我更关注请求标识、阶段名称、版本、语料修订、候选数量、用量和最终状态；需要核对证据时保留可回查的 ID，敏感内容按访问规则处理。

## 证据缓存的键，必须带上适用范围

我缓存的是检索并经过当前规则排序的证据，不是所有用户共享的一段答案。键包含规范问题、产品版本、语料修订和可信权限范围。问题相同但版本改变，不应拿到旧版结果；文档更新以后，旧修订也不应继续命中；权限范围不同，更不能为了节省一次查询而共享证据。

代码里的范围字符串是程序预设的实验输入。真实应用要先验证身份，再从服务端上下文得到范围，不能信任模型填入一个看起来合法的租户名称。键里带了范围，也不等于已经完成鉴权；它只是避免在已有可信范围之间误复用。

缓存还需要定义有效期、失效策略、容量和并发更新。这个实验仅使用进程内字典，强调哪些条件会改变结果。空列表同样可能是一次成功查询的结果，所以我用键是否存在判断命中，而不是用列表真假；服务异常则不写成一个“没有资料”的正常缓存。

## 完整观测脚本

将[耗时与费用脚本](/examples/agent-lab/latency_cost.py)与[知识库原型](/examples/agent-lab/project_walkthrough.py)放在同一目录。环境为 Python 3.12，仅用标准库，没有网络请求或实际计费。

```python
import asyncio  # 用可协作等待模拟外部阶段。
import json  # 打印测量值、成本口径与质量检查。
from time import perf_counter  # 使用单调高精度计时记录真实经过时间。
from project_walkthrough import build_index, retrieve  # 性能观测仍使用同一项目检索入口。

CACHE = {}  # 本地进程内的证据缓存，不保存真实用户数据。
INPUT_PRICE, OUTPUT_PRICE = 2.0, 8.0  # 自定义演示单价：每百万token的元数，不对应任何服务商。

async def pipeline(query, version, index, *, cache=False, evidence_limit=2, scope="trusted-demo", revision="manual-r1"):  # 范围由应用身份层提供，不交给模型选择。
    timings, started = {}, perf_counter()  # 同时保留分段和端到端计时。
    stage = perf_counter()  # 解析阶段单独开始。
    await asyncio.sleep(0.002)  # 模拟解析等待，不宣称是实际文件解析速度。
    normalized = query.strip()  # 只做与当前问题等价的简单规范化。
    timings["parse"] = (perf_counter() - stage) * 1000  # 记录实际经过时间。
    key = (normalized, version, revision, scope)  # 版本、语料修订和可信权限范围共同限定缓存。
    cache_hit = cache and key in CACHE  # 正常空列表同样可以有缓存记录。
    stage = perf_counter()  # 检索阶段独立记录。
    if cache_hit:  # 不再模拟一次远程检索等待。
        hits = [dict(row) for row in CACHE[key]]  # 返回副本，避免预算裁剪改坏缓存。
    else:  # 冷路径实际执行本地检索。
        await asyncio.sleep(0.006)  # 模拟检索服务的等待开销。
        hits = retrieve(normalized, version, top_k=2, index=index)  # 固定真实候选数量。
    timings["retrieve"] = (perf_counter() - stage) * 1000  # 缓存效果只在对应阶段解释。
    stage = perf_counter()  # 重排阶段单独记录。
    if not cache_hit and hits:  # 缓存存的是本轮规则排好序的证据。
        await asyncio.sleep(0.003)  # 这是重排等待替身，不是真实模型推理。
        hits = sorted(hits, key=lambda row: (-row["score"], row["id"]))  # 当前使用确定性规则重排。
    timings["rerank"] = (perf_counter() - stage) * 1000  # 不把这一数字归为真实重排模型延迟。
    if cache and not cache_hit:  # 成功完成检索后才保存该键。
        CACHE[key] = [dict(row) for row in hits]  # 空结果也保留，异常则不会进入这里。
    selected = hits[:evidence_limit]  # 预算裁剪发生在候选缓存之后。
    stage = perf_counter()  # 生成阶段单独记录。
    if selected:  # 无证据时不消耗这次生成预算。
        await asyncio.sleep(0.008 + 0.003 * len(selected))  # 用固定替身复现请求等待，不请求真实模型。
        usage = {"input_tokens": 160 + 80 * len(selected), "output_tokens": 40 * len(selected)}  # 替身预设用量，不是len字符推算真实token。
    else:  # 正常无依据状态直接结束。
        usage = {"input_tokens": 0, "output_tokens": 0}  # 当前流程没有发出生成请求。
    timings["generate"] = (perf_counter() - stage) * 1000  # 测量替身实际等待时间。
    cost = (usage["input_tokens"] * INPUT_PRICE + usage["output_tokens"] * OUTPUT_PRICE) / 1_000_000  # 输入输出按各自单价分别计价。
    ids = [row["id"] for row in selected]  # 裁剪后的证据才是本次实际使用内容。
    return {"cache_hit": cache_hit, "ids": ids, "status": "ok" if ids else "insufficient_evidence", "quality_ok": set(ids) == {"csv-v2", "encoding-v2"} if normalized == "E102 E201" and version == "v2" else None, "usage": usage, "estimated_yuan": round(cost, 6), "stage_ms": {key: round(value, 3) for key, value in timings.items()}, "total_ms": round((perf_counter() - started) * 1000, 3)}  # 无人工标注的问题质量记为未评估。

async def main():  # 对照同一查询的冷路径、缓存与过度裁剪。
    index = build_index()  # 索引构建不包含在在线阶段计时中。
    query = "E102 E201"  # 同时需要字段与编码两份证据。
    baseline = await pipeline(query, "v2", index)  # 不使用缓存的基线。
    await pipeline(query, "v2", index, cache=True)  # 单独预热，避免把冷请求当成缓存命中。
    cached = await pipeline(query, "v2", index, cache=True)  # 使用相同版本、修订和范围。
    reduced = await pipeline(query, "v2", index, cache=True, evidence_limit=1)  # 故意只留下第一条证据。
    for label, result in [("baseline", baseline), ("cached", cached), ("reduced", reduced)]:  # 数字来自本次实际运行。
        print(label, json.dumps(result, ensure_ascii=False))  # 公开取样值会随调度变化。
    for label, options in [("版本变化", {"version": "v1"}), ("范围变化", {"scope": "trusted-other"}), ("修订变化", {"revision": "manual-r2"})]:  # 改变任何一个可信条件都应失去原缓存命中。
        version = options.pop("version", "v2")  # 本地固定实验输入，不来自模型。
        result = await pipeline(query, version, index, cache=True, **options)  # 继续实际经过检索路径。
        print(label, "cache_hit", result["cache_hit"])  # 不泄露或复用原范围结果。
    empty = await pipeline("退款", "v2", index, cache=True)  # 库外请求不生成答案。
    print("库外问题", json.dumps({key: empty[key] for key in ("status", "ids", "usage", "estimated_yuan")}, ensure_ascii=False))  # 单列拒答与费用。
    assert baseline["ids"] == cached["ids"] and baseline["quality_ok"] and cached["quality_ok"]  # 缓存没有改变本例证据覆盖。
    assert not reduced["quality_ok"]  # 更便宜的裁剪不能被直接接受。

if __name__ == "__main__":  # 导入时不自动执行计时实验。
    asyncio.run(main())  # 本脚本无网络请求或真实计费。
```

## 代码逐段解析

冷路径实际调用 `retrieve`，并用独立等待表示远程阶段开销；缓存路径复制已经保存的证据，避免后续裁剪修改缓存本身。只有检索成功后才写入缓存，版本、范围和语料修订任一变化都形成新键。当前重排只是按本地分数与 ID 排序，等待替身不代表实际重排模型的推理。

`evidence_limit` 在缓存之后截取本次使用的资料。因此同一份候选可以比较不同预算，不需要偷偷修改检索算法。代码同时打印使用的 ID 与 `quality_ok`：对 E102 和 E201 的组合请求，字段资料与编码资料都必须保留。没有人工标注的其他问题记为未评估，不默认算通过。这个检查只覆盖本例的证据完整性，接真实模型以后还要检查答案是否忠于它们。

用量由替身预先设定：固定提示占一百六十个输入 token，每份证据增加八十个，每份输出占四十个。它不是把 Python 字符数当真实 token，也不是读取了外部模型的用量。费用计算使用自定义的每百万输入二元、输出八元，分别相乘后相加，只用于演示预算计算。真实服务应读取实际 usage，并与服务的缓存、推理用量及账单口径核对。

## 一次本机取样，分清缓存到底省了什么

```powershell
python latency_cost.py # 对比冷路径、缓存命中、过度裁剪与缓存隔离。
```

下面是本次 Python 3.12.14 的一次测量摘要，时间单位为毫秒，重复运行会随系统调度变化：

```text
baseline: parse=2.213 retrieve=16.478 rerank=15.435 generate=15.207 total=49.356
cached:   parse=15.163 retrieve=0.002 rerank=0.000 generate=15.887 total=31.069
reduced:  parse=15.221 retrieve=0.002 rerank=0.000 generate=16.411 total=31.648
```

完整输出还保留了三种配置的证据与费用。冷路径和缓存路径都使用 `csv-v2`、`encoding-v2`，质量检查通过；演示用量同为输入三百二十、输出八十，试算费用同为零点零零一二八元。证据缓存绕过了检索与规则重排等待，却没有取消生成，因此这次不能宣称它降低了模型调用费用。

解析阶段在三次请求中也有明显抖动，说明一次总时间差异不能全部换算成稳定收益。我更看重缓存命中时对应阶段是否确实被绕过，以及证据是否一致。真实优化还需要在同样问题分布、并发与预热条件下反复测量，再决定配置。

## 更便宜的那次请求，没有通过质量检查

把证据上限改成一以后，程序只保留 `csv-v2`。演示用量变为输入二百四十、输出四十，试算费用降为零点零零零八元，但 `quality_ok` 变成假：用户同时需要编码要求，当前上下文已经丢掉了它。这个结果不能作为一次可接受的优化。

我会先尝试去掉重复片段、保留必要条件，再控制冗余解释与输出长度。模型分层、结果缓存或批量请求也可以考虑，但都要建立对应的有效期、权限、失败状态和质量回归。某种方法减少 token 数，不代表它能同时满足业务信息完整性。

## 把无依据请求与缓存边界一起复核

版本、权限范围和语料修订分别改变后，三次缓存命中标记都为假；它们重新走了当前条件的查询路径。库外的“退款”问题返回无依据状态，使用量与演示费用为零，因为这个流程没有发送生成请求。检索异常、资料为空与生成失败仍需要分别处理，不能为了节省费用把异常当成正常拒答。

这轮实验留下了一个明确顺序：先定位阶段，再控制重复工作，再检查用量，最后把所有变化放回固定问题与失败样例中验证。对当前原型，我接受保持证据不变的缓存方案，拒绝丢失编码依据的裁剪。接上真实服务之后，会继续用实际阶段耗时、用量和回答记录替换替身设定。
