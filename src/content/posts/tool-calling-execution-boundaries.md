---
title: "LangGraph 工具调用实操：跑通决策、执行、回传和停止"
description: "使用实际LangGraph构建可运行工具循环，展示正常轨迹与6步终止，并提供兼容模型服务的可选接入代码。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-02-02T12:00:00+08:00
featured: false
draft: false
tags:
  - tool-calling
  - agent
  - 可靠性
series: "AI Agent 代码实操"
seriesOrder: 8
noteType: "代码实操"
---

先看[幻想offer的牛牛在牛客写的消息与工具调用示例](https://www.nowcoder.com/discuss/921906577349545984)：它把工具请求和工具返回放回同一段消息历史，便于理解后端究竟执行了什么。本篇将业务换成“v2导入报E102”，使用LangGraph实际运行decide→tools→decide三段流程。

默认决策采用固定回放，检索工具真实执行，不需要API Key。这样可以稳定核对消息与退出条件；真实模型由`--live`显式启用，其服务效果需要另外验证。

## 目录

## 准备文件与固定依赖

环境：Python 3.12。解压[完整示例](/examples/agent-lab.zip)，在agent-lab目录运行。已验证版本为langgraph 1.2.19、langchain-core 1.7.4。目录内保留knowledge_tool.py和model_client.py，不要只复制一个入口文件。

```powershell
python -m pip install -r requirements.txt # 在已激活的虚拟环境安装本系列固定依赖。
python langgraph_agent.py # 默认运行离线决策回放，真实执行只读检索。
```

## 完整状态图代码

```python
import argparse  # 选择默认回放、重复调用或真实模型模式。
import json  # 将工具结果和模型参数转换为结构化数据。
from typing import Annotated, Literal, TypedDict  # 定义状态和工具参数范围。
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, convert_to_openai_messages  # 使用框架消息类型。
from langchain_core.tools import tool  # 将 Python 函数注册为工具。
from langchain_core.utils.function_calling import convert_to_openai_tool  # 生成兼容聊天接口的工具描述。
from langgraph.errors import GraphRecursionError  # 识别达到图执行上限的情况。
from langgraph.graph import END, START, StateGraph  # 使用实际 LangGraph 状态图。
from langgraph.graph.message import add_messages  # 追加消息而非覆盖整段状态。
from langgraph.prebuilt import ToolNode  # 由框架执行注册工具并回写 ToolMessage。
from knowledge_tool import search_knowledge  # 复用已经运行的版本过滤检索。
from model_client import request_model  # 真实模型服务与回放策略使用同一图。

class State(TypedDict):  # 图状态只保存本次演示所需消息。
    messages: Annotated[list, add_messages]  # reducer 保留工具调用与返回的对应关系。

@tool  # 该装饰器生成工具输入描述。
def lookup_support(query: str, version: Literal["v1", "v2"]) -> list[dict]:  # 把版本范围放到参数契约中。
    """按问题和产品版本检索排障资料，返回来源及原文。"""  # 描述提供给模型和工具执行器。
    return search_knowledge(query, version)  # 工具内部仍执行真正的参数与版本检查。

def build_graph(live=False, repeat=False):  # 决策实现可替换，执行图不变。
    def decide(state):  # 每轮读取当前消息，决定请求工具或结束。
        messages = state["messages"]  # 不修改调用方传入的消息列表。
        if live:  # 只有显式选择 --live 才访问外部服务。
            raw = request_model(convert_to_openai_messages(messages), [convert_to_openai_tool(lookup_support)])  # 发送工具描述及当前上下文。
            calls = [{"name": item["function"]["name"], "args": json.loads(item["function"]["arguments"]), "id": item["id"]} for item in raw.get("tool_calls", [])]  # 解析请求，不执行模型生成的任意代码。
            answer = AIMessage(content=raw.get("content") or "", tool_calls=calls)  # 将实际服务结果交给图路由。
        elif isinstance(messages[-1], ToolMessage) and not repeat:  # 默认回放收到结果后即结束。
            if messages[-1].status == "error":  # 参数或工具错误不能当作正常证据解析。
                answer = AIMessage(content="工具执行失败，请核对输入条件。")  # 回放分支明确结束并反馈错误。
            else:  # 仅解析正常工具返回。
                rows = json.loads(messages[-1].content)  # 读取真实工具返回的演示证据。
                answer = AIMessage(content=f"{rows[0]['text']} [来源 {rows[0]['id']}]" if rows else "没有适用资料。")  # 回放输出是确定性的，不冒充真实模型回答。
        else:  # 第一轮或故意重复模式发出同一个只读工具请求。
            answer = AIMessage(content="", tool_calls=[{"name": "lookup_support", "args": {"query": "E102", "version": "v2"}, "id": f"lookup-{len(messages)}"}])  # 保留每轮调用标识。
        return {"messages": [answer]}  # 由 reducer 将新消息加入状态。
    builder = StateGraph(State)  # 定义本地执行图。
    builder.add_node("decide", decide)  # 添加模型或回放决策节点。
    builder.add_node("tools", ToolNode([lookup_support]))  # 仅注册一个允许执行的工具。
    builder.add_edge(START, "decide")  # 从决策节点开始。
    builder.add_conditional_edges("decide", lambda state: "tools" if state["messages"][-1].tool_calls else END)  # 有工具请求才进入工具节点。
    builder.add_edge("tools", "decide")  # 工具返回后重新决策，不能直接假定任务完成。
    return builder.compile()  # 编译状态图。

if __name__ == "__main__":  # 三种运行模式都从此入口开始。
    parser = argparse.ArgumentParser()  # 使用标准命令行参数。
    parser.add_argument("--live", action="store_true")  # 真实服务需要用户自行配置密钥与模型。
    parser.add_argument("--repeat", action="store_true")  # 此模式注入重复调用故障。
    options = parser.parse_args()  # 读取运行方式。
    graph = build_graph(options.live, options.repeat)  # 默认不访问外网。
    try:  # 记录节点轨迹并展示最终结果。
        for event in graph.stream({"messages": [SystemMessage(content="先调用工具核查产品版本；只按返回原文作答，附来源ID，没有资料时说明不足。"), HumanMessage(content="v2 导入报 E102，应该检查什么？")]}, {"recursion_limit": 6}, stream_mode="updates"):  # 上限是图执行步数，不是 Token 或总时间。
            for node, update in event.items():  # 一次更新对应一个实际执行节点。
                message = update["messages"][-1]  # 取得该节点新增的消息。
                print("节点", node, "消息", message.type)  # 不输出密钥或模型内部推理。
                if isinstance(message, AIMessage) and not message.tool_calls:  # 只有无工具请求的模型消息作为最终输出。
                    print("结果", message.content)  # 显示工具证据驱动的回放结果或真实模型返回。
    except GraphRecursionError:  # 重复模式应该到达此受控出口。
        print("达到图执行上限：6 步")  # 达到上限后停止继续调用。
```

messages使用add_messages追加，工具结果保留对应调用ID。条件边只检查当前AI消息有没有tool_calls：有则进入工具节点，没有则结束。ToolNode仅注册lookup_support，工具参数中的版本范围由Literal声明，读取资料时仍调用同一检索校验。

## 实际运行轨迹

```text
节点 decide 消息 ai
节点 tools 消息 tool
节点 decide 消息 ai
结果 CSV 导入缺少 customer_id 列，检查首行表头。 [来源 csv-v2]
```

工具返回csv-v2原文后，回放分支生成带来源ID的输出。这里没有让模型凭空写customer_id；默认最终文本由实际返回资料组成。模型或回放决策与工具执行是两个独立步骤。

## 故障实验：一直请求同一个工具

```powershell
python langgraph_agent.py --repeat # 注入重复请求，观察图执行预算能否终止。
```

```text
节点 decide 消息 ai
节点 tools 消息 tool
节点 decide 消息 ai
节点 tools 消息 tool
节点 decide 消息 ai
节点 tools 消息 tool
达到图执行上限：6 步
```

recursion_limit限制图执行步数，不等于六次模型调用，也不等于整个任务六秒。上限到达后应记录未完成状态，不能为了给出答案继续无限调用。本例工具即时返回；外部工具仍需要各自的超时与取消机制。

## 可选：接入真实兼容模型服务

下面的适配器读取AGENT_CHAT_URL、AGENT_MODEL和AGENT_API_KEY。URL应是服务商文档规定的完整聊天接口，模型必须支持这里的工具调用消息格式。密钥由本机环境配置，不写入文章或Git仓库。[DeepSeek官方中文Tool Calls说明](https://api-docs.deepseek.com/zh-cn/guides/tool_calls/)可核对这一消息契约；当前DeepSeek分支显式使用非思考工具调用。

```python
import json  # 使用兼容工具调用协议的 JSON 数据。
import os  # 仅从当前进程环境读取配置，不保存密钥。
from urllib.request import Request, urlopen  # 用标准库发送一次模型请求。
from urllib.parse import urlsplit  # 精确识别服务端主机名。

def request_model(messages, tools):  # 此适配器只在显式选择真实服务时调用。
    endpoint = os.environ.get("AGENT_CHAT_URL")  # 填写服务商提供的完整聊天接口 URL。
    model = os.environ.get("AGENT_MODEL")  # 使用该服务实际支持的模型名称。
    api_key = os.environ.get("AGENT_API_KEY")  # 密钥不进入示例文件或输出。
    if not endpoint or not model or not api_key:  # 在网络请求前检查必填配置。
        raise ValueError("请先设置 AGENT_CHAT_URL、AGENT_MODEL、AGENT_API_KEY")  # 不携带配置值报告错误。
    if not endpoint.startswith("https://"):  # 示例仅允许加密的外部模型连接。
        raise ValueError("AGENT_CHAT_URL 必须使用 HTTPS")  # 避免明文发送密钥。
    payload = {"model": model, "messages": messages, "tools": tools}  # 模型提出调用后仍由应用执行工具。
    if urlsplit(endpoint).hostname == "api.deepseek.com":  # 当前 DeepSeek 示例使用非思考工具调用，避免丢失额外推理字段。
        payload["thinking"] = {"type": "disabled"}  # 其他兼容服务不携带这个厂商专用参数。
    request = Request(endpoint, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})  # 身份信息只随请求发送。
    with urlopen(request, timeout=15) as response:  # 单次 HTTP 请求设置超时，不声明全任务十五秒完成。
        data = json.load(response)  # 读取实际服务的结构化返回。
    return data["choices"][0]["message"]  # 仅支持兼容此响应结构的模型服务。
```

```powershell
python langgraph_agent.py --live # 配置三个环境变量后才会请求你选择的真实模型服务。
```

单次HTTP调用设15秒超时，图步数与单次超时仍不是严格的全任务墙钟时间保证。本次已验证离线正常路径和重复终止，未使用真实API Key验证外部模型效果；真实输出应重新检查引用与业务条件。

## 中文原文与技术核查入口

- [幻想offer的牛牛：消息到工具调用，牛客](https://www.nowcoder.com/discuss/921906577349545984)：先观察请求、调用标识与返回的对应关系。
- [张高兴：LangGraph会话历史，博客园](https://www.cnblogs.com/zhanggaoxing/p/18791377)：继续阅读线程与持久化示例，注意按实际依赖版本调整API。
- [LangGraph官方仓库](https://github.com/langchain-ai/langgraph)与[工作流/Agent文档](https://docs.langchain.com/oss/python/langgraph/workflows-agents)：核对节点、条件边和运行接口。
