from chunk_context import chunk_document  # 导入本篇完整代码中的原函数。

text = "CSV 导入说明。先确认产品是 v2；E102 要检查 customer_id。文件使用 UTF-8 编码。"  # 保持同一份原文。
for size in (18, 24, 36):  # 一次只改变字符预算。
    chunks = chunk_document(text, "CSV 导入", "v2", "demo/csv-v2.md", max_chars=size)  # 使用相同元数据。
    whole_field = any("customer_id" in chunk["text"] for chunk in chunks)  # 检查业务字段是否在单块内完整。
    print(size, len(chunks), whole_field)  # 分别输出预算、块数和字段检查结果。
