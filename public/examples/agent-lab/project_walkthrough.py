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
