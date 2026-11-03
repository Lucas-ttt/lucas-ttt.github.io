---
title: "MCP 双端实操：发现检索工具，区分空结果与调用错误"
description: "用固定版本MCP Python SDK运行stdio服务端和客户端，实际观察工具发现、v2证据、v9空结果和错误参数返回。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-01-05T12:00:00+08:00
featured: false
draft: false
tags:
  - agent
  - mcp
  - skill
series: "AI Agent 代码实操"
seriesOrder: 10
noteType: "代码实操"
---

[张高兴在博客园的LangGraph与MCP文章](https://www.cnblogs.com/zhanggaoxing/p/18889516)给出了服务端、工具加载和调用的文件结构。本篇先把链路收窄：一个客户端启动一个只读知识检索服务，实际发现工具并拿回结果。这里固定官方Python SDK的1.30.0版本，不混用main分支或旧适配器的API。

## 目录

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

## 接入Agent时增加哪一层

MCP解决工具能力与调用结果如何交换，宿主仍要把发现的工具描述交给模型，并校验模型请求、权限和预算。它不会自动保存对话长期记忆，也不会因为工具通过协议注册就自动完成授权。

如将本篇接入上一节LangGraph，需要把工具调用转交给该会话并回传结果，保留调用标识；不要同时另起一个互不关联的工具进程。真实多用户服务还要区分身份、会话与数据范围，本篇只演练一个本地只读工具。

## 中文原文与版本依据

- [张高兴：在LangGraph中使用MCP协议，博客园](https://www.cnblogs.com/zhanggaoxing/p/18889516)：中文文件结构与工具加载示例。
- [一枫说码：MCP双端实战，博客园](https://www.cnblogs.com/yifeng-coding/p/19766178)：补充客户端与服务端开发的阅读入口。
- [官方Python SDK v1.x](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)：核对本篇固定版本所属分支；升级SDK后应重新执行三个分支。
