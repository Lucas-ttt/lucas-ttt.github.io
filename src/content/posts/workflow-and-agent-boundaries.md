---
title: "先固定流程，再开放决策：我对 Workflow 和 Agent 的取舍"
description: "把同一排障任务分别放进固定流程与有限调度器，观察状态、澄清、工具选择和停止条件。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-03-20T12:00:00+08:00
featured: false
draft: false
series: "AI Agent 开发实践"
seriesOrder: 6
noteType: "代码实操"
tags: ["agent", "workflow", "执行控制"]

modDatetime: 2026-11-03T13:03:44+00:00
---

我在知识库原型里先跑通的链路很固定：接收问题和版本、执行检索、检查证据、返回结果。这种场景的下一步事先就能写清楚。把它改成让模型反复决定“现在应该做什么”，并不会自动增加可回答范围，反而会引入额外调用和新的失败方式。

后来整理需要分步骤处理的任务时，我才把调度抽出来单独实验。同样是查询 E102，有时版本已经完整，有时需要先补条件；如果再加入状态查询或工单工具，还需要根据前一次结果选择下一步。我的做法是先保留稳定的固定流程，再为确实存在动态分支的任务设计一个受限调度入口，分别观察两种方式的执行边界。

## 目录

## 已经知道下一步时，我使用固定工作流

对版本明确的只读排障查询，流程可以由应用完整确定：先校验版本，调用一次检索，命中后组织原文，没有证据就结束。中间步骤不依赖开放式规划，比较容易记录状态、设置超时和复现失败。因此我的固定流程直接使用已有检索函数，没有为了使用某个框架再绕一层决策。

条件不完整也不一定需要 Agent。版本为空时，固定规则就能返回 `needs_input`，提示补充版本，再等待下一次请求。这样的澄清是一个明确的业务状态，而不是模型必须创造的行为。将它留在确定性路径里，可以避免猜测版本后查询旧资料，也减少了一次没有必要的生成调用。

我把工作流理解为“执行顺序和分支主要由应用预先规定”。它仍然可以包含模型，例如生成摘要或抽取字段；是否使用模型，与谁控制下一步不是同一件事。一个顺序固定的检索加生成链路，可以保持简单，重点放在证据和输出质量上。

## 任务要根据中间结果改变路径时，再增加动态调度

动态任务的困难在于，工具返回以后才能知道下一步。先查排障资料，发现缺少版本就澄清；发现还需要运行状态，再查询另一个受授权工具；信息已经够用则停止。这种场景需要维护状态，并让策略在允许的动作范围里选择下一步，而不是只把一条预先写好的流水线包装成“自主规划”。

我目前用固定计划回放来测试这个入口。计划里的每一项模拟一次策略输出，可以是工具请求、澄清或完成。工具会真实执行，但计划本身不是模型生成的，所以本次结果只验证应用怎样接收与执行这些决策。接入真实模型后，还需要单独评估它是否选对工具、参数是否完整、会不会过早结束，这些不能从回放成功推导出来。

## 我先定义状态，再限制能够执行的动作

执行层只认识应用注册表里的 `lookup_support`，不会根据文本去寻找同名系统命令。请求还必须携带明确的 `query` 和 `version` 两个字段。工具继续校验参数值，返回资料或正常空结果；调度层负责记录每次调用来自第几步、使用什么工具、实际返回哪些证据 ID。

我把“完成”和“用完计划”分成不同状态。策略明确提交完成动作时，调度停止；计划只有一次查询、没有完成动作时，返回 `incomplete`。这样工具已经返回一份资料，并不会被执行层擅自解释成整个任务一定结束。应用仍需决定任务成功的业务条件，不能把状态机接受一个结束动作当成答案正确性证明。

## 完整代码：两条路径共享同一个只读工具

将[已有知识工具](/examples/agent-lab/knowledge_tool.py)与下面的 `workflow_agent.py` 放在同一目录，也可[下载调度脚本](/examples/agent-lab/workflow_agent.py)。代码只使用 Python 3.12 标准库与本站配套模块，不调用真实模型。

```python
from knowledge_tool import search_knowledge  # 复用已有版本过滤和参数校验，工具实际执行。

TOOLS = {"lookup_support": search_knowledge}  # 注册允许执行的工具，不动态执行请求文本。

def fixed_workflow(question, version):  # 下一步已知的知识检索使用固定流程。
    if not version:  # 条件不完整时先暂停，不猜测当前版本。
        return {"status": "needs_input", "message": "请补充产品版本", "calls": 0}  # 澄清是明确状态，不必调用模型。
    hits = TOOLS["lookup_support"](question, version)  # 校验成功后执行一次真实检索。
    if not hits:  # 正常空结果不冒充工具错误。
        return {"status": "no_evidence", "message": "没有适用资料", "calls": 1}  # 当前流程结束，不无限换词重试。
    return {"status": "ok", "message": hits[0]["text"], "calls": 1}  # 使用检索原文作为离线输出。

def run_dispatcher(plan, max_calls=2, max_steps=4):  # 用固定计划回放检验动态调度的执行边界。
    if type(max_calls) is not int or max_calls < 1 or type(max_steps) is not int or max_steps < 1:  # 预算必须为正整数。
        raise ValueError("调用预算和步数预算必须为正整数")  # 禁止布尔值与无意义配置。
    history, calls = [], 0  # 分别记录执行历史和真正发出的调用次数。
    for step, action in enumerate(plan, 1):  # 计划是策略替身输出，不是模型决策能力的证明。
        if step > max_steps:  # 决策步骤与工具次数各有独立预算。
            return {"status": "step_limit", "calls": calls, "steps": max_steps, "history": history}  # 预算耗尽不再执行下一项。
        kind = action.get("kind")  # 明确区分完成、澄清与工具请求。
        if kind == "clarify":  # 策略发现缺少必要条件。
            return {"status": "needs_input", "calls": calls, "steps": step, "history": history}  # 暂停等待用户输入。
        if kind == "finish":  # 只有完成动作才能进入正常结束状态。
            return {"status": "ok", "calls": calls, "steps": step, "history": history}  # 保留此前实际执行结果。
        if kind != "tool":  # 未知动作不能被当成代码执行。
            return {"status": "invalid_action", "calls": calls, "steps": step, "history": history}  # 给调用方明确的结构错误。
        if calls >= max_calls:  # 在真正执行前检查收费或外部工具预算。
            return {"status": "call_limit", "calls": calls, "steps": step, "history": history}  # 不多执行一次后再补记超限。
        name, arguments = action.get("name"), action.get("arguments", {})  # 读取结构化工具请求。
        if name not in TOOLS:  # 请求必须匹配应用注册表。
            return {"status": "unknown_tool", "calls": calls, "steps": step, "history": history}  # 不临时寻找同名函数。
        if not isinstance(arguments, dict) or set(arguments) != {"query", "version"}:  # 这里只允许这两个明确字段。
            return {"status": "invalid_arguments", "calls": calls, "steps": step, "history": history}  # 参数结构错误不进入检索。
        calls += 1  # 尝试进入工具的请求计入调用次数，失败也不退还预算。
        try:  # 业务工具继续检查非空字符串与适用版本。
            hits = TOOLS[name](**arguments)  # 真正执行已注册的只读工具。
        except ValueError as error:  # 本例只映射工具声明的参数错误。
            return {"status": "invalid_arguments", "calls": calls, "steps": step, "history": history, "error": str(error)}  # 不把参数错误算作无命中。
        history.append({"step": step, "tool": name, "ids": [item["id"] for item in hits]})  # 保存可检查的请求与返回对应关系。
    return {"status": "incomplete", "calls": calls, "steps": min(len(plan), max_steps), "history": history}  # 计划用完但未finish，不伪装成完成。

if __name__ == "__main__":  # 直接运行固定工作流与三种调度计划。
    print("固定查询", fixed_workflow("E102", "v2"))  # 下一步明确时一次工具调用即可结束。
    print("缺版本", fixed_workflow("E102", ""))  # 简单条件缺失也能由固定规则处理。
    lookup = {"kind": "tool", "name": "lookup_support", "arguments": {"query": "E102", "version": "v2"}}  # 合法的工具请求。
    finish = {"kind": "finish"}  # 显式完成动作。
    print("有界调度", run_dispatcher([lookup, finish]))  # 真实查询后根据完成动作结束。
    print("重复调用", run_dispatcher([lookup, lookup, lookup, finish]))  # 第三次调用在执行前被拦截。
    print("未注册工具", run_dispatcher([{"kind": "tool", "name": "delete_all", "arguments": {}}]))  # 不执行未知能力。
    print("计划未完成", run_dispatcher([lookup]))  # 一次查询不自动等于整个任务完成。
```

```powershell
python workflow_agent.py # 对照固定流程、有限调度、重复请求和未完成状态。
```

## 代码逐段解析：预算要在执行之前检查

`fixed_workflow` 的状态转移很短。缺版本时不调用工具，有版本则真实检索，最后根据证据是否为空决定结果。它将确定性的参数与分支留给应用，便于在一个输入上反复核对同样的行为。

`run_dispatcher` 接收一份动作列表，并分别限制决策步骤和工具调用次数。两者的分母不同：澄清或完成会消耗一个决策步骤，但没有执行工具；有效工具请求进入调用时计数，即使工具随后发现参数值不合法，也不退还这次预算。未知名称和错误参数结构在进入工具前被拒绝，因此输出里的调用次数为零。

我把调用上限放在真正执行之前检查。重复计划的第三个请求到来时，已经执行了两次，程序直接返回 `call_limit`，不会先做第三次再补记超限。步数预算则防止策略通过大量非工具决策拖长流程。接入外部服务后还需要总时间、单次超时与费用预算；当前示例没有把这些不同限制混成一个“最大循环次数”。

## 实际输出揭示了几种结束方式

```text
固定查询 {'status': 'ok', 'message': 'CSV 导入缺少 customer_id 列，检查首行表头。', 'calls': 1}
缺版本 {'status': 'needs_input', 'message': '请补充产品版本', 'calls': 0}
有界调度 {'status': 'ok', 'calls': 1, 'steps': 2, 'history': [{'step': 1, 'tool': 'lookup_support', 'ids': ['csv-v2']}]}
重复调用 {'status': 'call_limit', 'calls': 2, 'steps': 3, 'history': [{'step': 1, 'tool': 'lookup_support', 'ids': ['csv-v2']}, {'step': 2, 'tool': 'lookup_support', 'ids': ['csv-v2']}]}
未注册工具 {'status': 'unknown_tool', 'calls': 0, 'steps': 1, 'history': []}
计划未完成 {'status': 'incomplete', 'calls': 1, 'steps': 1, 'history': [{'step': 1, 'tool': 'lookup_support', 'ids': ['csv-v2']}]}
```

版本完整的固定查询只调用一次工具；缺版本的固定查询直接要求补充输入，调用次数为零。有界调度用一次工具请求加一个完成动作结束，历史里保留 `csv-v2`。这些输出让我能分别检查“下一步由谁给出”和“工具是否真实执行”，避免把两件事混为一谈。

重复请求在第三个决策步骤被调用预算拦住，历史只留下两次真实执行。未注册工具在第一步被拒绝，没有产生调用；只有查询却没有完成动作的计划返回未完成。这些分支比一个只展示成功回答的演示更接近调度层需要处理的实际情况，也为以后接入模型保留了固定回归输入。

## 我的取舍是先增加决策空间，再评估它是否值得

动态调度能够应对不能预先完全写定的路径，但它会增加决策请求、状态处理和失败分析的工作。工具越多，也越需要清楚的参数契约和访问范围。我不会因为有多个业务接口就立即拆成多个 Agent；当任务顺序明确时，一个固定工作流往往更容易维护。

后续扩展时，我会先明确哪些分支真正需要策略判断，哪些条件可以直接由代码处理，再比较两种路径在同一组任务上的成功状态、调用次数和用户等待。对需要写入的操作，还要增加独立的确认、幂等和状态核查。当前演示保持只读，这让我能够先把调度责任与停止条件观察清楚，再逐步扩大执行能力。
