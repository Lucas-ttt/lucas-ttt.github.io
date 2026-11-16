# AI Agent 开发实践 · 配套代码

配套文章：https://lucas-ttt.github.io/posts/

当前十篇围绕同一个知识库原型，记录场景、选型、排错、切片、混合检索、执行编排、工具可靠性、评测、性能成本和重构。当前示例支持 Python 3.12 和更新版本，仅使用标准库。

## 作品集快速复现

下载 ZIP 后解压，在 `agent-lab` 目录打开终端。下列三个命令无需密钥或外部网络。

```sh
python replay_cases.py --case wrong_version
python retrieval_iteration.py --check
python refund_reconciliation.py --check
```

第一项会显示预期证据 `csv-v2` 及首个失败阶段 `metadata_filter`。改用 `--case context_dropped` 可看到检索命中、上下文为空。第二项检查别名补召回的逐条结果，第三项复核两期退款、渠道差额及只读写入拒绝。

## 本地问答接口

在第一个终端启动服务。默认监听 `127.0.0.1:8765`，使用词项基线返回原文。

```sh
python answer_service.py
```

在第二个终端查询。v2 会带回 `csv-v2`，将版本改为 v9 会得到 `insufficient_evidence`。

```powershell
Invoke-RestMethod http://127.0.0.1:8765/query -Method Post -ContentType 'application/json' -Body '{"query":"E102","version":"v2"}'
```

```bash
curl -s http://127.0.0.1:8765/query -H 'Content-Type: application/json' -d '{"query":"E102","version":"v2"}'
```

如需连接兼容聊天模型，启动前配置 `SUPPORT_CHAT_URL` 为完整的聊天补全地址和 `SUPPORT_CHAT_MODEL` 为模型名。需认证时通过环境变量 `SUPPORT_CHAT_API_KEY` 提供密钥。`SUPPORT_CHAT_TIMEOUT` 单位为秒，默认 5 秒。返回结果包含请求编号、证据、分段耗时，以及模型响应中可用的用量。

`python test_answer_service.py` 用本机受控 HTTP 端点验证正常返回、无证据、参数错误、合法引用、错引、模型出错与超时回落。引用检查覆盖 ID 与本次证据的对应关系。真实模型的回答质量仍需独立验证。

| 顺序 | 实践主题 | 入口文件 |
| --- | --- | --- |
| 01 | 从排障资料到可回查答案：我的知识库原型实践 | project_walkthrough.py |
| 02 | 我为什么给知识库选择 RAG，也保留长上下文和业务接口 | route_policy.py |
| 03 | 原文有答案却没有命中：我怎样沿检索链路定位问题 | retrieval_trace.py |
| 04 | 我如何拆分手册：保住表头、长段落和跨段条件 | structured_chunking.py |
| 05 | 从精确匹配到候选精排：我的混合检索实验 | hybrid_rerank.py |
| 06 | 先固定流程，再开放决策：我对 Workflow 和 Agent 的取舍 | workflow_agent.py |
| 07 | 把工具失败拆开处理：参数校验、有限重试与幂等 | tool_safety.py |
| 08 | 我给知识库建立了一份可复查的评测记录 | rag_evaluation.py |
| 09 | 先拆开耗时，再决定缓存和预算：我的性能成本实验 | latency_cost.py |
| 10 | 如果重做知识库，我会先统一请求、证据与执行契约 | redesign_contracts.py |

## 运行

在本目录使用 Python 3.12 及以上版本运行入口，例如：

```powershell
python project_walkthrough.py # 实际读取临时演示资料、建立词项索引并输出适用原文。
python rag_evaluation.py # 读取同一原型的候选并记录人工预期的命中与失败。
python latency_cost.py # 观察真实本机计时；模拟等待与用量不能代表线上性能。
python verify_examples.py # 复验文章示例、工具回归、作品集回放和本机问答。
```

第03、08、09篇导入 project_walkthrough.py；第06、07篇复用 knowledge_tool.py。工具现在通过薄包装调用同一个 retrieve 入口，英文字段名与错误码按完整词项匹配，中文仍采用子串基线。`E102` 能命中适用资料，`E10` 和 `id` 不再作为对应错误码或字段的证据。请保留整个目录，避免遗漏依赖文件。

## 自动回归与维护

`verify_examples.py` 检查错误码与字段片段、版本隔离、参数校验、空索引、工具返回结构，以及工具与项目在十条评测样例上的一致性。它还保留口语改写 `h2` 未命中的已知失败，不把回归通过等同于真实问答能力。

仓库发布前自动执行以下命令，额外核查十篇文章代码与对应脚本一致，并逐字节检查下载 ZIP；脚本直接运行不需要安装第三方包：

```bash
python3 public/examples/agent-lab/verify_examples.py --check-assets
```

修改示例后，在本目录运行 `python verify_examples.py --record`。从仓库根目录运行 `python scripts/pack-example-lab.py` 刷新下载包，再执行上述仓库检查。发布前会复验运行结果、文章与下载包一致性。

## 验证范围

verification.json 与 verified-output.txt 保留实际命令和输出，本次标准库复验与早期第三方框架记录分别标注。当前十个入口已运行；语义特征、规则重排、固定策略和模拟模型等待均属于可观察的实验替身，不等于真实 Embedding、交叉编码器或模型服务效果。计时会随设备与负载变化，演示单价不代表服务商实际报价。

## 早期补充实验

目录同时保留早期的knowledge_tool.py、chunk_context.py、retrieval_demo.py、citation_checks.py、eval_tools.py、sql_readonly.py、session_memory.py、langgraph_agent.py、model_client.py、retry_fallback.py、mcp_server.py、mcp_client.py、chunk_parameter_demo.py和rank_fusion_demo.py。它们的原验证记录仍可查；运行LangGraph和MCP补充实验时，先在独立环境安装requirements.txt锁定的依赖。外部模型--live适配器未用真实API Key验证，密钥仅从进程环境读取。

MIT许可见LICENSE。文章与下载的完整代码保持一致；更新代码时应同时更新说明与运行记录。
