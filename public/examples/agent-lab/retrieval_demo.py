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
