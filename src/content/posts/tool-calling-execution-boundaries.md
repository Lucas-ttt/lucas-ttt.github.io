---
title: "Tool Calling 怎样执行，Agent 怎样停止循环？"
description: "从工具描述、调用标识到结果回传拆解 LangGraph 执行闭环，解释固定回放、真实模型接口与图步数限制。"
pubDatetime: 2026-11-03T10:00:00+08:00
archiveDatetime: 2026-02-02T12:00:00+08:00
featured: false
draft: false
tags:
  - tool-calling
  - agent
  - 可靠性
series: "AI Agent 面试十问"
seriesOrder: 8
noteType: "代码实操"
---

先看[幻想offer的牛牛在牛客写的消息与工具调用示例](https://www.nowcoder.com/discuss/921906577349545984)：它把工具请求和工具返回放回同一段消息历史，便于理解后端究竟执行了什么。本篇将业务换成“v2导入报E102”，使用LangGraph实际运行decide→tools→decide三段流程。

默认决策采用固定回放，检索工具真实执行，不需要API Key。这样可以稳定核对消息与退出条件；真实模型由`--live`显式启用，其服务效果需要另外验证。

## 目录

## 面试题：Tool Calling 的完整流程是什么，如何限制 Agent 循环？

它容易被答成“模型选择一个函数，再返回结果”，却漏掉真正决定可靠性的中间环节：谁定义参数、谁执行代码、工具返回如何对应到原请求、什么时候结束。如果这几个责任没有说清，面试官继续追问一个错误版本、一个不存在的工具或者一次重复调用，回答就很难落到实现上。

### 一分钟回答

应用先把允许调用的工具名称、说明和参数结构发送给模型。模型返回工具请求后，程序解析参数，匹配已注册工具，并在执行前进行类型、业务条件和权限检查。工具执行的结果以对应调用标识回填历史，再让模型决定回答、补充调用或报告信息不足。模型提出调用不等于工具已经执行，参数结构正确也不代表用户有执行权限。本例用 LangGraph 显式组织决策、工具、再次决策三个节点，默认固定回放以稳定核对轨迹；重复调用故障通过六个图步数终止。实际服务还需要独立的超时、总成本预算和高风险动作确认，不能只依赖一句“不要无限循环”的提示词。

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

## 代码逐段解析：消息怎样驱动下一步

### 工具描述是契约，注册表是执行入口

`@tool` 将函数名、说明和类型信息转成工具描述。`version` 使用有限选项，便于告诉调用方只接受 v1 或 v2；函数体仍把数据交给 `search_knowledge`，由它校验空问题、返回数量并过滤版本。描述写得清楚能减少错误请求，但真正的执行边界仍在程序里。假如业务改成查询私有订单，用户身份应由受信任的应用上下文注入，不能让模型通过一个自由填写的参数授予自己权限。

`ToolNode([lookup_support])` 只注册这个查询工具。它执行的是应用事先选定的函数，不是对模型返回文本做 `eval`。将工具数量限制到完成当前任务所必需的范围，能让输入契约与失败状态更容易检查；工具多并不自动代表 Agent 更强。模型返回了未知名称时，也不应该临时下载插件或执行同名命令来迎合请求。

### 状态更新必须保存请求与结果

状态只保存 `messages`，并交由 `add_messages` 合并节点返回的新消息。本例每轮请求都有一个调用标识，工具消息再与它关联。这个标识用于回答“这条返回属于哪次调用”，与业务幂等键是两回事，不能因为有一个 ID 就认为重复退款能自动去重。[DeepSeek 工具调用说明](https://api-docs.deepseek.com/zh-cn/guides/tool_calls/) 展示了请求和结果回填的消息关系；实际采用其他兼容服务时，还应核对其支持的字段和限制。

如果状态更新直接覆盖整个列表，下一轮可能只看到工具结果，丢失用户原问题和此前调用；如果只保存模型文字，又会把“准备查询”误当成“已经查询”。排查时应同时查看消息角色、工具名、参数和调用标识，避免只展示最后一句自然语言。

### 条件边决定继续还是停止

第一次进入 `decide`，离线分支发出查询 v2、E102 的请求；条件边发现有 `tool_calls`，转入 `tools`。工具节点执行真正的只读查询并追加返回；再次进入 `decide`，回放分支读取返回原文，输出没有工具请求的 AI 消息，条件边因此指向 END。这里的“结束”来自结构化状态，而不是检查回答里是否含有“完成”二字。

`rows` 为空时，回放明确返回没有适用资料；工具消息带错误状态时，回放返回输入核对提示。二者不能混成同一情况：前者可能是正常的无命中，后者表示调用未正常完成。真实模型也可能在工具成功后给出不受支持的结论，所以执行流程正确只是必要条件，最终答案仍应使用本系列第四篇的引用检查思路继续验证。

### 固定回放验证流程，真实模型验证决策

默认分支把工具名和参数写死，能稳定复现消息与停止逻辑，却没有评估模型是否会自行选对工具、版本或参数。`--live` 才将转换后的消息与工具描述发送给兼容服务，解析其返回的 JSON 参数，再交给同一个图执行。这个转换层同样会遇到无效 JSON、缺失字段、未知工具或服务异常；当前适配器没有把这些情况全部包装成可恢复的产品状态，接入后应补充明确处理，而不是让通用异常堆栈直接成为用户反馈。

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

## 面试追问：图写出来之后还有哪些风险？

**用了图框架，这就是 Agent 吗？** 框架只提供编排方式。固定回放中的下一步由代码确定，适合验证流程；真实模式才把工具选择交给模型。两者共用图不代表决策机制相同。[LangGraph 工作流与 Agent 官方文档](https://docs.langchain.com/oss/python/langgraph/workflows-agents) 可用于核对这一区分。选型时应看任务是否需要动态选择工具，简单确定性查询也可以使用固定工作流。

**为什么六步只能执行三次工具？** 这个示例把决策节点和工具节点分别计入图执行轨迹，重复模式出现三组 decide、tools 后到达上限。图步数并不是通用工具计数器，换成并行节点或其他图结构时不能照搬这个换算。业务若要求最多调用两次收费工具，应另设工具调用计数，而不是只调 recursion_limit。

**检索结果里出现“忽略前面要求”怎么办？** 返回正文应作为待使用的数据，不应变成扩大工具权限的新指令。工具注册表、身份校验和执行限制必须由应用控制。当前自编资料没有实现提示注入检测，不能宣称已解决这类攻击；可以增加含恶意指令的测试资料，检查系统是否仍只调用允许的只读工具。

**工具调用成功，但用户断线了，重新请求会怎样？** 只读检索再次执行通常只增加开销；写入型操作可能造成重复副作用。此时需要业务操作标识、状态查询和幂等约束。消息里的调用 ID 用来关联通信，不足以替代业务去重。面试回答应先说明当前工具只读，再解释写操作接入前还欠缺哪些执行保障。

## 中文原文与技术核查入口

- [幻想offer的牛牛：消息到工具调用，牛客](https://www.nowcoder.com/discuss/921906577349545984)：先观察请求、调用标识与返回的对应关系。
- [张高兴：LangGraph会话历史，博客园](https://www.cnblogs.com/zhanggaoxing/p/18791377)：继续阅读线程与持久化示例，注意按实际依赖版本调整API。
- [LangGraph官方仓库](https://github.com/langchain-ai/langgraph)与[工作流/Agent文档](https://docs.langchain.com/oss/python/langgraph/workflows-agents)：核对节点、条件边和运行接口。
