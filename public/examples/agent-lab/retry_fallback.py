import asyncio  # 使用协程等待和可协作取消的超时机制。
import json  # 输出可核查的状态，而不是只打印自然语言答案。
MAX_ATTEMPTS = 2  # 将总尝试次数集中配置，含第一次调用。

async def fake_model(mode, attempt):  # 用确定性故障替身复现边界，不调用真实模型。
    if mode == "invalid":  # 模拟不可通过重复请求解决的参数错误。
        raise ValueError("缺少 query 参数")  # 本例将参数错误归为不可重试。
    if mode == "flaky" and attempt == 1:  # 只在第一次制造临时连接故障。
        raise ConnectionError("模拟连接中断")  # 后续重试可以成功。
    if mode == "timeout":  # 通过异步等待模拟慢响应。
        await asyncio.sleep(0.05)  # 等待点可以响应取消，不阻塞事件循环。
    return "v2 请核对 customer_id 列"  # 成功分支使用固定演示答案。

async def answer_with_fallback(mode, sources, total_budget=0.2):  # 对一次回答设置整体预算。
    attempts, reason = 0, ""  # 记录实际调用次数和最后失败原因。
    try:  # 外层捕获总预算用尽。
        async with asyncio.timeout(total_budget):  # 预算包含调用与两次调用之间的等待。
            for attempt in range(1, MAX_ATTEMPTS + 1):  # 最多尝试两次，不让模型无限重试。
                attempts = attempt  # 在发起调用前记录这一次尝试。
                try:  # 每次调用都有独立的处理分支。
                    text = await asyncio.wait_for(fake_model(mode, attempt), timeout=0.01)  # 单次等待最多十毫秒。
                    return {"status": "ok", "attempts": attempts, "answer": text, "sources": sources, "reason": ""}  # 成功后立即结束。
                except (ConnectionError, TimeoutError) as error:  # 只重试本例允许的临时错误。
                    reason = type(error).__name__  # 保存失败类型，供外部日志与界面区分。
                    if attempt < MAX_ATTEMPTS:  # 最后一次失败后不再无意义地等待。
                        await asyncio.sleep(0.002)  # 退避等待同样受外层总预算约束。
                except ValueError:  # 参数错误直接返回，不进入重试。
                    return {"status": "invalid", "attempts": attempts, "answer": "", "sources": [], "reason": "ValueError"}  # 不伪造业务答案。
    except TimeoutError:  # 外层总预算先于调用完成时进入这里。
        reason = "total_timeout"  # 与单次超时耗尽重试明确区分。
    status = "source_only" if sources else "unavailable"  # 仅有真实检索结果时才允许原文降级。
    return {"status": status, "attempts": attempts, "answer": "", "sources": sources, "reason": reason}  # 保留原文，声明未完成生成。

async def main():  # 顺序运行四种可重复的故障实验。
    sources = ["manual_v2.md#E102：必填列为 customer_id"]  # 将已检索到的演示原文作为输入。
    cases = [("flaky", "flaky", 0.2), ("timeout", "timeout", 0.2), ("invalid", "invalid", 0.2), ("deadline", "timeout", 0.003)]  # 分别验证恢复、重试耗尽、拒绝重试与总预算。
    for label, mode, budget in cases:  # 每种场景都重新开始计数。
        result = await answer_with_fallback(mode, sources, budget)  # 执行同一个控制入口。
        print(label, json.dumps(result, ensure_ascii=False))  # 输出真实分支和尝试次数。

if __name__ == "__main__":  # 被其他模块导入时不运行演示。
    asyncio.run(main())  # 脚本不访问网络，也不执行数据库写操作。
