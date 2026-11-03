export interface ProjectModule {
  title: string;
  description: string;
}

export interface ProjectStage {
  name: string;
  status: "已验证" | "待实现" | "尚未开始" | "方案已整理" | "参考已有" | "待复现" | "待改造" | "待验收";
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
    slug: "attribution-analysis",
    number: "01",
    title: "归因分析系统",
    subtitle: "从经营指标变化，到有数据依据的分析报告",
    status: "参考代码 · 待改造",
    statusDetail: "已获得并研读参考代码；本人尚未运行、改造或验收，不作为已完成项目成果。",
    summary:
      "面向电商经营指标分析，围绕 deepagents 与 LangGraph 参考架构，梳理自然语言提问、NL2SQL 取数、多维拆解与 HTML 报告链路。工程设计重点是指标口径、查询边界和分析结论的可追溯性。",
    tags: ["deepagents", "LangGraph", "NL2SQL", "FastAPI", "pandas"],
    audience: "电商运营、业务分析与经营管理人员",
    problem:
      "GMV、退款率等指标发生变化时，业务人员需要反复查询订单、退款和渠道数据，再按时间、商品、地域与人群拆解。时间窗口、金额单位或统计口径不一致，会让看似合理的解释缺少可靠依据。",
    scenario:
      "运营提问“最近三个月退款金额为什么增加”。参考流程先明确退款成功时间和金额口径，通过 NL2SQL 查询订单与退款数据，再按月份、原因、地域和渠道对比，保存中间数据并生成 HTML 分析报告。",
    objective:
      "为经营指标变化建立口径一致、数据可回查的分析路径，帮助业务人员定位变化集中的维度，并核对报告解释与计算依据。",
    contribution: [
      "参考架构：对话 Agent、NL2SQL 服务、身份认证与模拟电商数仓四个模块，覆盖从自然语言提问到分析报告的数据链路。",
      "口径核查设计：统一时间窗口、金额单位、退款状态与退款率分母，使用独立汇总查询核对分析口径。",
      "查询约束设计：SQL 执行前校验、纠错后复验、只读账号与查询范围限制，覆盖异常与超时反馈。",
      "验证设计：用固定经营问题与参考数据核查 SQL 结果、计算文件和报告依据，区分数据观察与原因假设。",
    ],
    flow: ["自然语言提问", "指标与元数据召回", "NL2SQL 取数", "多维拆解", "数据核对", "HTML 报告"],
    flowNote:
      "参考架构由 deepagents 组织工具与分析 Skill，LangGraph 编排 NL2SQL。db_query 通过 SSE 接收取数结果并保存为 CSV / JSON，pandas 承载分析计算，HTML 报告通过文件回传。",
    modules: [
      {
        title: "经营指标与多维分析",
        description:
          "参考分析 Skill 包含时间范围、金额单位与状态枚举等口径要求，覆盖趋势、退款原因、地域和渠道拆解。改造方案将提示约束转为可执行的口径检查与对账规则。",
      },
      {
        title: "NL2SQL 与元数据召回",
        description:
          "参考服务以 LangGraph 连接字段、指标和字段值召回、SQL 生成、EXPLAIN 验证、纠错与执行，涉及 MySQL、Qdrant 和 Elasticsearch。查询约束设计重点核查纠错后复验与执行权限边界。",
      },
      {
        title: "分析工作区与 HTML 报告",
        description:
          "参考代码将查询结果保存为 CSV / JSON，按用户与会话建立工作区，通过分析 Skill 和 pandas 形成中间文件与 HTML 报告。验证设计核对数据、图表与结论之间的对应关系。",
      },
      {
        title: "对话产品与服务组织",
        description:
          "参考项目包括 React 前端、FastAPI 服务、独立认证模块及模拟电商数仓，并有流式对话与会话上下文处理代码。集成验证设计覆盖依赖配置、模型与数据服务连接、流式交互及会话上下文。",
      },
    ],
    reliability: [
      {
        title: "口径一致，才能比较指标",
        description:
          "口径核查要求退款时间、状态、金额单位及分子分母窗口一致，并以独立 SQL 汇总结果对账。参考 Skill 中的提示约束需要对应数据级校验与差异记录。",
      },
      {
        title: "SQL 校验与执行权限分别约束",
        description:
          "参考代码包含 EXPLAIN 和错误纠正流程。查询约束设计覆盖纠错后再次校验、只读账号与查询范围限制，并以超时和错误用例核对执行边界。",
      },
      {
        title: "区分数据贡献与因果结论",
        description:
          "多维拆解用于发现变化集中的维度，不能单凭相关性证明因果。报告设计要求区分数据证据、候选驱动因素、原因假设及分析局限。",
      },
    ],
    stages: [
      {
        name: "参考架构与业务流程",
        status: "参考已有",
        evidence: "已从参考代码确认电商场景、四模块结构和取数到报告的设计；不代表本人完成开发或运行。",
      },
      {
        name: "本地部署与完整链路",
        status: "待复现",
        evidence: "待准备模型服务、MySQL、Redis、Elasticsearch、Qdrant 与样例数据，记录真实端到端运行结果。",
      },
      {
        name: "指标口径与查询约束",
        status: "待改造",
        evidence: "待增加可执行口径校验、纠错后复验、只读查询约束及失败处理。",
      },
      {
        name: "固定问题与报告核查",
        status: "待验收",
        evidence: "待保存测试问题、参考数据、SQL、计算文件和报告；暂无准确率、耗时或生产使用结论。",
      },
    ],
    acceptance: [
      "从经营问题、NL2SQL 取数到多维拆解与 HTML 报告的流程能够在样例数据上复现。",
      "时间窗口、金额单位、退款状态和统计分母有明确口径，并能与独立汇总结果核对。",
      "查询在执行前接受约束；无数据、SQL 错误与服务超时有可核查的失败记录。",
      "报告结论能够回查 SQL、CSV / JSON 和计算过程，区分已观察事实与待核实的原因假设。",
    ],
    takeaway:
      "经营分析报告应同时说明指标口径、数据来源、计算过程与原因假设，让读者能够回查依据和适用范围。",
  },
  {
    slug: "support-knowledge-base",
    number: "02",
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
      "帮助技术支持人员定位适用资料、核对回答依据，并沿文档处理、检索与生成链路回查问题。",
    contribution: [
      "当前已验证：使用 Python 读取 UTF-8 演示资料，按空行分段并统计片段数量。",
      "检索方案：来源与片段元数据、文档入库、向量检索、证据 Prompt 与问答接口的链路设计。",
      "可靠性设计：会话隔离、引用核查、无依据反馈、调用超时与检索原文降级。",
      "评估设计：固定问题集、分阶段耗时、失败定位记录与同配置复测。",
    ],
    flow: ["文档与来源", "清洗与切分", "向量索引", "问题检索", "证据生成", "答案与引用"],
    flowNote:
      "文档入库与在线问答分开组织。存储设计中，SQLite 管理业务元数据，Chroma 管理向量索引；回答引用由本次检索证据映射，保留来源与适用条件。",
    modules: [
      {
        title: "文档处理与来源记录",
        description:
          "文档处理方案从 TXT / Markdown 入库起步，为文档与片段设计可回查标识。清洗规则保留标题、版本与报错编号，使适用条件能够随片段传递。",
      },
      {
        title: "检索与证据组装",
        description:
          "检索方案连接 Embedding 与 Chroma，并记录候选片段、检索配置和来源映射。参数优化以单路基线与失败分析为依据，按需要比较关键词检索或重排。",
      },
      {
        title: "问答与上下文",
        description:
          "上下文设计按会话标识组织必要历史并控制输入预算。证据 Prompt 保留版本与业务条件，针对连续追问、话题切换和历史截断分别设置检查项。",
      },
      {
        title: "评估与问题定位",
        description:
          "评估设计固定问题及参考证据，分别记录检索命中、引用支持和答案质量。参数对比保留原始结果与单变量修改，便于复核方案取舍。",
      },
    ],
    reliability: [
      {
        title: "引用存在，也要检查是否支持结论",
        description:
          "引用设计包含两层检查：服务端核对引用 ID 是否来自本次检索，人工核查结论与片段的支持关系。分别检查标识有效性与语义支持程度。",
      },
      {
        title: "资料不足与服务故障分别反馈",
        description:
          "错误反馈设计区分库外问题、检索故障与生成失败。库外问题说明证据不足，检索成功而生成超时的降级方案展示原文与失败状态。",
      },
      {
        title: "保留定位问题需要的中间结果",
        description:
          "定位方案记录请求标识、召回片段、关键配置与分阶段耗时，沿解析、切分、索引、检索和生成链路建立可回查的检查点。",
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
];
