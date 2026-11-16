---
title: "从精确匹配到候选精排：我的混合检索实验"
description: "对照词项、手工语义特征、排名融合与规则精排，分析每一步的收益、边界与额外开销。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-04-06T12:00:00+08:00
featured: false
draft: false
series: "AI Agent 开发实践"
seriesOrder: 5
noteType: 代码实操
tags: ["rag", "混合检索", "重排"]

modDatetime: 2026-11-03T13:03:44+00:00
---

我最初的检索工具依赖错误码、字段名和版本。对“v2 的 E102”这种输入，它很容易找到正确说明；换成“上传时提示找不到客户字段”，连续词项就未必存在于正文。这个变化让我开始把两种能力分开看：一条路径负责精确线索，另一条路径尝试覆盖自然语言改写。

但多加一条检索路径并不是完成优化。我还需要知道两路分数怎么合并，同一资料是否重复占位，粗排之后是否仍有缺少操作依据的概览页。为观察这些关系，我做了一个完全离线的小实验：词项召回、手工语义特征、RRF 融合和规则精排都能直接运行，输出每个阶段实际处理的候选。

## 目录

## 我先保留精确路径，再验证改写的缺口

错误码和字段名对这个场景很重要。E102 与 E201 只有几个字符的区别，却代表不同处理方向；`customer_id` 也不能随意替换为旧版的 `user_id`。如果把所有问题都交给模糊相似性判断，这些小差异可能被主题相近的内容掩盖。因此我保留词项路径，把它作为可以手工核对的基线。

另一方面，用户未必知道文档里使用的准确名称。我在示例里把“上传”与“导入”、“客户字段”与 `customer_id` 分别放进手工概念组，构造三维零一特征，并计算余弦相似度。这只是一个可以解释的特征实验，没有加载训练过的 Embedding 模型，也不能据此判断真实语义模型的效果。它的作用是把另一条候选路径接入相同流程，让改写查询的缺口可以被实际观察。

无论走哪一路，版本都先作为硬条件过滤。若先搜索全库，再希望重排“尽量优先 v2”，旧版仍然可能进入上下文。适用性不是一个可以靠其他分数抵消的偏好；我宁可让合法范围内返回空列表，也不借用不适用的资料来制造有答案的外观。

## 融合先解决候选如何合并

词项命中数和余弦相似度不在同一个尺度。我没有直接把它们相加，而是先只利用各自的名次：每一条排名贡献一个倒数名次分，同一资料跨路累加。代码中平滑常量显式设置为六十，名次从一开始，这些都是当前例子的约定，不代表所有实现的默认参数。

我用资料 ID 作为融合键，所以一份说明在两路同时命中后仍只占一个位置。去重不仅影响展示，也影响 Top-K 的实际覆盖。如果重复项占据了大半上下文，候选列表看起来很长，独立证据却可能很少。这里我只去重同一个 ID，没有实现不同文档之间的近重复识别，后者要避免误删版本差异和重要修订。

## 精排再判断已有候选是否更贴近任务

排障资料里还可能有概览页：它确实提到 E102，却只让读者继续查详细步骤。这样的候选并非毫不相关，但不能直接支撑“应该添加哪一列”。我因此在实验中保留一个规则精排：检查精确错误码，再检查正文是否包含可核对的字段或编码依据，观察第二阶段能否改变候选顺序。

这条规则不等同于真实的 cross-encoder。真实精排模型一般需要把问题与候选正文一起处理，候选数量和输入长度都会增加计算与等待；我的脚本只演示职责和执行位置。特别是，精排只能重新安排已召回的资料。如果详细说明没有进入候选，再强的第二阶段也不能从一个不存在的输入中恢复它。

## 完整代码：把每个阶段留在输出里

保存为 `hybrid_rerank.py`，或[下载脚本](/examples/agent-lab/hybrid_rerank.py)。代码只用 Python 3.12 标准库，没有网络调用和模型下载。

```python
import math  # 使用标准库计算手工特征的余弦相似度。
import re  # 保留错误码与英文标识的精确词项。

DOCUMENTS = [  # 所有资料为自编内容，前两条故意使用相同错误码。
    {"id": "csv-v1", "version": "v1", "code": "E102", "text": "CSV 导入缺少 user_id 列，检查首行表头。"},  # 旧版资料不应进入v2候选。
    {"id": "csv-v2", "version": "v2", "code": "E102", "text": "CSV 导入缺少 customer_id 列，检查首行表头。"},  # 当前版本字段要求。
    {"id": "encoding-v2", "version": "v2", "code": "E201", "text": "文件使用 UTF-8 编码，避免乱码。"},  # 与字段故障相邻但不同的原因。
    {"id": "overview-v2", "version": "v2", "code": "", "text": "E102 汇总页，请继续查看对应的详细排障步骤。"},  # 有精确词项却没有直接处理依据。
]  # 结束固定实验资料。
FEATURES = [("csv", "导入", "上传"), ("customer_id", "客户字段", "客户列"), ("utf-8", "编码", "乱码")]  # 手工概念组，仅演示语义改写信号。

def features(text):  # 构造三维可解释特征，不使用训练过的Embedding模型。
    lowered = text.lower()  # 统一英文大小写。
    return [float(any(word in lowered for word in group)) for group in FEATURES]  # 每个概念是否出现记为0或1。

def cosine(left, right):  # 计算两个手工向量的相似度。
    norm = math.sqrt(sum(value * value for value in left) * sum(value * value for value in right))  # 得到两向量长度乘积。
    return sum(a * b for a, b in zip(left, right)) / norm if norm else 0.0  # 空向量不制造相似命中。

def candidate_lists(query, version):  # 在同一个合法范围内分别生成词项和特征候选。
    allowed = [item for item in DOCUMENTS if item["version"] == version]  # 硬过滤先于每一路评分。
    terms = set(re.findall(r"[a-z0-9_]+", query.lower()))  # 错误码、CSV和字段名保留为精确词项。
    keyword = [(sum(term in (item["code"] + " " + item["text"]).lower() for term in terms), item["id"]) for item in allowed]  # 计算简单词项命中数。
    semantic = [(cosine(features(query), features(item["text"])), item["id"]) for item in allowed]  # 计算手工语义特征相似度。
    order = lambda rows: [identity for score, identity in sorted(rows, key=lambda row: (-row[0], row[1])) if score > 0]  # 稳定排序并排除零分。
    return order(keyword), order(semantic)  # 保留两种不同尺度的排名，不直接相加原始分。

def fuse(rankings, smoothing=60):  # 使用显式常量进行RRF名次融合。
    scores = {}  # 证据ID作为键，合并两路重复项。
    for ranking in rankings:  # 每一路只贡献它自己的名次信号。
        if len(ranking) != len(set(ranking)):  # 单路重复会不合理地放大得分。
            raise ValueError("单路候选不可重复")  # 将重复候选视为上游错误。
        for rank, identity in enumerate(ranking, 1):  # 名次明确从1开始。
            scores[identity] = scores.get(identity, 0.0) + 1 / (smoothing + rank)  # 同一资料跨路累加贡献。
    return [identity for identity, _ in sorted(scores.items(), key=lambda row: (-row[1], row[0]))]  # 相同得分按ID稳定打破平局。

def rerank(query, candidates, version):  # 用可检查的业务规则模拟第二阶段精排。
    by_id = {item["id"]: item for item in DOCUMENTS}  # 仅从已有资料取得内容。
    requested_code = re.search(r"E\d+", query.upper())  # 如果用户给出错误码，排序中保留这个精确条件。
    scored = []  # 只处理输入候选，不能从全库补回漏项。
    for position, identity in enumerate(candidates):  # 记录融合名次用于稳定打破同分。
        item = by_id[identity]  # 从候选身份回查正文。
        if item["version"] != version:  # 第二阶段也不接受错误版本。
            raise ValueError("候选版本不符")  # 不把硬性约束降成一个软分数。
        exact = int(requested_code is not None and item["code"] == requested_code.group())  # 精确错误码对应加一。
        actionable = int("customer_id" in item["text"] or "UTF-8" in item["text"])  # 本例人工定义能直接核对的处理依据。
        scored.append((exact + actionable, position, identity))  # 当前规则分并非模型置信度。
    return [identity for _, _, identity in sorted(scored, key=lambda row: (-row[0], row[1]))]  # 第二阶段只改变已有候选顺序。

if __name__ == "__main__":  # 运行固定查询，避免把手工规则当作真实模型评测。
    query = "上传报 E102，提示找不到客户字段"  # 错误码与自然语言改写同时出现。
    keyword, semantic = candidate_lists(query, "v2")  # 两路使用相同的版本范围。
    merged = fuse([keyword, semantic])  # 合并候选并按身份去重。
    ranked = rerank(query, merged, "v2")  # 用规则进行第二阶段对照。
    print("词项候选", keyword)  # 展示精确线索得到的资料。
    print("特征候选", semantic)  # 展示手工概念扩展得到的资料。
    print("融合候选", merged)  # 此时同一资料只占一个位置。
    print("重排结果", ranked)  # 核对有明确字段依据的资料是否靠前。
    print("处理数量", {"词项候选": len(keyword), "特征候选": len(semantic), "重排候选": len(merged)})  # 观察增加路径后的处理规模。
    print("噪声排前对照", rerank(query, ["overview-v2", "csv-v2"], "v2"))  # 手工构造错序，验证精排规则能改变顺序。
    missing = rerank(query, ["overview-v2"], "v2")  # 人为令详细资料在召回阶段缺失。
    print("漏召回后重排", missing)  # 重排不能凭空补回csv-v2。
    rewrite = candidate_lists("找不到客户字段", "v2")  # 另查一条没有英文精确词项的改写。
    print("改写词项候选", rewrite[0])  # 词项基线为空。
    print("改写特征候选", rewrite[1])  # 手工概念匹配能够产生候选。
```

```powershell
python hybrid_rerank.py # 查看两路候选、融合、重排和两组失败对照。
```

## 代码逐段解析

`candidate_lists` 先统一过滤范围，再分别计算精确命中数与手工特征相似度。返回的是两份排名，而非一个混合分数，这样我能在排错时看清某条资料来自哪一路。`features` 的概念组是人工编写的规则；加入真实向量服务时，需要记录模型、索引版本与输入配置，不能把本例的可解释特征直接换个名字当成真实语义检索。

`fuse` 只接受没有单路重复项的排名，将资料身份去重后累加名次贡献。`rerank` 再用相同身份回查正文，对输入候选评分，并继续拒绝版本冲突。它没有在缺少证据时自行搜索全库，这个限制让“召回漏了”和“排序排错了”能够在日志里分开。

我还保留了处理数量的输出。它不是完整成本统计，却能指出新增路径至少带来了哪些工作：额外一次候选生成、融合去重，以及对融合后资料的第二阶段处理。以后接入真实服务时，才需要在这些位置增加分段耗时、调用量、输入长度和费用记录。

## 本次结果：默认顺序没有改变，也是一条结论

```text
词项候选 ['csv-v2', 'overview-v2']
特征候选 ['csv-v2']
融合候选 ['csv-v2', 'overview-v2']
重排结果 ['csv-v2', 'overview-v2']
处理数量 {'词项候选': 2, '特征候选': 1, '重排候选': 2}
噪声排前对照 ['csv-v2', 'overview-v2']
漏召回后重排 ['overview-v2']
改写词项候选 []
改写特征候选 ['csv-v2']
```

默认输入同时提供 E102 和“客户字段”的改写，词项路径得到详细说明与概览页，特征路径只得到详细说明。融合后已经把 `csv-v2` 放在第一位，因此这次精排没有继续改变顺序。我没有把“模块都跑过了”写成检索效果提升；对这条问题，额外精排主要增加工作，没有展示出新的排序收益。

为了单独检查精排职责，我手工构造“概览页排前”的候选，结果详细说明回到前面。随后只给它一个概览候选，输出仍然只有概览，直接暴露了召回漏项无法靠精排弥补的边界。没有英文词项的“找不到客户字段”则让词项基线为空、手工特征路径有结果，说明这次规则扩展确实覆盖了指定改写，但不能推广成真实用户问题的总体收益。

## 我会在收益和额外开销之间做选择

如果资料少、问题主要是固定错误码，我会先把精确条件、元数据与文档质量做好。真实语义检索会增加向量化、索引维护和查询成本；真实精排通常还会增加一段不能忽略的等待。即使可以并行召回，融合和第二阶段也需要等待相应候选，端到端收益要用实际轨迹衡量。

下一步我会固定语料和开发问题，对照词项、语义、融合、融合加精排四组配置，分别记录证据覆盖、错误版本、重复候选、耗时和费用。只在开发集上选参数，再用未参与调整的问题观察是否仍然有效。这样决定某个模块是否保留时，依据是它补回了哪些失败、牺牲了什么，而不是架构图上多了一层。
