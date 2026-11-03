import re  # 使用标准库识别句子和需要保护的英文标识。

MANUAL = """# CSV 导入

适用条件：产品 v2，执行 CSV 导入。

导入前应备份文件并确认当前模板。表头必须保留 customer_id，不能用旧模板的 user_id 代替。出现 E102 时先核对首行，不要直接修改业务数据。文件较大时还要检查编码，并记录原始文件名，便于重现问题。

| 错误码 | 原因 | 处理 |
| --- | --- | --- |
| E102 | 缺少必填列 | 核对 customer_id |
| E201 | 编码不匹配 | 转为 UTF-8 |

操作前先确认当前文件属于 v2，并保留备份。

随后补齐必填列，再按原始导入步骤重新验证。
"""  # 自编手册同时覆盖长段落、表格和跨段操作条件。

def split_paragraph(text, max_chars):  # 先按句子组织，过长句再保护标识切分。
    if type(max_chars) is not int or max_chars < 1:  # 字符预算必须是真正的正整数。
        raise ValueError("max_chars 必须是正整数")  # 不接受零步长或布尔值。
    pieces, current = [], ""  # 保存已完成片段和当前片段。
    for sentence in re.findall(r"[^。！？]+[。！？]?", text):  # 优先保留中文句子边界。
        atoms = [sentence] if len(sentence) <= max_chars else re.findall(r"[A-Za-z_][A-Za-z0-9_-]*|.", sentence, re.S)  # 过长句中的字段名不拆开。
        for atom in atoms:  # 逐个检查句子或受保护单元。
            if len(atom) > max_chars:  # 单个不可拆字段也可能超过预算。
                raise ValueError("单个标识超过预算，需要调整策略")  # 显式失败，避免静默截断字段。
            if current and len(current) + len(atom) > max_chars:  # 当前片段无法继续容纳该单元。
                pieces.append(current)  # 保存完整的已有内容。
                current = ""  # 为下一个片段重新累计。
            current += atom  # 将完整单元加入当前片段。
    if current:  # 保存最后一个非空片段。
        pieces.append(current)  # 不丢掉段落末尾。
    return pieces  # 结果只包含正文，标题和适用条件另外保存。

def chunk_manual(text, document_id="manual-v2", version="v2", max_chars=80):  # 为单份手册构建结构化切片。
    chunks, section, condition = [], "", ""  # 持续保存当前章节与适用条件。
    def append(kind, content):  # 统一生成元数据，防止各分支丢字段。
        chunks.append({"id": f"{document_id}:{len(chunks)}", "document": document_id, "version": version, "section": section, "condition": condition, "kind": kind, "text": content})  # 标识仅对本次文档版本有效。
    for block in text.strip().split("\n\n"):  # 此演示只解析明确的空行分块 Markdown。
        block = block.strip()  # 去掉块外空白，不改写字段内容。
        if block.startswith("# "):  # 一级标题成为后续片段的上下文。
            section = block[2:].strip()  # 保存标题，不让它独占一个弱证据块。
        elif block.startswith("适用条件："):  # 将明确的适用范围复制为结构化条件。
            condition = block  # 不依靠后续模型从远处历史里猜测版本。
        elif block.startswith("|"):  # 表格按行切分，并为每行重复表头。
            lines = block.splitlines()  # 取得表头、分隔行与数据行。
            if len(lines) < 3:  # 不完整表格不能按正常数据处理。
                raise ValueError("表格至少需要表头、分隔行和数据行")  # 明确暴露解析失败。
            columns = len(lines[0].strip("|").split("|"))  # 记录当前表格列数。
            for row in lines[2:]:  # 每个数据行单独组织为可读证据。
                if len(row.strip("|").split("|")) != columns:  # 检查表头与数据列是否对齐。
                    raise ValueError("表格列数不一致")  # 不把错位单元交给后续生成。
                content = "\n".join([lines[0], lines[1], row])  # 每片都包含表头、分隔行和当前行。
                if len(content) > max_chars:  # 整行过长时需要专门的宽表策略。
                    raise ValueError("完整表格行超过预算")  # 本例不强拆单元格。
                append("table_row", content)  # 保留该行自己的章节与版本。
        else:  # 普通段落按照句子和字符预算处理。
            for part in split_paragraph(block, max_chars):  # 长段落拆为若干完整单元。
                append("paragraph", part)  # 各片共享明确的适用条件。
    return chunks  # 返回有顺序的结构化片段。

def render(chunk):  # 将元数据与正文一起组织为实际上下文。
    return f"{chunk['section']} | {chunk['version']} | {chunk['condition']}\n{chunk['text']}"  # 标题和条件也要计入后续上下文预算。

def expand_context(chunks, anchor_id, version, max_chars):  # 有条件地补入同文档相邻片段。
    anchor = next(item for item in chunks if item["id"] == anchor_id)  # 定位本次检索命中的片段。
    if anchor["version"] != version:  # 先验证命中片段是否适用。
        raise ValueError("命中片段版本不符")  # 不能跨版本拼接来补足信息。
    allowed = [item for item in chunks if item["document"] == anchor["document"] and item["version"] == version]  # 邻接范围限定为同文档版本。
    position = allowed.index(anchor)  # 在合法的文档顺序中查找位置。
    selected = [anchor]  # 优先保留本次确实命中的片段。
    if len(render(anchor)) > max_chars:  # 命中片段本身超出预算时不能静默丢失。
        raise ValueError("命中片段超过上下文预算")  # 交由上层缩减或重构上下文。
    for offset in (-1, 1):  # 按固定顺序尝试补充前一片与后一片。
        neighbor = position + offset  # 计算邻片位置。
        if 0 <= neighbor < len(allowed):  # 文档首尾没有对应邻片。
            proposal = sorted(selected + [allowed[neighbor]], key=lambda item: chunks.index(item))  # 恢复原始文档顺序。
            if len("\n\n".join(render(item) for item in proposal)) <= max_chars:  # 实际渲染后再核对总字符数。
                selected = proposal  # 只有满足预算的邻片才进入结果。
    return selected  # 不扩大到同主题的其他文档。

if __name__ == "__main__":  # 直接运行时完成三类结构检查。
    paragraph = MANUAL.strip().split("\n\n")[2]  # 固定同一段原文作为朴素切片对照。
    naive = [paragraph[start:start + 24] for start in range(0, len(paragraph), 24)]  # 用固定二十四字符步长构造边界失败对照。
    print("固定步长24字段完整", any("customer_id" in text for text in naive))  # 检查原始字段是否仍存在于某个单块。
    print("同预算保护字段完整", any("customer_id" in text for text in split_paragraph(paragraph, 24)))  # 在相同二十四字符预算下比较保护规则。
    chunks = chunk_manual(MANUAL)  # 使用同一份自编手册建立切片。
    print("片段类型", [item["kind"] for item in chunks])  # 观察长段落与表格分别产生什么。
    print("表格行保留表头", all("| 错误码 | 原因 | 处理 |" in item["text"] for item in chunks if item["kind"] == "table_row"))  # 核对每行证据的列含义。
    print("字段完整", any("customer_id" in item["text"] for item in chunks))  # 检查字段没有在所有片段中断裂。
    print("条件覆盖", all("产品 v2" in item["condition"] for item in chunks))  # 核对跨段适用条件可见。
    print("正文长度", [len(item["text"]) for item in chunks])  # 对照段落和完整表格行的字符预算。
    expanded = expand_context(chunks, chunks[-1]["id"], "v2", 220)  # 为最后一段补入同文档的操作前提。
    print("跨段补充", [item["id"] for item in expanded])  # 展示实际加入的相邻片段。
    print("上下文字符", len("\n\n".join(render(item) for item in expanded)))  # 计入重复标题、条件与分隔符。
    try:  # 额外复现一个不能静默处理的边界。
        split_paragraph("customer_id", 5)  # 单个完整字段已经超过预算。
    except ValueError as error:  # 捕获本次预期的失败。
        print("小预算错误", error)  # 用明确状态提示需要调整策略。
