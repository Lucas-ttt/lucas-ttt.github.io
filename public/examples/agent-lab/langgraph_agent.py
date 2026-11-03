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
