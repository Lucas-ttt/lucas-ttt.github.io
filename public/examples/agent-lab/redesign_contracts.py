from dataclasses import dataclass, replace  # 用不可变对象表达一次请求的条件。
from hashlib import sha256  # 对完整的缓存条件生成稳定标识。
import json  # 使用确定的字段顺序序列化条件。

@dataclass(frozen=True)  # 防止后续步骤悄悄改写本次请求的条件。
class QueryContext:  # 身份范围由可信应用传入，此类本身不实现认证。
    scope: str  # 记录已经授权的数据范围。
    product_version: str  # 区分同错误码的不同产品版本。
    corpus_revision: str  # 将答案绑定到明确的知识库修订。

@dataclass(frozen=True)  # 本例证据的文本与适用条件一同保存。
class Evidence:  # 结构化证据用于跨阶段校验。
    id: str  # 唯一证据标识。
    version: str  # 证据适用的产品版本。
    revision: str  # 证据来自哪个语料修订。
    text: str  # 保留实际用于回答的原文。
    source: str  # 保留可回查的位置。

def validate_context(context):  # 检查执行前必须明确的三个条件。
    values = (context.scope, context.product_version, context.corpus_revision)  # 条件缺失不能依靠缓存补齐。
    if any(not isinstance(value, str) or not value.strip() for value in values):  # 类型声明不会自动验证运行时输入。
        raise ValueError("查询范围、产品版本和语料修订必须明确")  # 返回可解释的条件错误。

def cache_key(query, context):  # 为同一查询的不同适用范围生成不同键。
    validate_context(context)  # 缓存读取前也执行条件检查。
    if not isinstance(query, str) or not query.strip():  # 不接受空问题。
        raise ValueError("query 必须为非空字符串")  # 让调用方补齐输入。
    payload = {"query": query.strip(), "scope": context.scope, "version": context.product_version, "revision": context.corpus_revision}  # 纳入所有本例影响结果的条件。
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")  # 显式固定序列化方式。
    return sha256(encoded).hexdigest()  # 哈希用于标识，不提供权限或内容加密。

def validate_evidence(rows, context):  # 在展示或生成前再次核对证据条件。
    validate_context(context)  # 同样拒绝不完整请求。
    seen = set()  # 防止重复证据占据多个位置。
    for row in rows:  # 逐条检查当前返回的证据。
        if row.id in seen:  # 同一证据在多路召回中只保留一次。
            raise ValueError("证据标识重复")  # 此处选择明确报错来暴露组装缺陷。
        if not row.id or not row.text.strip() or not row.source:  # 引用必须有内容和回查入口。
            raise ValueError("证据结构不完整")  # 不用一个空标识冒充来源。
        if row.version != context.product_version:  # 不让旧版本混进当前回答。
            raise ValueError("证据版本不匹配")  # 条件错误不靠改写答案来掩盖。
        if row.revision != context.corpus_revision:  # 旧语料修订也不能复用。
            raise ValueError("证据语料修订不匹配")  # 提示重新检索或刷新缓存。
        seen.add(row.id)  # 校验通过后记录当前标识。
    return "ready" if rows else "insufficient_evidence"  # 空证据有独立业务状态。

def main():  # 用固定输入复现一次重构应保护的条件。
    current = QueryContext("tenant-A/support", "v2", "r1")  # 本地固定范围，不代表已验证登录身份。
    variants = [current, replace(current, product_version="v1"), replace(current, corpus_revision="r2"), replace(current, scope="tenant-B/support")]  # 分别改变版本、修订和访问范围。
    keys = {cache_key("E102", context) for context in variants}  # 相同问题也必须产生四个不同键。
    assert len(keys) == 4  # 若漏掉任一条件，回归应直接失败。
    print("独立缓存键", len(keys))  # 观察隔离条件是否实际进入键。
    evidence = Evidence("csv-v2", "v2", "r1", "CSV 缺少 customer_id 列。", "demo/csv-v2.md")  # 自编资料限定本次版本。
    assert validate_evidence([evidence], current) == "ready"  # 正常证据可以继续使用。
    print("正确证据", [evidence.id])  # 保留可核对的标识。
    for label, bad in [("旧版本", replace(evidence, version="v1")), ("旧语料", replace(evidence, revision="r0"))]:  # 分别注入两种不适用证据。
        try:  # 预期每个错误条件都被拒绝。
            validate_evidence([bad], current)  # 走与正常结果相同的检查入口。
        except ValueError as error:  # 显示实际错误类型对应的原因。
            print(label, str(error))  # 不把条件冲突显示为没有资料。
        else:  # 错误证据通过就说明约束被破坏。
            raise AssertionError("不适用证据未被拒绝")  # 让验证命令以失败结束。
    print("无证据", validate_evidence([], current))  # 正常空结果独立于异常。
    wrong_claim = "请添加 user_id 列"  # 故意给出与 v2 原文不符的建议。
    print("结构合法仍需语义核查", wrong_claim)  # 结构验证没有接收断言，不能证明建议正确。

if __name__ == "__main__":  # 导入契约函数不会执行实验。
    main()  # 本脚本不访问网络或用户已有数据库。
