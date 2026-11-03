def fuse_rankings(rankings: list[list[str]], smoothing: int = 60) -> list[tuple[str, float]]:  # 对预设名次进行融合。
    if type(smoothing) is not int or smoothing < 1:  # 这里只接受显式的正整数平滑常量。
        raise ValueError("smoothing 必须是正整数")  # 避免非法分母和含糊的布尔参数。
    scores: dict[str, float] = {}  # 证据ID作为键，防止同一资料重复占位。
    for ranking in rankings:  # 逐路处理候选名单。
        if len(ranking) != len(set(ranking)):  # 本例要求单路名单内不重复。
            raise ValueError("单路候选ID不可重复")  # 不让重复项人为增加得分。
        for rank, evidence_id in enumerate(ranking, start=1):  # 明确采用从一开始的名次。
            scores[evidence_id] = scores.get(evidence_id, 0.0) + 1 / (smoothing + rank)  # 累加名次贡献。
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))  # 降序排列，同分时保持可复查顺序。

rankings = [["csv-v2"], ["encoding-v2", "csv-v2"]]  # 两路排序是手工输入，不是实际模型输出。
result = fuse_rankings(rankings)  # 使用本例显式设定的平滑常量。
print([(evidence_id, round(score, 6)) for evidence_id, score in result])  # 仅为展示四舍五入，不改变排序。
