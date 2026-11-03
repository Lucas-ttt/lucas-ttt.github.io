def chunk_document(text: str, title: str, version: str, source: str, max_chars: int = 18) -> list[dict]:  # 按字符预算切分，并保留业务条件。
    if not isinstance(text, str) or not text:  # 拒绝空内容，避免生成没有证据的片段。
        raise ValueError("text 必须是非空字符串")  # 让调用方修正输入。
    metadata = {"title": title, "version": version, "source": source}  # 元数据不混入正文的字符预算。
    if any(not isinstance(value, str) or not value.strip() for value in metadata.values()):  # 检查标题、版本与来源。
        raise ValueError("title、version、source 必须是非空字符串")  # 不默默遗漏适用条件。
    if type(max_chars) is not int or max_chars < 1:  # 布尔值不作为有效字符预算。
        raise ValueError("max_chars 必须是正整数")  # 非正预算无法推进切分位置。
    chunks = []  # 按原文顺序收集片段。
    for start in range(0, len(text), max_chars):  # 每次移动固定数量的字符。
        end = min(start + max_chars, len(text))  # 最后一个片段可以短于预算。
        chunks.append({  # 一个片段既保存内容，也保存回查位置。
            "id": f"{source}#{len(chunks) + 1:03d}",  # 演示标识只在当前切分配置下有意义。
            **metadata,  # 每一段都携带相同的标题、版本与来源。
            "char_start": start, "char_end": end,  # 使用左闭右开的字符区间。
            "text": text[start:end],  # 不清理空白，保证可以准确拼回原文。
        })  # 完成当前片段。
    restored = "".join(chunk["text"] for chunk in chunks)  # 按生成顺序还原正文。
    if restored != text:  # 核查切分过程中是否丢失或重复字符。
        raise RuntimeError("切分结果不能还原原文")  # 这是切分错误，不应交给模型猜测修补。
    return chunks  # 返回可被检索或引用环节消费的片段列表。

if __name__ == "__main__":  # 直接运行，查看实际的切分边界。
    text = "CSV 导入说明。先确认产品是 v2；E102 要检查 customer_id。文件使用 UTF-8 编码。"  # 自编演示原文。
    chunks = chunk_document(text, "CSV 导入", "v2", "demo/csv-v2.md")  # 使用默认的十八字符预算。
    for item in chunks:  # 逐段打印版本、位置与文本。
        print(item["version"], f"{item['char_start']}:{item['char_end']}", repr(item["text"]))  # repr 保留可观察的空白。
    print("拼回一致:", "".join(item["text"] for item in chunks) == text)  # 展示实际还原检查结果。
    print("每段不超预算:", all(len(item["text"]) <= 18 for item in chunks))  # 十八指字符数，不是 token 数。
    print("完整字段命中:", any("customer_id" in item["text"] for item in chunks))  # 演示硬切分把字段拆开的实际问题。
