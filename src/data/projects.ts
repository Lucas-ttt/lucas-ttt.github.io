export interface ProjectModule {
  title: string;
  description: string;
}

export interface ProjectStage {
  name: string;
  status:
    | "已验证"
    | "待实现"
    | "尚未开始"
    | "方案已整理"
    | "参考已有"
    | "待复现"
    | "待改造"
    | "待验收";
  evidence: string;
}

export interface ProjectCaseStudy {
  id: string;
  label: string;
  title: string;
  question: string;
  context: string;
  risk: string;
  decision: string;
  checks: string[];
  evidence: string[];
  takeaway: string;
}

export interface Project {
  slug: string;
  number: string;
  title: string;
  subtitle: string;
  category: string;
  status: string;
  statusDetail: string;
  summary: string;
  deliverables: { label: string; href: string; description: string }[];
  reproduce?: string;
  results?: { input: string; output: string; detail: string }[];
  highlights: ProjectModule[];
  cases: ProjectCaseStudy[];
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
    subtitle: "带版本约束的离线知识检索原型",
    category: "离线检索原型",
    status: "离线原型 · 已验证",
    statusDetail:
      "已验证三份自编资料的读取、切片、词项检索与版本过滤；输出为原文抽取，真实模型与在线服务待接入。",
    summary:
      "用 Python 复现同一错误码在不同版本下的处理差异，返回适用原文与来源，并用固定小样本检查命中、空结果和失败。",
    deliverables: [
      {
        label: "查看核心代码",
        href: "https://github.com/Lucas-ttt/lucas-ttt.github.io/blob/main/public/examples/agent-lab/project_walkthrough.py",
        description:
          "文件读取、规范化切片、内存词项索引、版本过滤与原文返回共用同一条数据链路。",
      },
      {
        label: "查看运行记录",
        href: "/examples/agent-lab/verified-output.txt",
        description: "保留实际输入输出与小样本评测结果，可以对照脚本重新运行。",
      },
      {
        label: "下载复现示例",
        href: "/examples/agent-lab.zip",
        description:
          "Python 离线示例、运行说明与验证记录；核心原型不需要密钥和外部服务。",
      },
    ],
    reproduce: "python project_walkthrough.py\npython rag_evaluation.py",
    results: [
      {
        input: "E102 · 产品 v2",
        output: "检查 customer_id 列",
        detail: "返回 csv-v2 的实际原文与来源；状态为 ok。",
      },
      {
        input: "E102 · 产品 v1",
        output: "检查 user_id 列",
        detail: "同一错误码只返回 csv-v1，不混用新版本资料。",
      },
      {
        input: "E102 · 未收录的 v9",
        output: "当前资料未找到适用依据",
        detail:
          "证据列表为空，状态为 insufficient_evidence，不借用其他版本补齐。",
      },
    ],
    highlights: [
      {
        title: "同一错误码，按版本返回依据",
        description:
          "已验证 v1 的 E102 返回 user_id，v2 返回 customer_id；版本过滤发生在评分之前，输出保留本次命中的证据 ID 与原文。",
      },
      {
        title: "保留失败，而非只展示命中",
        description:
          "十条人工问题分为开发集与留出集。Top-K 从 1 调到 2 后，留出样例规则验收从 5/7 到 6/7，口语改写仍失败；这只说明该小型离线实验。",
      },
    ],
    cases: [
      {
        id: "version-aware-evidence",
        label: "已运行的离线实验",
        title: "同一 E102，两个版本返回不同字段",
        question: "产品 v2 导入 CSV 报 E102，应该检查哪个字段？",
        context:
          "用三份自编排障资料建立内存索引：两份分别描述 v1、v2 的 E102，另一份描述 v2 的编码问题。数据和输出均为个人离线实验。",
        risk: "只按错误码查找，会遇到两条相关但版本不同的资料。若把 v1 的 user_id 要求用于 v2，即使提供了来源，建议仍然不适用。",
        decision:
          "让版本、错误码、来源与正文一起进入片段；检索先过滤版本，再做词项匹配。输出直接抽取命中的原文，并附上对应证据 ID。",
        checks: [
          "运行 E102 / v2，返回 customer_id 与来源 csv-v2。",
          "改为 E102 / v1，返回 user_id 与来源 csv-v1。",
          "改为未收录的 v9，返回空证据和 insufficient_evidence 状态。",
        ],
        evidence: [
          "project_walkthrough.py：三份演示资料、索引和查询入口",
          "verified-output.txt：E102 在 v1、v2、v9 下的实际输出",
          "rag_evaluation.py：跨版本与库外问题的固定样例",
        ],
        takeaway:
          "已知版本必须参与检索条件；没有适用资料时结束于明确状态，而非用其他版本答案填补。",
      },
      {
        id: "top-k-regression",
        label: "已运行的小样本对照",
        title: "多取一个候选，解决了什么、没解决什么？",
        question: "同时询问字段和编码时，Top-K 从 1 改为 2 会怎样？",
        context:
          "人工标注十条问题与参考证据，三条用于开发、七条留出观察；语料仍是同一组微型自编资料，不代表真实用户问题分布。",
        risk: "只取一条候选可能遗漏组合问题的一半依据；仅看平均命中率，又会掩盖词项检索不理解口语改写的限制。",
        decision:
          "固定语料、匹配规则和标注，仅调整 Top-K，分别记录证据召回、规则验收、空结果与失败输入。",
        checks: [
          "Top-K=1 时开发样例通过 2/3，留出样例通过 5/7。",
          "Top-K=2 时开发样例通过 3/3，留出样例通过 6/7；留出问题中三个应为空的请求均返回空结果。",
          "“上传时找不到客户字段”仍无命中，保留为后续检索改进的失败样例。",
        ],
        evidence: [
          "rag_evaluation.py：问题、证据标注与评测计算",
          "verified-output.txt：两组 Top-K 的通过数与失败明细",
          "评测文章：样本划分、分母约定与当前局限说明",
        ],
        takeaway:
          "增加候选改善了这组组合问题的证据覆盖，但不能补足词项规则对口语表达的理解能力。",
      },
    ],
    tags: ["Python", "词项索引", "版本过滤", "来源回查", "离线评测"],
    audience: "以客服、实施与技术支持的排障查询为设计场景",
    problem:
      "同一个错误码可能在不同产品版本下要求不同的处理方法。原型先解决一个可复查的问题：依据来自哪里，是否适用于本次版本，以及没有资料时如何结束。",
    scenario:
      "输入产品版本与错误码，在三份自编排障资料中查找适用片段，返回原文、证据 ID 和来源；版本未收录或没有词项命中时，返回无适用依据。",
    objective:
      "先把读取、检索与原文输出连成一条可运行的数据链路，用小样本与失败记录验证行为，再逐步扩展真实检索和生成服务。",
    contribution: [
      "已实现：UTF-8 文件读取、文本规范化、按段切片，保留版本、错误码、来源及片段标识，并建立内存词项索引。",
      "已实现：先按显式版本过滤，再用英文与错误码词项、中文子串基线匹配；输出实际命中原文与来源，无命中则返回明确状态。",
      "已验证：十条人工问题的开发/留出划分、Top-K 单变量对照、空结果检查与失败输入记录。",
      "后续设计：接入真实 Embedding、向量存储、模型生成与服务接口，再验证引用支持关系、会话隔离和异常反馈。",
    ],
    flow: [
      "自编 UTF-8 资料",
      "规范化与切片",
      "内存词项索引",
      "版本过滤与匹配",
      "命中原文",
      "来源与结果状态",
    ],
    flowNote:
      "当前链路为离线 Python 原型，答案直接抽取检索到的原文。没有调用真实生成模型，没有持久化向量索引，也尚未提供 FastAPI 在线接口。",
    modules: [
      {
        title: "读取、切片与证据身份",
        description:
          "build_index 实际写入并读取三份 UTF-8 演示资料，规范化后按段切分，将版本、错误码、来源与正文保存在同一条索引记录中。",
      },
      {
        title: "按版本约束的词项检索",
        description:
          "retrieve 在计算相关分数前过滤版本，英文标识与错误码采用精确词项匹配，中文采用子串基线；同分按证据 ID 排序，便于复查。",
      },
      {
        title: "原文输出与空结果状态",
        description:
          "answer 仅拼接本次命中的原文和来源 ID，证据列表随结果返回。未收录版本或无匹配资料时，返回 insufficient_evidence，不生成补充建议。",
      },
      {
        title: "固定样例与失败明细",
        description:
          "rag_evaluation 调用同一索引与检索入口，参考证据由人工预先标注；分别记录开发与留出结果，保留组合问题遗漏和口语改写失败。",
      },
    ],
    reliability: [
      {
        title: "版本约束先于相关性排序",
        description:
          "当前实现要求显式提供版本，并在匹配前过滤候选。未收录的版本不会借用其他版本资料；缺少必要输入会报参数错误。",
      },
      {
        title: "来源有效不等于生成答案正确",
        description:
          "当前结果直接来自命中原文，可以回查证据 ID 与来源。真实模型生成尚未接入，开放文本的语义支持和引用正确性还需另行验证。",
      },
      {
        title: "让小样本结论保持边界",
        description:
          "十条人工问题只用于检查当前微型语料上的机制。留出集经过观察后不能继续当作独立泛化证据；后续调规则需要补充新的问题与文档。",
      },
    ],
    stages: [
      {
        name: "离线资料到检索输出",
        status: "已验证",
        evidence:
          "三份自编资料经过文件读取、规范化、切片与词项索引，返回按版本过滤的原文、证据 ID 与来源。",
      },
      {
        name: "小样本 Top-K 对照",
        status: "已验证",
        evidence:
          "十条人工问题中，Top-K=2 开发样例通过 3/3、留出样例通过 6/7；口语改写仍未命中，保留失败记录。",
      },
      {
        name: "真实向量检索与在线接口",
        status: "待实现",
        evidence:
          "待接入真实 Embedding、Chroma 等持久化索引与 FastAPI，检查新增资料、重复导入和检索结果。",
      },
      {
        name: "真实生成与服务边界",
        status: "待实现",
        evidence:
          "待接入 LLM，验证生成引用的支持关系、会话隔离、超时反馈与端到端质量。",
      },
    ],
    acceptance: [
      "已验证：相同 E102 按 v1、v2 返回不同字段要求与对应证据 ID。",
      "已验证：未收录版本和库外词项返回空结果，缺少必要参数时拒绝调用。",
      "已验证：固定问题集可重复运行，保留通过数、分母与失败明细。",
      "待验证：真实模型生成、向量检索、在线会话与异常降级的完整链路。",
    ],
    takeaway:
      "已有成果是一个可复现的离线证据检索原型；从版本条件、来源与失败样例出发，再扩展完整 RAG 服务。",
  },
  {
    slug: "attribution-analysis",
    number: "02",
    title: "归因分析系统",
    subtitle: "电商经营分析的架构研读与改造方案",
    category: "架构研读与改造方案",
    status: "架构研读 · 待复现",
    statusDetail:
      "已获得并研读参考代码；本人尚未运行、改造或验收，不作为已完成项目成果。",
    summary:
      "面向电商退款与经营指标分析，基于参考架构设计自然语言取数和报告核查流程。用一致的指标口径解释变化，并为纠错后的 SQL 设置执行检查点。",
    deliverables: [
      {
        label: "查看改造方案",
        href: "/projects/attribution-analysis/#cases",
        description:
          "退款口径与 SQL 纠错后复验的设计推演；尚无本人运行或改造后的系统成果。",
      },
    ],
    highlights: [
      {
        title: "指标口径与报告核查",
        description:
          "围绕退款时间、状态与金额单位统一取数口径，设计 SQL、中间数据和报告数字的核对关系，让经营结论有据可查。",
      },
      {
        title: "纠错查询的执行复验",
        description:
          "针对参考代码中 SQL 纠错后直接执行的路径，设计再次校验、只读权限与查询范围约束，明确模型建议和实际执行的边界。",
      },
    ],
    cases: [
      {
        id: "refund-metric-consistency",
        label: "业务场景推演",
        title: "退款金额上涨，结论是否算对了？",
        question: "为什么本月退款金额比上月增加？",
        context:
          "基于参考架构推演退款金额环比分析，重点说明统计口径与报告核对方法，不包含实测增长原因或收益结论。",
        risk: "若申请时间与成功时间混用、退款状态不同或元与分未换算，两期金额就无法直接比较；某个渠道变化明显，也不等于已经证明它是业务根因。",
        decision:
          "先明确完整自然月还是截至当日累计，固定退款成功时间、成功状态、金额单位与可比日期区间，再按渠道或商品分别拆解。用独立汇总 SQL 对账，将查询结果和报告数字关联，另列需要核实的原因假设。",
        checks: [
          "两期采用一致的时间和状态口径；若比较退款率，另行说明分子、分母及其统计窗口。",
          "同一维度内的分组金额与整体金额分别对账，不把渠道、地域等不同维度的贡献相加。",
          "报告数字能够回查 SQL 与数据文件，明确区分观察到的变化、解释假设和分析局限。",
        ],
        evidence: [
          "指标定义、金额单位与两期日期边界",
          "参考 SQL、分组结果与整体汇总对照",
          "CSV / JSON 到报告数字的核查清单",
        ],
        takeaway:
          "先确认两期在比较同一个指标，再讨论变化集中在哪些维度，让报告解释建立在可复查的数据上。",
      },
      {
        id: "sql-correction-validation",
        label: "改造设计",
        title: "SQL 修正后，还能直接执行吗？",
        question: "模型修正了一条查询，执行前还需要检查什么？",
        context:
          "本案例依据参考代码的纠错执行路径展开，修正后复验、只读权限与查询限制属于改造设计。",
        risk: "参考代码的纠错分支会直接进入执行，原查询的 EXPLAIN 校验不能替代修正后 SQL 的检查；语法可执行也不代表权限与查询范围合适。",
        decision:
          "将新生成或修正的 SQL 重新送入校验，再交给只读账号执行；同时约束查询范围、结果数量与总耗时，为连续纠错失败设置停止条件。",
        checks: [
          "构造 SQL 错误并触发纠错，核查修正后的查询重新经过校验，而非直接进入执行。",
          "用写入语句和越界查询样例检查数据库权限与应用约束，不能只依赖 Prompt 或 EXPLAIN。",
          "对连续纠错失败和查询超时检查停止条件、失败反馈与执行记录，避免无界重试。",
        ],
        evidence: [
          "纠错前后 SQL 与校验执行轨迹",
          "只读权限及查询边界检查记录",
          "异常分支、重试次数与停止条件记录",
        ],
        takeaway:
          "模型提出查询，程序负责校验和执行；修正后的 SQL 需要重新接受同样的执行约束。",
      },
    ],
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
    flow: [
      "自然语言提问",
      "指标与元数据召回",
      "NL2SQL 取数",
      "多维拆解",
      "数据核对",
      "HTML 报告",
    ],
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
        evidence:
          "已从参考代码确认电商场景、四模块结构和取数到报告的设计；不代表本人完成开发或运行。",
      },
      {
        name: "本地部署与完整链路",
        status: "待复现",
        evidence:
          "待准备模型服务、MySQL、Redis、Elasticsearch、Qdrant 与样例数据，记录真实端到端运行结果。",
      },
      {
        name: "指标口径与查询约束",
        status: "待改造",
        evidence: "待增加可执行口径校验、纠错后复验、只读查询约束及失败处理。",
      },
      {
        name: "固定问题与报告核查",
        status: "待验收",
        evidence:
          "待保存测试问题、参考数据、SQL、计算文件和报告；暂无准确率、耗时或生产使用结论。",
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
];
