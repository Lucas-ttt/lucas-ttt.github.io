---
title: "Agent 调用超时或遇到 429，怎样重试与降级？"
description: "结合异步故障注入，逐段解释重试分类、单次超时、总预算和原文降级，说明真实接口接入时还要验证什么。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-01-13T12:00:00+08:00
featured: false
draft: false
tags:
  - 可靠性
  - 重试
  - rag
series: "AI Agent 面试十问"
seriesOrder: 9
noteType: 代码实操
---

知识库已经检索到 v2 手册，生成回答却超时了。把所有错误都重试三次，会让错误参数也重复执行；一超时就返回“没有资料”，又会混淆模型故障与知识缺失。下面用四个可重复的故障实验，把这些分支写成能观察的代码。

`fake_model` 是故障替身，不是实际 LLM。它通过一次连接异常、异步慢响应和参数错误触发控制逻辑；本篇记录本地故障注入，不将它写成线上事故或真实模型性能结果。

## 目录

## 面试题：模型超时或者返回 429 时，怎样重试和降级？

回答的重点不是背出“指数退避”，而是说明哪些错误值得再次请求、还可以等多久、再次请求会不会产生重复副作用，以及用户最终看到什么。对于知识库应用，检索失败、没有检索到证据和生成服务不可用，是三个不同状态，不能统一显示为“知识库没有答案”。

### 一分钟回答

我会先把调用分成参数和权限错误、临时网络故障、服务限流以及整体预算耗尽。参数不合法和认证失败应立即停止；临时故障可以在有限次数与剩余时间内重试；限流还需要参考服务端给出的等待信息，并降低并发，而不是立刻把流量放大。每次调用有独立超时，整个任务另有总预算，退避也计入预算。已拿到可展示的可靠原文、只有生成失败时，可以明确标注“暂未生成总结”并展示来源；没有资料不能编造一个降级答案。本文用可取消的异步故障替身验证四个分支，不把它当成真实模型性能测试；真实 SDK 的异常分类和取消行为还要单独确认。

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

## 代码逐段解析：怎样避免越重试越慢

### 第一步：用替身固定每一种失败条件

`fake_model` 的四种行为是人为指定的：参数错误总是抛异常，临时连接错误只在第一次触发，慢响应每次都等待五十毫秒，其余路径返回固定文本。这样可以控制输入条件，检查分支是否符合设计。如果直接用真实服务偶发的一次失败做验证，就很难知道下一次成功究竟来自代码修复，还是网络自己恢复。固定替身用于验证控制逻辑，不用于衡量答案质量、线上故障率或模型平均耗时。

### 第二步：把两种时间边界分开

外层 `asyncio.timeout(total_budget)` 约束整个异步区域，内层 `wait_for` 约束一次 `fake_model` 等待。内层超时在当前尝试的异常分支处理；外层先耗尽时，则跳到总预算分支，将原因记成 `total_timeout`。这使日志能够区分“每次都很慢”和“尚有次数但任务已没时间”。相关取消语义以 [Python asyncio 官方超时文档](https://docs.python.org/3.12/library/asyncio-task.html#timeouts) 为准；它并不承诺任何远端请求都能立刻停止。

`attempts` 在发起调用前更新，所以计数包含失败的那次请求。第一次调用失败、第二次成功，输出为二；它不是“重试了两次”。这个口径在指标看板和面试回答里都要明确，否则很容易把一个两次尝试的策略描述成三次请求，随后又用错误的分母解释成功率。

### 第三步：只给被允许的错误第二次机会

内部只捕获连接异常与超时进行重试，参数异常直接返回。这里有意没有写一个捕获所有异常后继续循环的分支，因为程序错误、无效输入和服务临时失败应该进入不同处理路径。示例的短暂固定等待便于快速演示，不等于实现了指数退避或随机抖动。若后续增加这些策略，应同时保存每次等待值与剩余预算，才能解释为何某次请求没有继续尝试。

### 第四步：将降级结果设计成独立状态

失败后函数把 `answer` 留空，并用 `source_only` 告诉上层只能展示来源。界面可以显示“总结服务暂不可用，以下为已检索到的 v2 原文”，再列出来源与适用条件，而不是把原文包装成已经生成的结论。当来源为空时返回 `unavailable`，提示当前服务没有可展示结果。本文参数错误分支还清空了来源，避免无效请求继续沿用某次输入资料；真实接口可根据错误类型设计更细的反馈。

## 429 如何处理：区分已实现逻辑与接入策略

当前脚本没有 HTTP 请求，也没有制造真实的 429 响应，因此不能说它已经测试了限流恢复。[RFC 6585 对 429 的定义](https://www.rfc-editor.org/rfc/rfc6585#section-4) 说明它表示请求过多，响应可以带 `Retry-After`。接入服务时，应读取 SDK 暴露的状态码和响应头，按照服务商约定决定等待；如果要求等待的时间已经超过剩余总预算，就直接结束本次请求，给用户稍后再试的反馈。不能为了遵守一个等待值无限延长任务。

批量请求同时收到限流时，全部立即重试可能制造新的峰值。可按业务优先级降低并发，并让等待时间适当错开；如果持续失败，还需要限制继续进入下游的请求。这些属于接入后的策略，当前示例只展示固定退避与有限尝试。[AWS 的重试与退避官方说明](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html) 同样强调临时故障、重试开销与幂等约束；这里没有使用它的云服务或复制其示例代码。

## 再做两个小实验

把 `MAX_ATTEMPTS` 改成一，观察 flaky 不再有第二次成功机会。随后恢复为二，把最后一组的整体预算从三毫秒改为二百毫秒，检查它是否从 `total_timeout` 变成两次单独超时后的降级。

这个演示中的协程会在 `await asyncio.sleep` 处响应取消。真实网络调用、本地线程或远端工具是否停止，必须另外核查；本地超时不能证明远端操作没有执行。查询和退款写入也不能共用同一套盲目重试规则，写操作需要先确认状态并考虑幂等。

## 面试追问：怎么选配置，怎么证明改动有效？

**十毫秒超时能直接用到线上吗？** 不能。这里只是让故障实验快速结束。真实阈值应结合请求类型、分阶段耗时记录、可接受等待时间与成功率确定；检索、模型首个响应和完整生成也可能需要不同观察方式。先给出测量环境与样本口径，再讨论配置取舍，不能用演示数字充当性能结论。

**如果已经退费成功，但客户端超时了怎么办？** 超时只表明本地没有按时拿到结果，不代表服务端没有执行。写操作重试前应查询操作状态，并使用业务幂等标识约束重复执行；不能看到 TimeoutError 就再发一次扣款或退款。本文的工具没有写入型副作用，因此这类保障尚未实现。

**没有检索结果时能展示旧缓存吗？** 要先确认缓存的权限范围、版本和有效期；过期或其他用户的证据不能因为服务故障就重新变得可用。当前脚本只接收本次传入的演示来源，没有缓存读取逻辑，不应把 `source_only` 解释成自动回退到任意历史资料。

**怎样验收一次修改？** 固定四个场景，逐项对比状态、尝试次数、失败原因和来源是否保留。再增加空来源输入，确认失败时变成 `unavailable`。如果接入真实服务，还要记录每阶段耗时、取消后的资源状态与限流分支。先证明状态机按约定结束，再讨论用户体验是否改善。

## 资料入口

- [Python 3.12：asyncio 超时与等待](https://docs.python.org/3.12/library/asyncio-task.html#timeouts)：外层超时上下文与取消行为。
- [Python 3.12：wait_for](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.wait_for)：单次等待、取消和超时的官方说明。

## 中文实战阅读

[阿瑞说项目管理：Agent可靠性工程，博客园](https://www.cnblogs.com/itarui/p/20404026)可作为失败控制的中文阅读入口。本文用独立故障替身执行四条分支，运行结果以本页脚本为准。
