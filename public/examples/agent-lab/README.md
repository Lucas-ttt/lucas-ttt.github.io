# AI Agent 代码实操

配套文章：https://lucas-ttt.github.io/posts/

这组示例使用自编的产品排障资料和退款记录，覆盖工具、校验、状态、执行闭环与MCP。文章中的Python代码与对应下载文件保持一致，每个非空代码行有中文注释。

## 从哪里开始

| 文章顺序 | 入口文件 | 实际观察 |
| --- | --- | --- |
| 01 | knowledge_tool.py | v2命中csv-v2，v1命中csv-v1，v9为空 |
| 02 | chunk_context.py | 字符边界、元数据与字段被截断的例子 |
| 03 | retrieval_demo.py | 有无版本约束的结果对照 |
| 04 | citation_checks.py | 来源ID、适用版本与语义支持的区别 |
| 05 | eval_tools.py | 8条固定工具回归用例 |
| 06 | sql_readonly.py | 350元、修正SQL重新校验、写入拒绝 |
| 07 | session_memory.py | SQLite会话隔离与历史字符预算 |
| 08 | langgraph_agent.py | 真实状态图、固定决策回放与6步停止 |
| 09 | retry_fallback.py | 四种故障注入与有限重试 |
| 10 | mcp_client.py | 启动mcp_server.py，发现工具并实际调用 |

## 环境

本次验证：Python 3.12.14，mcp 1.30.0、langgraph 1.2.19、langchain-core 1.7.4。第01—07、09篇只需Python标准库。08和10需要第三方依赖。

Windows PowerShell，在本目录执行：

```powershell
python -m venv .venv # 用已安装的Python 3.12建立独立环境。
.\.venv\Scripts\python.exe -m pip install -r requirements.txt # 安装固定的示例依赖。
.\.venv\Scripts\python.exe langgraph_agent.py # 默认回放决策，真实执行检索工具。
.\.venv\Scripts\python.exe mcp_client.py # 运行真正的本地MCP双端调用。
```

WSL或Linux，在本目录执行：

```bash
python3 -m venv .venv # 使用Python 3.12创建独立环境。
.venv/bin/python -m pip install -r requirements.txt # 安装固定的示例依赖。
.venv/bin/python langgraph_agent.py # 运行默认离线决策回放。
.venv/bin/python mcp_client.py # 运行本地MCP协议连接与工具调用。
```

## 三个边界实验

在已激活Python虚拟环境的终端执行：

```powershell
python langgraph_agent.py --repeat # 观察重复工具请求如何在图预算到达后结束。
python mcp_client.py --version v9 # 请求结构合法，但没有对应版本资料。
python mcp_client.py --bad-input # 注入空问题，观察工具错误返回。
```

MCP的服务端stdout用于协议通信，SDK处理日志可出现在stderr；不要将任意print输出放到服务端协议流里。

## 可选真实模型

langgraph_agent.py默认没有外部模型请求；工具确实执行，决策和最终拼接使用固定回放。显式使用--live时，model_client.py从环境读取AGENT_CHAT_URL、AGENT_MODEL、AGENT_API_KEY，再请求兼容该工具消息结构的服务。密钥不能写进文件或公开文章。

真实服务的模型ID、完整接口URL和工具能力应按服务商文档确认。此部分本次未用真实API Key验证；图循环、查询、回归、故障注入和本地MCP调用已执行，见verification.json及verified-output.txt。回放结果不代表真实模型回答质量，8条工具用例也不代表LLM准确率。

## 来源与代码范围

文章保留牛客、博客园中文作者的阅读入口，并用官方SDK或语言文档核对API。这里的业务数据与示例程序为本系列组织的可运行演练，没有收录未授权博客全文，也不将其他作者的项目成果列为个人经历。

示例按MIT许可证提供，见LICENSE。LangGraph和MCP属于独立的第三方项目，安装它们时适用各自许可证；本包不内置这些第三方依赖。
