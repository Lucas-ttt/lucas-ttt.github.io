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
