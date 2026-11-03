from mcp.server.fastmcp import FastMCP  # 使用固定在 requirements.txt 中的官方 v1 SDK。
from knowledge_tool import search_knowledge  # 复用同一份只读版本检索逻辑。

server = FastMCP("lucas-knowledge")  # 服务名用于工具发现。

@server.tool()  # 将普通函数注册成可发现的 MCP 工具。
def lookup_support(query: str, version: str) -> list[dict]:  # SDK 会根据签名生成参数描述。
    """按明确的产品版本检索演示排障资料。"""  # 工具说明由客户端取得。
    return search_knowledge(query, version)  # 后端仍负责校验参数与执行读取。

if __name__ == "__main__":  # 客户端会通过子进程启动本文件。
    server.run(transport="stdio")  # 标准输出专用于协议，不能向其中随意 print 日志。
