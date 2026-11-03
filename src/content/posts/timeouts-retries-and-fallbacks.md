---
title: 给 Agent 调用加超时：有限重试、总预算与原文降级
description: 用四种可重复故障注入，运行并观察连接恢复、重试耗尽、参数错误和整体预算终止；附完整 Python 代码与输出。
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-01-13T12:00:00+08:00
featured: false
draft: false
tags:
  - 可靠性
  - 重试
  - rag
series: AI Agent 代码实操
seriesOrder: 9
noteType: 代码实操
---

知识库已经检索到 v2 手册，生成回答却超时了。把所有错误都重试三次，会让错误参数也重复执行；一超时就返回“没有资料”，又会混淆模型故障与知识缺失。下面用四个可重复的故障实验，把这些分支写成能观察的代码。

`fake_model` 是故障替身，不是实际 LLM。它通过一次连接异常、异步慢响应和参数错误触发控制逻辑；本篇记录本地故障注入，不将它写成线上事故或真实模型性能结果。

## 目录

## 四种情况分别怎样结束

| 场景 | 注入方式 | 应看到的结果 |
| --- | --- | --- |
| flaky | 第一次连接失败，第二次成功 | 尝试两次后返回答案 |
| timeout | 每次响应都慢于单次等待上限 | 用尽两次尝试后只展示原文 |
| invalid | 请求参数不合法 | 第一次就结束，不重试 |
| deadline | 整体预算先耗尽 | 即使还有次数，也停止等待 |

`MAX_ATTEMPTS = 2` 表示总尝试次数，包含第一次调用。单次十毫秒、整体三毫秒等数值仅用于快速触发演示分支，不是生产超时配置建议。接入真实服务后，阈值要根据可接受等待时间与实际响应记录调整。

## 运行环境与完整代码

环境：Python 3.12，Windows PowerShell 或 WSL/Linux 终端。无需 API Key，无第三方依赖，不连接外网；原文由脚本中的演示数据传入。

```bash
python --version  # 确认使用 Python 3.12。
python retry_fallback.py  # 运行四种故障注入并打印分支状态。
```

[下载完整的 retry_fallback.py](/examples/agent-lab/retry_fallback.py)

```python
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
```

## 本地运行输出

以下输出已在 Python 3.12.14 核对，重点看状态、尝试次数和原因：

```text
flaky {"status": "ok", "attempts": 2, "answer": "v2 请核对 customer_id 列", "sources": ["manual_v2.md#E102：必填列为 customer_id"], "reason": ""}
timeout {"status": "source_only", "attempts": 2, "answer": "", "sources": ["manual_v2.md#E102：必填列为 customer_id"], "reason": "TimeoutError"}
invalid {"status": "invalid", "attempts": 1, "answer": "", "sources": [], "reason": "ValueError"}
deadline {"status": "source_only", "attempts": 1, "answer": "", "sources": ["manual_v2.md#E102：必填列为 customer_id"], "reason": "total_timeout"}
```

第一行说明临时连接错误得到了一次重试。第二行没有生成回答，却仍保留已经检索到的原文。第三行在参数错误后立即结束。第四行由外层总预算终止，区别于两次单独超时后耗尽次数。

## 总预算与单次超时放在哪里

外层 `asyncio.timeout` 包住调用和退避等待，内层 `wait_for` 只限制一次生成。两次调用之间的等待同样消耗整体预算，不能因为进入重试就重新赠送一整段等待时间。

示例只允许 `ConnectionError` 和 `TimeoutError` 重试，`ValueError` 立即返回。接入 SDK 时，应按其具体异常定义补充认证失败、限流和网络错误分类，不能照搬本地异常名就认为覆盖了全部情况。

原文降级也有前提：`sources` 必须来自已经完成的检索。函数收到空列表时会返回 `unavailable`，不会编造来源。若调用者确认检索成功但本来没有资料，应在生成前走“证据不足”的业务分支，而不是故意调用模型等它失败。

## 再做两个小实验

把 `MAX_ATTEMPTS` 改成一，观察 flaky 不再有第二次成功机会。随后恢复为二，把最后一组的整体预算从三毫秒改为二百毫秒，检查它是否从 `total_timeout` 变成两次单独超时后的降级。

这个演示中的协程会在 `await asyncio.sleep` 处响应取消。真实网络调用、本地线程或远端工具是否停止，必须另外核查；本地超时不能证明远端操作没有执行。查询和退款写入也不能共用同一套盲目重试规则，写操作需要先确认状态并考虑幂等。

## 资料入口

- [Python 3.12：asyncio 超时与等待](https://docs.python.org/3.12/library/asyncio-task.html#timeouts)：外层超时上下文与取消行为。
- [Python 3.12：wait_for](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.wait_for)：单次等待、取消和超时的官方说明。

## 中文实战阅读

[阿瑞说项目管理：Agent可靠性工程，博客园](https://www.cnblogs.com/itarui/p/20404026)可作为失败控制的中文阅读入口。本文用独立故障替身执行四条分支，运行结果以本页脚本为准。
