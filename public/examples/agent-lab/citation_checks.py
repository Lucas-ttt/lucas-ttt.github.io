from knowledge_tool import search_knowledge  # 取得本次调用实际返回的证据。

def check_citations(citation_ids: list[str], documents: list[dict], version: str) -> list[str]:  # 只校验来源与版本。
    if not citation_ids:  # 回答没有给出任何引用时先报告缺失。
        return ["缺少引用"]  # 这不是对答案语义的判定。
    evidence = {document["id"]: document for document in documents}  # 为本次检索建立白名单。
    errors = []  # 汇总检查结果，交给调用方决定如何反馈。
    for citation_id in citation_ids:  # 对回答中的每一个引用标识执行相同检查。
        if citation_id not in evidence:  # 全库存在的ID也不能代替本次检索证据。
            errors.append(f"不属于本次检索: {citation_id}")  # 记录越出证据集合的引用。
            continue  # 缺少本次证据时不再访问对应字典。
        document = evidence[citation_id]  # 取到实际被检索到的文档。
        if document["version"] != version:  # 防止上游检索混入其他版本资料。
            errors.append(f"版本不符: {citation_id}")  # 版本冲突与引用不存在分别报告。
    return errors  # 空列表表示这两项校验通过，不表示答案必然正确。

def main() -> None:  # 演示四种结构问题和一个语义边界。
    current = search_knowledge("E102", "v2")  # 当前用户明确使用v2。
    legacy = search_knowledge("E102", "v1")  # 仅用于模拟上游误传旧版本证据。
    cases = [  # 每个样例给出本次证据集合与待检查引用。
        ("正常引用", ["csv-v2"], current),  # ID与版本都对应本次请求。
        ("旧版 ID", ["csv-v1"], current),  # 全库有此ID，但本次没有检索到它。
        ("未知 ID", ["made-up"], current),  # 模拟模型生成了不存在的标识。
        ("混入旧证据", ["csv-v1"], legacy),  # ID在集合内，但版本仍然错误。
        ("没有引用", [], current),  # 没有引用需要单独反馈。
    ]  # 结束五种检查输入。
    for label, citation_ids, documents in cases:  # 用相同函数检查每种情况。
        errors = check_citations(citation_ids, documents, "v2")  # 请求版本始终是v2。
        print(label + ":", errors or "通过")  # 通过只指ID与版本两项条件。
    bad_answer = "请在 CSV 表头添加 user_id"  # 故意给出不适用于v2的错误建议。
    errors = check_citations(["csv-v2"], current, "v2")  # 合法引用仍能附在错误建议后面。
    print("错误建议的 ID 检查:", errors or "通过")  # 复现结构校验无法覆盖语义的问题。
    print("仍需核查:", bad_answer, "；v2 原文要求 customer_id")  # 提醒逐条核对结论支持关系。

if __name__ == "__main__":  # 保证导入校验函数时不会执行示例。
    main()  # 开始本地确定性演示。
