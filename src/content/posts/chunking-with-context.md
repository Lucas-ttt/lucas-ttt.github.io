---
title: 18 个字符怎样切坏 customer_id：可运行的切片排错例子
description: 运行一个保留标题、版本和来源的字符切片脚本，观察字段被拆开的真实输出，并用原文还原与预算检查区分不同质量目标。
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-07-30T12:00:00+08:00
featured: false
draft: false
series: AI Agent 代码实操
seriesOrder: 2
noteType: 代码实操
tags:
  - rag
  - 文档处理
  - 开源研读
---

给每个片段补上版本和来源，检索就不会漏资料了吗？先运行一个很小的反例：正文只有 54 个字符，切分预算设为 18，最终每段都没有超限，也能准确拼回原文，但 `customer_id` 还是被切成了两半。

这篇把切分阶段单独拿出来排错，不接模型，也不安装文本切分框架。目的不是推荐 18 作为真实项目参数，而是让字符边界、来源位置和业务字段的关系直接出现在输出里。

## 目录

## 输入与预期检查

自编文档说明 v2 的 E102 错误，正文中包含 `customer_id` 和 UTF-8。每段携带标题、版本、来源、字符起止位置和正文。标题等元数据单独存放，没有偷偷拼进 18 字符的正文额度；以后组装模型输入时，仍需另算这些内容的实际 token 开销。

位置采用左闭右开区间。例如 `18:36` 对应 Python 的 `text[18:36]`，便于重新打开原文核对。脚本不删除空白、不插入重叠文本，因此可以用直接拼接检查有没有漏字符或重复字符。

## 完整代码

执行环境：Python 3.10 及以上，仅用标准语法。保存为 `chunk_context.py`，或直接[下载脚本](/examples/agent-lab/chunk_context.py)。

```python
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
```

## 运行与实际输出

在脚本所在目录，用 Windows PowerShell 执行：

```powershell
python chunk_context.py # 打印每段的位置与正文，再检查还原、长度和字段完整性。
```

本次运行输出：

```text
v2 0:18 'CSV 导入说明。先确认产品是 v2'
v2 18:36 '；E102 要检查 customer'
v2 36:54 '_id。文件使用 UTF-8 编码。'
拼回一致: True
每段不超预算: True
完整字段命中: False
```

第二段以 `customer` 结束，第三段以 `_id` 开始。如果后续工具逐段检查是否包含完整字段名，就没有任何单段能够命中。先保留这份失败输入与输出，再讨论调整切分策略，排错会更直接。

## 三个检查分别说明什么

“拼回一致”检查字符没有丢失；“每段不超预算”检查当前计量方式下的长度；“完整字段命中”检查这个业务条件是否还在单段内。前两项通过不能推出第三项通过，更不能推出模型回答正确。

同样，Python 的 `len()` 计算字符串字符数量，不是字节数，也不是目标模型的 token 数。本例明确采用字符预算，避免把脚本中的 18 误读成模型输入限制。换成特定模型的输入预算时，需要使用对应计量并把标题、历史与工具描述一起计入。

## 怎样修改，而不是只换一个更大数字

可以先把预算改为 24，保留同一份原文重新运行，观察字段是否完整、片段数量怎样变化。随后再比较按段落或句号切分、保护错误码与字段名等方案。一次只改一个规则，才能知道变化来自哪里；单个演示字段没有被拆开，不代表所有资料都适合这个参数。

还可以把 `max_chars` 改为 0，观察程序是否在进入循环前拒绝输入；更换标题或版本后，检查每一段的元数据是否同步。本例的片段ID依赖当前来源与序号，重新切分后不应假定旧引用还能指向相同正文，实际入库还需要版本化和引用更新策略。

## 中文原文与一手资料

- [溯光独立开发：Langchain Splitter 源码阅读笔记（一）](https://www.cnblogs.com/nanimono/p/19248329)：原文逐段分析长度函数、分隔符、合并与元数据位置，适合在看过本例输出后继续阅读。本文没有复制其中框架源码。
- [LangChain 官方 Text Splitter 文档](https://docs.langchain.com/oss/python/integrations/splitters/index)：比较字符、结构与语义等切分思路；参数是否合适仍需回到自己的文档与问题验证。
