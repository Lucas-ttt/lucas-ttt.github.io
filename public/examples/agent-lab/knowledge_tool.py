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
