---
title: "从排障资料到可回查答案：我的知识库原型实践"
description: "围绕版本冲突搭建一个离线知识库原型，记录我处理的模块、实际数据链路与验证结果。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-11-01T12:00:00+08:00
featured: true
draft: false
series: "AI Agent 开发实践"
seriesOrder: 1
noteType: 代码实操
tags: ["rag", "项目实践", "python"]

modDatetime: 2026-11-03T13:03:44+00:00
---

我做这组知识库实践时，先选了一个足够具体的问题：同样是 CSV 导入报 E102，v1 要检查 `user_id`，v2 要检查 `customer_id`。如果系统只认错误码，不保留产品版本，找到了文字也可能给出错误建议。我先把“资料从哪里来、命中哪一条、依据怎样到达输出”连成一条能回看的链路。

这篇记录的是一个个人离线原型。数据只有三份自编排障说明，运行不需要模型密钥，也不连接企业系统。我先用词项检索和原文抽取验证处理过程，把需要接入模型、真实资料和身份系统的部分留在明确的接口后面。这样每个结果都有对应输入，不会把一段流畅回答当成整个系统已经有效。

## 目录

## 我先限定了一个可验证的使用场景

原型面对的是软件使用者已经知道产品版本、能够提供错误码的排障任务。正常输入是“v2 的 E102”，希望拿回适用于 v2 的说明，并能看到资料标识。未知版本应该得到没有适用依据的状态，缺少版本则应该先修正输入。这里没有接入订单、账户或实时交易，三类数据也不应由同一份文档库承担。

我把目标写成三个可以直接观察的条件：同错误码不串版本；输出保留本次实际检索到的依据；没有依据时结束于明确状态。它们比“做一个智能知识库”具体，也能帮助我决定最先实现什么。搜索框、聊天历史和界面样式都可以后续增加，错误版本的资料却会直接破坏排障建议。

## 我负责串起的模块与数据边界

在这次原型里，我把实现范围集中在资料读取、文本规范化、片段元数据、版本过滤、证据返回和运行验证。下面的代码实际覆盖这些环节。资料本身是为实验编写的，不将企业数据治理、生产运维或外部模型效果计入已经完成的范围。

| 模块 | 这次实现 | 我观察的输出 |
| --- | --- | --- |
| 资料输入 | 临时目录里的三份 UTF-8 文件 | 读取后的实际正文 |
| 规范化与切片 | 保留字段名，按空段落分块 | 片段正文及资料身份 |
| 内存索引 | 错误码、英文词项与中文可查文本 | 当前索引的证据 ID |
| 在线检索 | 先按版本过滤，再计算词项命中 | 排序后的适用证据 |
| 回答输出 | 抽取实际返回原文并附资料标识 | 正常或证据不足状态 |

我刻意让离线构建和在线查询分别成为函数。`build_index` 负责将资料变成可检索对象，`retrieve` 只消费当前索引，`answer` 则处理证据到输出的转换。后面比较缓存或评测时，可以复用同一份索引，不必让每次查询都重新读取文件。

## 完整代码：让每一段处理真的参与结果

代码使用 Python 3.12 和标准库。保存为 `project_walkthrough.py`，也可[下载脚本](/examples/agent-lab/project_walkthrough.py)。临时文件由程序独立创建并清理，不读写已有业务文件。

```python
import json  # 以结构化结果显示原型的实际行为。
import re  # 用明确的词项规则建立小型离线索引。
import unicodedata  # 统一文本表示，但保留字段名和错误码。
from pathlib import Path  # 使用固定文件名定位本次演示资料。
from tempfile import TemporaryDirectory  # 文件只写入独立临时目录。

DOCUMENTS = [  # 三条自编资料用于复现同错误码、不同版本的问题。
    {"id": "csv-v1", "version": "v1", "error_code": "E102", "text": "CSV 导入缺少 user_id 列，检查首行表头。", "source": "demo/csv-v1.md"},  # 旧版字段。
    {"id": "csv-v2", "version": "v2", "error_code": "E102", "text": "CSV 导入缺少 customer_id 列，检查首行表头。", "source": "demo/csv-v2.md"},  # 新版字段。
    {"id": "encoding-v2", "version": "v2", "error_code": "E201", "text": "文件应使用 UTF-8 编码，避免出现乱码。", "source": "demo/encoding-v2.md"},  # 编码说明。
]  # 资料与结果均属于本地演示。

def normalize(text):  # 只合并横向空白，保留段落和业务标识。
    return re.sub(r"[ \t]+", " ", unicodedata.normalize("NFC", text)).strip()  # 不删除下划线或数字。

def build_index():  # 实际走文件读取、规范化、切片和索引构建。
    index = []  # 返回值是本次真正供检索使用的内存索引。
    with TemporaryDirectory(prefix="lucas-support-") as folder:  # 不接触用户已有文件。
        for document in DOCUMENTS:  # 将自编正文保存为三份 UTF-8 文件。
            path = Path(folder) / Path(document["source"]).name  # 文件名仅来自固定演示配置。
            path.write_text(document["text"] + "\n", encoding="utf-8")  # 产生本次输入文件。
            text = normalize(path.read_text(encoding="utf-8"))  # 实际读取刚保存的文件。
            paragraphs = [part for part in text.split("\n\n") if part.strip()]  # 当前三份短文各形成一块。
            for number, paragraph in enumerate(paragraphs):  # 多段资料会得到独立片段身份。
                chunk = {key: document[key] for key in ("id", "version", "error_code", "source")}  # 复制证据元数据。
                chunk["id"] = document["id"] if len(paragraphs) == 1 else f"{document['id']}#{number}"  # 短文保持稳定示例ID。
                chunk["text"] = paragraph  # 使用读取和切分后的真实正文。
                searchable = f"{chunk['error_code']} {paragraph}".lower()  # 编号和正文一起进入词项层。
                chunk["tokens"] = sorted(set(re.findall(r"[a-z0-9_]+", searchable)))  # 保存精确词项供英文和编号匹配。
                chunk["search_text"] = searchable  # 中文暂用子串基线匹配。
                index.append(chunk)  # 检索函数之后直接使用这份索引。
    return index  # 临时文件清理后，正文与来源标识仍保留在索引中。

def retrieve(query, version, top_k=3, index=None):  # 查询可以复用已构建索引。
    if not isinstance(query, str) or not query.strip():  # 问题缺失属于输入错误。
        raise ValueError("query 必须是非空字符串")  # 不把错误输入伪装成无命中。
    if not isinstance(version, str) or not version.strip():  # 不猜测用户正在使用的版本。
        raise ValueError("version 必须是非空字符串")  # 版本约束必须显式存在。
    if type(top_k) is not int or not 1 <= top_k <= 5:  # 排除布尔值和无意义数量。
        raise ValueError("top_k 必须是1到5的整数")  # 上层应修正参数后再调用。
    rows = build_index() if index is None else index  # 传入空索引时不能偷偷重建成正常索引。
    terms = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", query.lower()))  # 区分连续中文与精确标识。
    ranked = []  # 收集当前版本内有实际命中的候选。
    for row in rows:  # 每次只读，不修改索引。
        if row["version"] != version.strip():  # 在评分之前过滤版本。
            continue  # 相同E102的旧版本不会混入当前结果。
        score = sum(term in row["tokens"] if re.fullmatch(r"[a-z0-9_]+", term) else term in row["search_text"] for term in terms)  # 英文标识精确匹配，中文暂用子串。
        if score:  # 零匹配不能靠扩大Top-K制造证据。
            hit = {key: row[key] for key in ("id", "version", "error_code", "text", "source")}  # 返回可回查证据。
            hit["score"] = score  # 保留当前算法分数用于定位，不叫置信度。
            ranked.append(hit)  # 结果与内部索引分离。
    return sorted(ranked, key=lambda row: (-row["score"], row["id"]))[:top_k]  # 同分按ID稳定排序。

def answer(query, version, index=None):  # 用抽取原文验证检索到输出的完整链路。
    sources = retrieve(query, version, index=index)  # 不再查询另一套静态资料。
    if not sources:  # 检索成功但没有适用资料。
        return {"status": "insufficient_evidence", "answer": "当前资料未找到适用依据。", "sources": []}  # 显式保留无证据状态。
    text = "\n".join(f"{row['text']} [来源 {row['id']}]" for row in sources)  # 仅抽取实际命中原文。
    return {"status": "ok", "answer": text, "sources": sources}  # 生成式模型后续可接在同一证据接口之后。

if __name__ == "__main__":  # 运行默认示例时不访问模型或网络。
    index = build_index()  # 先完成一次离线入库。
    print("索引证据", [row["id"] for row in index])  # 确认实际读取了三份资料。
    for query, version in [("E102", "v2"), ("E102", "v1"), ("E102", "v9")]:  # 比较条件变化。
        result = answer(query, version, index=index)  # 在线查询复用刚构建的索引。
        print(json.dumps({"query": query, "version": version, "status": result["status"], "ids": [row["id"] for row in result["sources"]], "answer": result["answer"]}, ensure_ascii=False))  # 保留便于核对的输出。
```

## 代码解析：我保留的五个实现决定

第一段数据配置同时保留正文与适用条件。我没有把版本藏在一句自然语言中，而是让它成为检索入口的显式参数。这样 E102 在两个版本下对应不同资料，是由执行逻辑确定的。来源在这里是演示资料的逻辑标识，临时文件结束后不会继续存在，不能把它误解成已经部署的文件下载地址。

`build_index` 的文件读取不是装饰步骤。后续片段的 `text` 来自 `read_text`，词项与可查文本又来自这个片段，最后查询直接消费返回的索引。如果入库和查询各维护一套内容，演示虽然能跑通，却无法说明真实的读取结果是否参与回答；我因此把同一份数据对象一直传到检索环节。

规范化只合并横向空白并统一文本表示，保留数字、下划线和换行边界。字段名与错误码在这个场景中有业务含义，清洗得更“干净”反而可能删掉检索线索。当前三份短文各只有一个段落，所以每份形成一个完整片段。长资料、表格和跨段条件会改变切片策略，不能从这个小样例直接推出通用参数。

检索时我先检查问题、版本和数量，再按版本缩小候选。英文标识保留精确词项，中文暂用连续片段的子串匹配。这个分数只是当前规则的命中计数，不能解释成答案概率。它便于排错，但自然语言改写和近义表达仍容易遗漏，因此我把它作为后续检索实验的基线。

`index is None` 也有实际意义。调用者没有提供索引时，函数才自行构建；显式传入空列表则代表当前索引确实为空。若简单写成“空值就重建”，一次入库失败可能被正常的演示资料悄悄覆盖，后续排查会失去最重要的现场。

## 实际运行：相同错误码，不同版本

在脚本所在目录执行：

```powershell
python project_walkthrough.py # 构建一次索引，再运行三个版本条件。
```

本次 Python 3.12.14 的实际输出如下：

```text
索引证据 ['csv-v1', 'csv-v2', 'encoding-v2']
{"query": "E102", "version": "v2", "status": "ok", "ids": ["csv-v2"], "answer": "CSV 导入缺少 customer_id 列，检查首行表头。 [来源 csv-v2]"}
{"query": "E102", "version": "v1", "status": "ok", "ids": ["csv-v1"], "answer": "CSV 导入缺少 user_id 列，检查首行表头。 [来源 csv-v1]"}
{"query": "E102", "version": "v9", "status": "insufficient_evidence", "ids": [], "answer": "当前资料未找到适用依据。"}
```

索引里先出现三条证据，v2 的查询随后只返回 `csv-v2`，旧版本则返回 `csv-v1`。未知 v9 没有被偷偷解释成“采用最新版本”，而是结束于 `insufficient_evidence`。这些结果共同验证了输入条件确实传到了取数环节。

当前 `answer` 直接抽取检索原文，它没有调用大模型重新组织建议。我这样做是为了先观察证据装配是否正确：如果原文已经选错，生成阶段写得再顺也没有帮助；如果证据正确，后面再接生成模型，就可以单独检查模型有没有改坏字段、条件或操作步骤。

## 我保留下来的限制与下一步

这条链路目前验证的是小数据、单进程和固定词项规则。它没有持久化索引、账户权限、并发控制、真实模型评测，也没有声称能承载某种线上规模。每一项都可以继续增加，但最好先写清对应输入和预期行为，再比较改动前后的结果。

下一步我会先扩充有代表性的失败输入：同一问题的不同说法、字段跨片段、没有适用版本、正确资料已经命中但没有进入上下文。之后再决定是否引入语义检索、重排和模型摘要。这样原型的价值来自可回查的数据流与验证记录，也给后续能力留下了明确的落点。
