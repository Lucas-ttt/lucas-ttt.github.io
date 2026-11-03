---
title: "把检索函数接入 MCP：一次 stdio 双端实践"
description: "保留同一个检索函数，记录 MCP 初始化、工具发现和实际调用，并区分空结果与执行错误。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-01-05T12:00:00+08:00
featured: false
draft: false
tags:
  - agent
  - mcp
  - skill
series: "AI Agent 开发实践"
seriesOrder: 10
noteType: "代码实操"
---

前面几篇里，我一直直接调用 Python 函数查询排障资料。这次我把同一个函数接到 MCP 服务上，想看清一个变化：业务逻辑保持原样，调用方怎样发现工具、提交参数，再拿回结构化结果。

为了让问题足够具体，我只保留一个客户端和一个只读检索服务。客户端启动本地子进程，查询 v2 的 E102，再分别尝试未知版本和空问题。环境固定为 Python 3.12、MCP Python SDK 1.30.0，运行中不请求模型，也不依赖远程数据库。

## 目录

## 从直接调用到工具服务

直接调用函数时，程序已经知道函数的位置、名称和参数。拆成工具服务后，客户端首先需要知道服务提供什么，再按照约定的结构提交请求。我把原来的 `search_knowledge` 留在业务层，在外面增加一个 MCP 注册入口，让这两种方式能够使用相同的检索与校验逻辑。

设计时，我先明确三个角色：宿主应用组织模型和用户交互；客户端管理与工具服务的连接；服务端执行已注册的能力。本次先把中间两部分跑通。只有等工具请求与返回都能独立复现，再加入模型决策，才能分辨失败来自协议交互、业务执行还是模型选择。

## 这次实践的观察重点

我把验收拆成四个可观察的步骤：初始化能完成，工具清单里存在 `lookup_support`，合法参数能够进入检索函数，返回值仍保留版本与资料标识。正常路径提交 E102 与 v2，收到 `csv-v2`；这说明协议层没有丢掉原本的版本条件，也给后续引用校验留下了依据。

另外，我单独检查调用失败与正常空结果。查询未知版本得到空列表，表示当前没有适用资料；空问题触发工具错误，需要修正参数。这样的区分会直接影响上层提示和重试策略。至于权限、聊天记忆和整个任务的预算，仍然由应用分别管理，不能从“工具已经连通”推导出这些能力也已经具备。

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

我在导入处保留了协议层与业务层的分工：`FastMCP` 负责注册与收发，`search_knowledge` 负责空参数校验、版本过滤和资料查找。同一条 E102 查询可以先直接验证，再通过 MCP 复测。如果两种方式结果不一致，排查范围就能缩小到连接、参数序列化或返回值转换。

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

然后按顺序读取三个 `await`。`initialize()` 完成双方协议与能力的协商；`list_tools()` 获取服务端实际提供的工具描述；`call_tool()` 才执行此次业务请求。我保留工具清单的打印，方便核对工具名称；需要检查参数结构时，再读取工具对象中的 `inputSchema`。这样即使进程能启动，也可以继续判断目标工具是否真正注册成功。

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

## 跑通之后，我对使用边界的整理

### 按复用需求选择接入方式

对进程内的固定功能，我仍会直接调用函数。只有一个固定客户端、现成 HTTP 约定也足够清晰时，同样可以沿用原接口。MCP 在这次实践中增加的是一致的工具描述、发现和调用入口，适合把同一能力提供给不同宿主。选择它的依据应是接入与复用需求，而不是期待换一种协议就能提高检索准确率。

这次使用的 stdio 由客户端管理本地进程。如果要将服务提供给远程应用，我会重新检查连接认证、传输与部署条件，并把断连、超时及并发加入验证范围。当前这份代码只负责本地一次完整交互，后续扩展需要保留这个可复现的基线。

### 将工具能力与数据权限分别管理

工具清单说明服务可以执行什么动作，数据访问范围则需要由可信身份与授权规则决定。我这里的三份演示资料没有租户和敏感字段，因此代码里没有账户系统。接入真实文档库时，我会先从应用身份得到访问范围，再将范围落实到查询中，而不是接受模型自由填写的用户或租户编号。

### 协议会话与聊天历史各司其职

本例中的会话负责协议连接和请求交互，聊天历史的保存、裁剪与读取范围由宿主另行实现。我会把这次检索结果与当前问题一起关联，再交给第七篇的会话模块；持久化时继续保留版本和证据标识，避免后来只能看见一段没有适用条件的文本。切换用户或任务时，也需要重新确定可用上下文。

### 用三条结果保留可复查的基线

这次实践最后留下了工具发现清单、正常证据、未知版本空结果和错误参数结果。下载包里的验证记录保留了三次调用的实际标准输出，后续升级 SDK 或调整返回结构时，可以继续用相同输入复测。

我目前验证到的是本地双端链路。下一步接入模型后，还要记录模型究竟选了什么工具、参数是否正确，以及最终回答是否使用了返回证据。把连接、工具执行和答案质量分开观察，才能知道每次新增能力实际解决了哪一层问题。
