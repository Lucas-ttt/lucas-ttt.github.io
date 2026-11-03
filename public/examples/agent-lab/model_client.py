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
