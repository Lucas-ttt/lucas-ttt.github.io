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
