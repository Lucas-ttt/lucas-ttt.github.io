---
title: "我如何拆分手册：保住表头、长段落和跨段条件"
description: "用结构化切片实验处理表格、长段落与相邻上下文，保留字段、版本和可回查位置。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-04-27T12:00:00+08:00
featured: false
draft: false
series: "AI Agent 开发实践"
seriesOrder: 4
noteType: 代码实操
tags: ["rag", "文档处理", "上下文"]

modDatetime: 2026-11-03T13:03:44+00:00
---

我最早检查文档切片时，主要看两个结果：片段有没有超过预算，拼回去有没有丢字。后来把排障手册放进这个流程，我发现检索真正依赖的东西往往更细：表格里的一个值需要对应的表头，处理动作需要适用条件，英文标识需要完整保留。单纯控制长度，并不能保证这些信息一起进入候选。

这次我用一份自编的 CSV 导入手册重新做了实验。材料包含 v2 的适用范围、一段较长的操作说明、一张 E102/E201 排障表，以及分成两段的前提和操作。我的目标不是写一个通用 Markdown 解析器，而是把这三类结构的处理规则落到代码里，再从输出检查它们保住了什么。

## 目录

## 我先把切片的验收条件改了

对这个技术支持场景，我关心的是检索到一条证据后，是否仍能理解它的适用范围和处理动作。我给每个片段保留文档标识、版本、章节、适用条件、结构类型与正文。版本是执行过滤的字段，章节帮助阅读，条件则决定相同动作能否在当前任务里使用。这些信息不应该依靠一个很远的旧片段偶然被同时召回。

我也没有继续用“全文原样拼回”作为唯一标准。表格按行重复表头后，拼接结果本来就会包含重复内容；适用条件被放进结构字段后，也不再表现为一段独立正文。因此现在的检查分别关注：长段有没有漏掉单元，字段是否完整，表格行是否携带表头，以及上下文组装时是否带上条件。每一种检查都对应具体的丢失方式。

## 长段落先按句子组织，字段作为原子保留

我把正文预算设成八十个 Python 字符。这个数字只是让小样例产生可观察的边界，不代表某种模型的最佳长度。代码先识别中文句子，能够整体装下的句子一起合并；单句已经很长时，再继续拆成较小单元。英文单词、带下划线的字段名和带连字符的编码名称作为完整单元保留。

这个策略保护了 `customer_id` 和 `UTF-8`，但它并不理解所有业务语义。日期范围、否定条件或一整条操作链仍可能需要更专门的边界规则。我把它看作对固定步长基线的一次明确改进，而没有把正则表达式称作语义理解。若单个字段已经比预算长，程序直接报错，让上层决定调整预算或使用另一种表示，不悄悄切开后假装处理成功。

## 表格按数据行切，列的含义跟着走

手册里的表格只有错误码、原因和处理三列。我让每个数据行都携带同一张表的表头与分隔行，形成一份可以单独阅读的证据。这样召回 E102 行时，可以看清“缺少必填列”属于原因，“核对 customer_id”属于处理动作。只留下几个单元格值，生成阶段很容易把它们的关系说反。

代码同时检查每行列数与表头一致，并在完整一行超过预算时停止。这里没有处理合并单元格、转义竖线、嵌套表格或扫描 PDF 的版面识别。遇到这些输入，需要先得到可靠的结构化结果，再进入本例的分块规则。把不支持的结构当作普通行吞下去，只会让后面的检索与生成难以定位原始错误。

## 完整实现与运行方式

将下面代码保存为 `structured_chunking.py`，或[下载完整脚本](/examples/agent-lab/structured_chunking.py)。只需要 Python 3.12 标准库，不会访问网络或已有业务文件。

```python
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
```

执行命令：

```powershell
python structured_chunking.py # 查看固定步长对照、结构切片和相邻片段补充结果。
```

## 代码逐段解析：分块与组装是两道预算

`split_paragraph` 只负责正文切片。它先让片段长度可控，再保护明确的英文标识。`chunk_manual` 则在读取每个块时维护当前章节和适用条件，为不同结构统一生成元数据。这让表格分支和段落分支返回相同的字段，后面的检索与上下文组装不必为每一种结构重新猜测来源。

`render` 是另一条关键边界：实际交给生成环节的内容除了正文，还包含标题、版本和适用条件。因此我没有拿正文八十字符的检查代替整段上下文检查。`expand_context` 在每次尝试补入邻片时，都先渲染完整候选，再加上分隔符计算字符数。未来采用特定模型时，还要换成对应的 token 计量，并给系统提示、当前问题和输出留出空间。

邻接扩展以已经命中的片段为中心，先确认版本一致，再只在同一份文档内寻找前后片。它优先保留命中证据，补前一片后再尝试后一片，最后恢复原文顺序。这个例子不按主题相似度跨文件拼接，因为相同错误码并不足以证明两份资料可以合并使用。

## 实际输出让我看到了三种不同约束

```text
固定步长24字段完整 False
同预算保护字段完整 True
片段类型 ['paragraph', 'paragraph', 'table_row', 'table_row', 'paragraph', 'paragraph']
表格行保留表头 True
字段完整 True
条件覆盖 True
正文长度 [80, 28, 71, 65, 22, 21]
跨段补充 ['manual-v2:4', 'manual-v2:5']
上下文字符 117
小预算错误 单个标识超过预算，需要调整策略
```

固定二十四字符的对照故意忽略字段边界，完整字段检查失败；同样用二十四字符预算调用保护规则，完整字段检查通过。这个对照才把预算保持不变，单独观察边界策略的影响。完整手册示例另外使用八十字符预算，目的是容纳每一条带表头的完整表格行，不能把这两组不同预算直接当成检索效果比较。

完整手册的长段产生八十与二十八字符的两块，表格两行分别占七十一和六十五字符。长度结果说明当前规则确实执行了，但它仍不能单独证明所有问题都能被回答。

最后两段中，前一段要求确认 v2 并保留备份，后一段才说明补齐字段和重新验证。我以后一段为命中点，允许补入相邻前提，得到两个片段、共一百一二十四个渲染后字符。这样当前上下文既有动作，也能看见动作之前的条件。若预算装不下邻片，函数保留命中块，而不是跨文档寻找一段看起来更短的替代说明。

## 我保留的限制和下一步改进

这次实现证明的是小型 Markdown 手册的处理规则。表格重复表头会增加索引和上下文体积，邻接扩展也会引入额外文本，二者都要在检索问题集上观察收益。某条字段检查通过以后，我仍会增加“表头缺失”“否定词被拆开”“操作条件在前一段”等样例，避免所有规则只照顾这一份手册。

后续我会优先补两个能力：为不同文档类型保留更可靠的位置映射，以及在相邻片段补充时按真实模型预算计量。重新切分也会改变片段含义，因此索引更新与旧引用失效需要一起处理。我的做法是先保存明确的输入、切片结果和失败原因，再调整规则；只有能指出哪一种信息被保住了，切分优化才有可复查的依据。
