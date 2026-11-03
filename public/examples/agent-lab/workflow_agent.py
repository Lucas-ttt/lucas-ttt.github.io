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
