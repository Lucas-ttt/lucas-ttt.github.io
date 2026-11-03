---
title: "如果重做知识库，我会先统一请求、证据与执行契约"
description: "从当前原型的连接边界出发，实践缓存隔离与证据条件校验，整理已知限制和下一轮改造顺序。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-01-05T12:00:00+08:00
featured: false
draft: false
tags: ["rag", "重构", "工程设计"]
series: "AI Agent 开发实践"
seriesOrder: 10
noteType: "代码实操"
modDatetime: 2026-11-03T13:03:45+00:00
---

把读取资料、检索、工具执行和评测分别跑通之后，我开始回看这些脚本之间的连接。单个函数能返回正确结果，组合起来仍然可能丢条件：查询使用 v2，缓存却只按问题文本命中；检索拿到当前资料，后面的引用又指向另一次修订；工具正常结束，界面却把无证据和执行失败显示成同一种状态。

如果重新组织这个知识库原型，我会先统一这些连接处的约定，再考虑增加模型或更复杂的调度。当前已经能复现的是离线资料处理、词项检索和一组独立实验，外部模型决策与真实服务规模还需要另外验证。这次我选了一个很小的重构切口：把请求条件和证据结构写成明确的契约，用反例检查它们是否贯穿整个流程。

## 目录

## 我先保留那些已经有解释力的结果

前面的实验给了我几条可以继续使用的基线。v2 的 E102 应返回 `customer_id`，旧版本资料不应混入；没有适用资料时，应保留无证据状态；工具的参数错误应在执行前发现。它们都能由固定输入与实际输出复核，不依赖最后一段文字是否流畅。

重构时我会把这些基线放在入口附近。每替换一个模块，就运行原来的正常、错误版本和空结果样例，再增加新能力对应的失败样例。这样可以知道哪些行为发生了改变，也能避免把“代码拆得更整齐”误当成“回答变得更可靠”。前面的评测记录继续保留语料版本、参数和原始结果，不能为了新接口好看而丢掉失败输入。

## 当前限制首先出现在跨模块条件上

在小实验里，产品版本通常是函数的显式参数，但实际请求还会受到访问范围和语料修订影响。同一句 E102，换用户可见资料、换产品版本或更新知识库，都可能需要不同证据。如果缓存只保存问题字符串，命中率再高，也可能只是稳定地返回过时结果。

我因此把本轮必要条件收敛为 `QueryContext`：可信应用传入的数据范围、明确的产品版本和知识库修订。数据范围在这里仅是一个固定标识，类定义本身没有认证能力。真正接入账户系统时，要由服务端身份决定它，不能接受模型自行声明“我是另一个用户”。

另一方面，我把证据的 ID、版本、修订、正文和回查位置放到同一个对象里。以前只有一段字符串时，后续模块很容易忘记它来自哪里。结构固定之后，每个阶段都可以检查自己是否仍在使用当前请求允许的证据。这个选择增加了字段维护成本，但也让条件丢失能够被程序发现。

## 用一段小代码验证重构的方向

下面的脚本只依赖 Python 3.12 标准库，不访问网络和已有数据库。可以保存为 `redesign_contracts.py`，也可以[下载完整脚本](/examples/agent-lab/redesign_contracts.py)。这里的范围、修订和资料都是自编测试输入。

```python
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
```

## 代码逐段解析

两个不可变数据类负责表达状态。`frozen=True` 可以阻止普通属性重新赋值，减少同一个对象在后续步骤中被悄悄改写的机会；它不负责核对字段内容，所以我仍在 `validate_context` 中检查空值和运行时类型。明确“当前版本”比从整段历史对话里反复猜测更容易调试。

`cache_key` 把问题、范围、版本和修订一起序列化，再生成哈希。这里固定字段顺序和 UTF-8 编码，是为了让相同条件得到一致的标识。哈希提供的是定位方式，不会加密内容，也不会自动实现授权。真实系统如果还有地区、角色、模型配置或提示模板等影响结果的条件，缓存策略还需要分别评估，不能机械照搬这四个字段。

`validate_evidence` 放在生成或展示之前，逐条核对重复 ID、正文与位置是否存在、版本和修订是否一致。我让正常证据与故意错误的证据经过同一个函数，避免出现“常规路径检查了，重试路径却绕过去”的情况。返回的 `ready` 与 `insufficient_evidence` 也是不同状态，方便上层决定继续处理还是说明资料不足。

这段代码没有读取账户权限，也没有理解答案含义。最后一条故意错误的建议仍能被打印，正好保留了结构契约的能力边界：需要检查的信息没有进入函数，就不能期待函数替我完成那项判断。后续增加断言核查时，我会让答案、当前证据和判断依据共同进入评测，而不只是给函数换一个更强的名字。

## 实际输出与四个可复查的条件

```powershell
python redesign_contracts.py # 验证缓存隔离、证据条件与空结果状态。
```

本次运行得到：

```text
独立缓存键 4
正确证据 ['csv-v2']
旧版本 证据版本不匹配
旧语料 证据语料修订不匹配
无证据 insufficient_evidence
结构合法仍需语义核查 请添加 user_id 列
```

第一行来自同一个问题的四组条件：当前请求、另一产品版本、另一修订和另一访问范围。四个不同键只能证明这些字段确实参与了本例的缓存标识，还不能证明完整权限链路已经实现。第二行是正常证据；接着两行分别注入旧版本和旧语料，拒绝原因能够直接回到被破坏的约束。

第五行没有抛出系统异常，因为合法查询的空结果是正常业务状态。最后一行则保留反例：证据正文要求 `customer_id`，随后的建议却写成 `user_id`。检查器没有接收这段建议，因此结构通过与语义正确必须继续分开观察。

## 我会按风险而不是按框架安排重做顺序

第一步是统一请求、证据和错误状态，把条件从接口一直带到缓存、检索和展示。第二步补齐阶段轨迹，能够回查解析文本、切片位置、过滤条件、候选变化和最终输入。第三步固定开发集与留出集，再比较切片、召回、重排和预算的收益。只有这些观察方式稳定后，我才会逐步替换模型、检索服务或调度框架。

结构化文档仍是当前原型的限制。表格、扫描件和跨章节条件不能靠增加几个元数据字段就处理好，需要单独验证解析与切片。手工特征和规则重排能够解释流程，但不能代表真实 Embedding 或重排模型的效果；模拟网络延迟也不能代替真实服务压测。这些能力在重做清单中保留明确的验证任务，不混进已经跑通的结果里。

我还会把“能否复现一次失败”当作交付材料的一部分。新同伴应该能够用同一个输入看到错误，理解为什么改变过滤或缓存条件后结果不同，再查看尚未覆盖的情况。对这个阶段的个人项目来说，把当前实现的依据和边界讲清楚，比过早堆上更多组件更有助于下一次改进。
