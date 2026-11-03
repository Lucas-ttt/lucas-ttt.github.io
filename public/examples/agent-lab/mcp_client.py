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
