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
