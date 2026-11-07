from project_walkthrough import retrieve  # 项目、工作流与工具共用同一个版本过滤和精确词项检索入口。


def search_knowledge(query: str, version: str, top_k: int = 3) -> list[dict]:
    """返回适用原文；英文标识和错误码精确匹配，中文仍使用子串基线。"""
    hits = retrieve(query, version, top_k=top_k)  # 参数校验、索引与排名统一由项目核心处理。
    return [
        {key: value for key, value in hit.items() if key != "score"}
        for hit in hits
    ]  # 保持已有工具契约，不向调用方暴露内部词项得分。


if __name__ == "__main__":  # 直接执行时演示三个独立问题。
    for version in ("v2", "v1", "v9"):
        hits = search_knowledge("E102", version)
        print(version, [item["id"] for item in hits])
