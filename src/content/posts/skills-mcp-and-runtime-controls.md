---
title: "MCP 和普通函数调用有什么区别？跑通双端调用"
description: "用真实 MCP stdio 双端连接拆解初始化、工具发现、参数与结构化返回，区分连接异常、工具错误和正常空结果。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-01-05T12:00:00+08:00
featured: false
draft: false
tags:
  - agent
  - mcp
  - skill
series: "AI Agent 面试十问"
seriesOrder: 10
noteType: "代码实操"
---

[张高兴在博客园的LangGraph与MCP文章](https://www.cnblogs.com/zhanggaoxing/p/18889516)给出了服务端、工具加载和调用的文件结构。本篇先把链路收窄：一个客户端启动一个只读知识检索服务，实际发现工具并拿回结果。这里固定官方Python SDK的1.30.0版本，不混用main分支或旧适配器的API。

## 目录

## 面试题：MCP 和普通函数调用有什么区别

面试官问：“你说接了 MCP，它与直接调用一个 Python 函数有什么区别？请说明工具发现、参数校验、结果返回和错误处理。”可以用同一份检索函数的两种调用方式展开：先直接调用，再观察经过 MCP 之后增加了哪些交互步骤。

回答时先把三个角色分开：宿主应用组织模型和用户交互；MCP 客户端管理与工具服务的连接；服务端提供可发现、可调用的工具。本例没有调用模型，客户端直接提交已知参数，因此验证的是协议与执行链路。给它加上模型决策，还需要宿主把工具描述提供给模型，并将模型提交的调用请求转交客户端。

## 一分钟回答

普通函数调用发生在程序已经知道函数位置和参数的情况下；MCP 在客户端与服务端之间约定了能力发现、工具描述和调用结果的交换方式。我的示例保留同一个版本检索函数，在服务端注册成工具；客户端启动本地子进程，先初始化，再发现工具，最后提交 E102 与 v2，收到带来源的 csv-v2 证据。业务检索逻辑没有因为换协议而变化。

我会分别检查连接失败、调用错误和正常空结果。查询未知版本得到空列表，表示这次查询没有可用资料；空问题触发工具错误，应修正参数。MCP 不替代应用的权限控制、对话记忆或调用预算。只有一个进程中的固定函数时，直接调用更省事；多个宿主需要复用同一套工具描述与服务时，统一协议才开始体现价值。

## 文件与运行环境

Python 3.12，mcp==1.30.0。解压[完整示例](/examples/agent-lab.zip)，保留mcp_server.py、mcp_client.py和knowledge_tool.py。无需浏览器插件，也不请求模型；协议客户端会真实启动本地服务子进程。

```powershell
python -m pip install -r requirements.txt # 在已激活虚拟环境中安装固定版本。
python mcp_client.py # 一次完成服务启动、初始化、发现和工具调用。
```

## 服务端：注册同一个检索函数

```python
from mcp.server.fastmcp import FastMCP  # 使用固定在 requirements.txt 中的官方 v1 SDK。
from knowledge_tool import search_knowledge  # 复用同一份只读版本检索逻辑。

server = FastMCP("lucas-knowledge")  # 服务名用于工具发现。

@server.tool()  # 将普通函数注册成可发现的 MCP 工具。
def lookup_support(query: str, version: str) -> list[dict]:  # SDK 会根据签名生成参数描述。
    """按明确的产品版本检索演示排障资料。"""  # 工具说明由客户端取得。
    return search_knowledge(query, version)  # 后端仍负责校验参数与执行读取。

if __name__ == "__main__":  # 客户端会通过子进程启动本文件。
    server.run(transport="stdio")  # 标准输出专用于协议，不能向其中随意 print 日志。
```

stdio把标准输出作为协议通道。调试日志不要随手print到服务端stdout，否则可能破坏消息解析；当前SDK自己的处理日志在stderr，下面结果块只列客户端stdout。

### 服务端代码逐段解析

第一段导入将协议层与业务层分开。`FastMCP` 负责注册与收发，`search_knowledge` 仍负责空参数校验、版本过滤和资料查找。这样，同一条 E102 查询可以先在普通函数测试中验证，再通过 MCP 复测；如果直接调用正确而协议调用失败，排查范围就能缩小到连接、参数序列化或返回值转换。

第二段的装饰器把 `lookup_support` 暴露为工具，函数名、参数类型和说明用于形成可发现的描述。这里的 `query: str` 只能说明参数类型，不能表达“非空白问题”这一完整业务条件，所以函数内部的非空校验仍然必要。工具说明也要告诉调用方版本是必填业务条件，避免模型把 v1 的字段要求用于 v2。

第三段只启动 stdio 服务，没有开放公网端口。服务进程从标准输入接收消息，用标准输出返回协议数据。某次看见“正在处理请求”的日志，并不能据此断言调用失败；应区分日志所在通道与工具结果。开发者自己添加调试信息时，放到标准错误通道，避免把一行提示文字混进协议消息。

## 客户端：发现后再调用

```python
import asyncio  # 使用 SDK 的异步客户端。
import argparse  # 让同一客户端可以验证未知版本与错误参数。
import json  # 显示结构化工具结果。
import sys  # 服务端使用与客户端相同的虚拟环境解释器。
from pathlib import Path  # 通过脚本位置定位服务端，不依赖当前工作目录。
from mcp import ClientSession, StdioServerParameters  # 官方 MCP 客户端会话和进程参数。
from mcp.client.stdio import stdio_client  # 建立实际的标准输入输出协议连接。

async def main(version="v2", bad_input=False):  # 连接、发现与调用使用同一个会话。
    script = Path(__file__).with_name("mcp_server.py")  # 定位同目录的服务端入口。
    parameters = StdioServerParameters(command=sys.executable, args=[str(script)], env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})  # 复用解释器并避免在示例目录生成缓存。
    async with stdio_client(parameters) as (reader, writer):  # 启动服务子进程并打开协议通道。
        async with ClientSession(reader, writer) as session:  # 创建实际 SDK 会话。
            await session.initialize()  # 使用本次固定 SDK 版本完成会话初始化。
            tools = await session.list_tools()  # 真实查询服务端工具清单。
            print("发现工具", [item.name for item in tools.tools])  # 这份清单来自协议返回。
            result = await session.call_tool("lookup_support", {"query": "" if bad_input else "E102", "version": version})  # 发起一次真实协议工具调用。
            print("调用错误", result.isError)  # 失败状态不能伪装成正常证据。
            print("结构化结果", json.dumps(result.structuredContent, ensure_ascii=False))  # 保存当前 SDK 返回的完整结构。

if __name__ == "__main__":  # 直接执行客户端即可完成双端演示。
    parser = argparse.ArgumentParser()  # 命令行参数不改变服务端实现。
    parser.add_argument("--version", default="v2")  # 默认查询新版本资料。
    parser.add_argument("--bad-input", action="store_true")  # 此参数主动注入一个空问题。
    options = parser.parse_args()  # 读取本次验证条件。
    asyncio.run(main(options.version, options.bad_input))  # 上下文结束后 SDK 会回收本次服务子进程。
```

sys.executable保证子进程使用客户端所在虚拟环境，Path(__file__)避免从其他目录启动时找不到服务文件。会话初始化、工具发现和call_tool是实际SDK调用，不是把一个HTTP函数改名为MCP。

### 客户端代码逐段解析

先看进程参数。`sys.executable` 解决“主程序装了依赖，子进程却换了另一个 Python”的环境问题；`Path(__file__)` 解决工作目录变化的问题。这两个设置与检索算法无关，却直接决定别人能否下载代码后复现。生产场景还应限制可启动的服务入口，不能让模型提供任意命令字符串来启动程序。

再看两个嵌套的异步上下文。外层负责子进程与输入输出流，内层管理 SDK 会话。调用必须放在连接有效期间，退出后再使用旧会话不能保证成功。本文的客户端完成一次任务就退出，便于复现；真实应用若复用长连接，需要单独设计断连恢复、资源回收和并发策略，不能直接把示例当成连接池。

然后按顺序读取三个 `await`。`initialize()` 完成双方协议与能力的协商；`list_tools()` 获取服务端实际提供的工具描述；`call_tool()` 才执行此次业务请求。面试时可以打开工具清单，指认工具名称及输入结构，而不只说“配置已经连接成功”。一个服务端正在运行，并不等于目标工具已注册成功。

最后看结果处理。代码分别打印 `isError` 与 `structuredContent`，而不是把整个对象转成字符串后直接给用户看。本次结构化对象中的 `result` 来自固定 SDK 对列表返回值的处理，不能推广成所有 MCP 工具的统一业务字段。接入其他服务时，应先核对其输入输出约定，再决定如何提取证据和显示错误。

## 正常路径的实际输出

```text
发现工具 ['lookup_support']
调用错误 False
结构化结果 {"result": [{"id": "csv-v2", "version": "v2", "error_code": "E102", "text": "CSV 导入缺少 customer_id 列，检查首行表头。", "source": "demo/csv-v2.md"}]}
```

结构化返回的result包含csv-v2、版本和原文。这里输出对象的形状对应本次固定SDK与工具返回类型；调用方应检查实际schema，不能假设所有工具都返回这个字段。

## 两条容易混淆的分支

```powershell
python mcp_client.py --version v9 # 输入结构合法，但演示资料没有v9。
python mcp_client.py --bad-input # 注入空问题，触发检索函数参数校验。
```

未知版本：

```text
发现工具 ['lookup_support']
调用错误 False
结构化结果 {"result": []}
```

空问题：

```text
发现工具 ['lookup_support']
调用错误 True
结构化结果 null
```

前者是正常调用的空结果，后者是工具调用错误。应用需要据此决定澄清版本、补充资料还是反馈参数问题，不能把两者统一显示成“模型没有答案”。

### 把输出翻译成用户能理解的行为

对 v2 的正常命中，可以显示“请检查 customer_id 表头”，同时保留版本、资料标识和来源供后续引用校验。对 v9 的空结果，可以提示“当前资料没有 v9 的排障依据，请确认版本或补充手册”，不要自动查询 v1 来填满回答。对空问题，应提示补充错误码或故障描述，而不是重试完全相同的无效参数。

还有一类失败发生在获得工具结果之前，例如服务脚本路径错误、进程无法启动或初始化失败。这种连接异常与本例 `isError=True` 的工具结果处于不同位置，需要在宿主捕获并记录。排查时依次确认解释器路径、服务端依赖、初始化、工具名称、参数和结果，能够避免把所有错误都交给模型“再想一次”。

## 接入Agent时增加哪一层

MCP解决工具能力与调用结果如何交换，宿主仍要把发现的工具描述交给模型，并校验模型请求、权限和预算。它不会自动保存对话长期记忆，也不会因为工具通过协议注册就自动完成授权。

如将本篇接入第八篇的 LangGraph，需要在连接有效期间调用 MCP 工具，再把返回值对应到原模型工具请求，保留调用标识。真实多用户服务还要区分身份、会话与数据范围，本篇只演练一个本地只读工具。

## 面试追问：协议统一之后还缺什么

**为什么不用一个 HTTP 接口？** 如果只服务一个固定客户端，且团队已有清晰接口规范，直接 HTTP 调用可能已经够用。MCP 的价值在于统一工具能力的描述和交换约定，让宿主有一致的发现与调用入口；它不保证网络更快，也不要求底层业务必须重新实现。本文用 stdio，换成远程连接后需要重新验证认证、传输与部署条件。

**工具发现成功，是否代表用户有权查所有文档？** 不能这样推断。工具清单说明可提供什么能力，实际数据访问仍要结合已验证的身份与授权范围。本例的三份演示资料没有租户和敏感数据，也没有实现账户权限。真实服务应从可信身份上下文得到访问范围，再限制查询，不能信任模型自行填写的用户或租户编号。

**MCP 的会话是不是聊天记忆？** 本例会话管理的是协议连接和请求交互，聊天历史是否持久化、怎样裁剪、能否跨用户共享，由宿主另行实现。可以把本篇的检索返回值交给第七篇的会话模块，但应保存本次问题与证据的关联，不把上一个用户的结果带入下一个用户的回答。

**怎样证明自己跑通了，而不是只写了配置？** 展示工具发现清单、一次正常证据、一次未知版本空结果以及一次错误参数结果，再指出各分支对应的客户端行为。下载包中的验证记录保留了这三次命令的实际标准输出。它们证明本地双端链路可以运行，模型是否选对工具、生成答案是否忠于证据，还要另外设计评测。

## 中文原文与版本依据

- [张高兴：在LangGraph中使用MCP协议，博客园](https://www.cnblogs.com/zhanggaoxing/p/18889516)：中文文件结构与工具加载示例。
- [一枫说码：MCP双端实战，博客园](https://www.cnblogs.com/yifeng-coding/p/19766178)：补充客户端与服务端开发的阅读入口。
- [官方Python SDK v1.x](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)：核对本篇固定版本所属分支；升级SDK后应重新执行三个分支。
- [MCP 官方：工具与错误返回](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)：核对工具描述、结构化返回及工具错误的职责。
- [MCP 官方：连接生命周期](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)与[stdio 传输](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)：核对初始化顺序与标准输出通道约定。
