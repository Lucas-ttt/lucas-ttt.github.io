export interface ProjectModule {
  title: string;
  description: string;
}

export interface ProjectStage {
  name: string;
  status: "已验证" | "待实现" | "尚未开始" | "方案已整理";
  evidence: string;
}

export interface Project {
  slug: string;
  number: string;
  title: string;
  subtitle: string;
  status: string;
  statusDetail: string;
  summary: string;
  tags: string[];
  audience: string;
  problem: string;
  scenario: string;
  objective: string;
  contribution: string[];
  flow: string[];
  flowNote: string;
  modules: ProjectModule[];
  reliability: ProjectModule[];
  stages: ProjectStage[];
  acceptance: string[];
  takeaway: string;
}

export const projects: Project[] = [
  {
    slug: "support-knowledge-base",
    number: "01",
    title: "企业技术支持知识库",
    subtitle: "从分散文档，到有依据的回答",
    status: "开发中",
    statusDetail: "文档读取与分段原型已运行，完整 RAG 问答链路待实现。",
    summary:
      "围绕产品手册、FAQ 与排障指南，设计可回查来源的知识问答流程。把版本、错误码和回答依据保留下来，让技术支持中的检索与判断有迹可循。",
    tags: ["RAG", "Python", "FastAPI", "Chroma", "引用溯源"],
    audience: "客服、实施与技术支持人员",
    problem:
      "技术资料分散在手册、FAQ 和排障说明中，同一个报错可能因产品版本不同而有不同处理方式。只给出一段流畅回答，不能帮助支持人员确认它是否适用于当前问题。",
    scenario:
      "用户询问 CSV 导入失败。系统需要定位必填字段、编码和报错编号对应的说明，返回处理建议，并让使用者打开依据原文；资料没有覆盖时，应说明缺少的条件。",
    objective:
      "把文档定位、答案生成和来源核查连接起来，并能通过中间结果区分文档处理、检索和生成阶段的问题。",
    contribution: [
      "当前已验证：使用 Python 读取 UTF-8 演示资料，按空行分段并统计片段数量。",
      "拟承担：来源与片段元数据设计、文档入库、向量检索、证据 Prompt 和问答接口。",
      "拟承担：会话隔离、引用核查、无依据反馈、调用超时与原文降级。",
      "拟承担：固定问题集、失败定位记录、分阶段耗时与复测说明。",
    ],
    flow: ["文档与来源", "清洗与切分", "向量索引", "问题检索", "证据生成", "答案与引用"],
    flowNote:
      "文档入库与在线问答分开组织。SQLite 拟保存业务元数据，Chroma 拟保存向量索引；每次回答关联本次检索的证据片段，而不是让模型自行编造引用。",
    modules: [
      {
        title: "文档处理与来源记录",
        description:
          "从 TXT / Markdown 起步，为文档和片段分配可回查标识。保留标题、版本、报错编号等条件，避免清洗时丢失适用范围。",
      },
      {
        title: "检索与证据组装",
        description:
          "接入 Embedding 与 Chroma，保存候选片段和检索配置。先建立单路检索基线，再按真实失败决定是否增加关键词检索或重排。",
      },
      {
        title: "问答与上下文",
        description:
          "使用检索证据约束回答，按会话标识隔离历史并限制输入预算。连续追问需要保留必要业务条件，话题切换时避免沿用旧版本信息。",
      },
      {
        title: "评估与问题定位",
        description:
          "固定问题与参考证据，分别判断检索命中、引用支持和答案质量。保留原始结果，用单变量修改与复测说明方案取舍。",
      },
    ],
    reliability: [
      {
        title: "引用存在，也要检查是否支持结论",
        description:
          "拟由服务端检查引用 ID 是否来自本次检索，再人工核查结论与片段的支持关系。引用合法与事实正确是两个不同的检查。",
      },
      {
        title: "资料不足与服务故障分别反馈",
        description:
          "库外问题说明证据不足；检索成功而生成超时时展示已找到的原文与失败状态，避免把技术故障解释成知识不存在。",
      },
      {
        title: "保留定位问题需要的中间结果",
        description:
          "拟记录请求标识、召回片段、关键配置和分阶段耗时，让错误可以沿解析、切分、索引、检索和生成链路回查。",
      },
    ],
    stages: [
      {
        name: "演示资料读取与分段",
        status: "已验证",
        evidence: "UTF-8 CSV 导入说明按空行拆分，实际运行输出 4 个片段。",
      },
      {
        name: "片段元数据与持久化检索",
        status: "待实现",
        evidence: "待补来源标识、重复导入处理、Embedding 与 Chroma 检索。",
      },
      {
        name: "带引用的真实问答",
        status: "待实现",
        evidence: "待验证 LLM 调用、引用核查、会话隔离和连续追问。",
      },
      {
        name: "异常处理与固定评估",
        status: "待实现",
        evidence: "待记录无依据、超时和检索失败行为，以及真实失败复测。",
      },
    ],
    acceptance: [
      "能够从原文、片段、检索证据一路回查到答案中的引用。",
      "文档内、库外与条件冲突的问题都有明确的预期行为和实际记录。",
      "检索成功但生成失败时，能够展示原文并说明系统状态。",
      "保存固定测试、失败分析与复测配置，结果可重新运行核对。",
    ],
    takeaway:
      "这个项目关注的不只是返回答案，而是能说明答案来自哪里、适用于什么条件，以及错误发生在哪个环节。",
  },
  {
    slug: "support-ticket-agent",
    number: "02",
    title: "归因分析系统",
    subtitle: "从报错线索，到可核查的原因假设",
    status: "方案设计",
    statusDetail: "基于 Hermes Agent 的第二项目，尚未开始开发。",
    summary:
      "面向企业软件故障，设计线索补全、证据检索、原因假设与核验流程。复用知识库能力，重点记录依据、待核验项与人工确认结果。",
    tags: ["Hermes Agent", "MCP", "Tool Calling", "Skills", "任务状态"],
    audience: "售后与技术支持团队",
    problem:
      "报错受理常常缺少版本、异常信息和已尝试步骤。资料查询、补问与工单整理之间容易反复切换；工具超时或重复提交时，也需要知道任务到底完成到了哪一步。",
    scenario:
      "用户描述 CSV 导入失败。系统补齐版本、报错与已尝试步骤，检索适用证据，整理候选原因及核验方法；未完成核验时保留假设状态，经人工确认后保存归因报告与待处理事项。",
    objective:
      "让每个候选原因对应可回查证据与核验步骤；在信息不足或工具失败时保留不确定项，并形成可供人工接续的归因记录。",
    contribution: [
      "拟承担：故障场景拆解、线索与证据字段、原因假设和归因报告设计。",
      "拟承担：通过标准 MCP 接入知识检索、案例查询与归因记录工具。",
      "拟承担：排障 Skill 的触发条件、步骤、工具范围、停止条件和结构化输出。",
      "拟承担：参数校验、确认写入、幂等处理、调用记录与失败接续。",
    ],
    flow: ["线索补全", "证据检索", "原因假设", "核验步骤", "归因报告", "人工交接"],
    flowNote:
      "Hermes Agent 拟承担工具使用与排查步骤组织。业务服务负责字段、确认状态和重复请求检查；每个原因都需区分推测、待核验和已确认状态。首版使用本地演示案例，不接入真实客户系统。",
    modules: [
      {
        title: "知识检索工具",
        description:
          "复用项目一的检索服务，通过 MCP 返回片段、来源与适用条件。没有依据时保留未确认项，不把推测写成已核实结论。",
      },
      {
        title: "归因记录与人工交接",
        description:
          "计划保存故障现象、产品版本、引用证据、候选原因和核验步骤。服务端核对确认状态与请求标识后保存报告，未核验项保留为假设。",
      },
      {
        title: "可加载的排障 Skill",
        description:
          "将线索收集、依据检索、假设整理、核验和人工升级整理为任务说明。保留加载与执行轨迹，检查每项建议的依据与适用条件。",
      },
      {
        title: "任务状态与执行记录",
        description:
          "记录任务标识、工具参数摘要、调用结果和耗时，区分已完成、失败与待确认步骤，为人工接手提供上下文。",
      },
    ],
    reliability: [
      {
        title: "确认由业务服务校验",
        description:
          "工具端拟核验用户确认和草稿版本，避免只靠提示词约束写入；内容发生变化后，需要重新确认对应草稿。",
      },
      {
        title: "重复提交返回同一处理结果",
        description:
          "拟使用幂等请求标识和数据库约束处理超时重试，检查多次调用后实际新增的记录数量。具体机制待实现与验证。",
      },
      {
        title: "执行有边界，失败有交接",
        description:
          "拟设置最大步骤与超时预算。工具失败时说明已完成操作、尚未完成事项与终止原因，避免将未执行的动作描述成成功。",
      },
    ],
    stages: [
      {
        name: "业务场景与验收边界",
        status: "方案已整理",
        evidence: "本文记录业务场景与初步验收边界，详细字段和可执行验收用例待实现。",
      },
      {
        name: "Hermes 运行与 MCP 接入",
        status: "尚未开始",
        evidence: "尚未安装、配置或验证工具发现与调用。",
      },
      {
        name: "Skill 与归因分析主链",
        status: "尚未开始",
        evidence: "尚无 Skill 加载、原因核验和归因报告保存的运行记录。",
      },
      {
        name: "失败处理与任务评估",
        status: "尚未开始",
        evidence: "尚无任务成功率、工具调用或耗时的实测结论。",
      },
    ],
    acceptance: [
      "从故障线索、证据检索、原因假设到核验步骤和归因报告的流程可复现。",
      "缺少信息与无检索证据时，能够提问或标记未确认事实。",
      "未经核验的原因保留为假设；未经确认的报告写入被拒绝，重复请求不重复保存。",
      "工具超时后能够给出已完成步骤、未完成事项与人工接续信息。",
    ],
    takeaway:
      "这个项目的设计重点，是把故障线索、证据支持、核验步骤与人工确认联系起来，让一次失败也能解释清楚并继续处理。",
  },
];
