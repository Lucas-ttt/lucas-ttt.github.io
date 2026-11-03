# Lucas_AI · AI 工程实践

基于 AstroPaper 的中文项目作品集与博客，展示企业技术支持知识库、归因分析系统以及相关工程笔记。

网站地址：https://lucas-ttt.github.io/ 。展示名为 Lucas_AI。

## 日常编辑

- 写文章：src/content/posts/，复制一篇Markdown并修改标题、摘要、日期和标签。
- 系列文章：series 指定系列名，seriesOrder 指定阅读序号，noteType 可用代码实操、实践记录、设计笔记、架构分析与开源研读；日期填写真实整理时间，更新时填写 modDatetime。
- 修改项目名称、顺序与设计说明：src/data/projects.ts。当前归因分析第一、企业知识库第二。
- 修改亮点：每个项目的 highlights；修改案例：cases。案例包含用户问题、风险、设计选择、验证项和材料说明，会同步出现在首页与项目页。
- 修改首页：src/pages/index.astro。
- 修改个人介绍：src/content/pages/about.md。
- 修改站点配置：astro-paper.config.ts。
- 简历页面：src/pages/resume.astro；下载附件：public/downloads/。

文章中的“## 目录”会根据后面的标题生成可折叠目录。draft: true 为草稿，发布时改为 false。

工程笔记目前为10篇“AI Agent 代码实操”，每篇包含完整Python代码、执行命令、实际输出、改错实验及原文入口。文章页按seriesOrder展示，首页精选由featured控制；原始日期仍用于订阅和结构化元信息。中文阅读入口涵盖牛客、博客园，示例为独立编写的演练，不收录未授权博客全文。

下载包在public/examples/agent-lab.zip，源文件及运行记录在public/examples/agent-lab/。修改脚本时需要同步文章代码块，并实际重跑后更新verification.json和verified-output.txt；不能只改显示输出。标准库示例、LangGraph和MCP已执行验证，真实外部模型--live模式需使用自己的服务配置另行验证。

archiveDatetime 是自定义归档日期，用于文章列表及归档页编排。pubDatetime 和 modDatetime 保留实际发布/整理与更新记录，供正文、订阅和结构化信息使用。自定义日期不代表文章当时已经发表。

项目采用案例形式呈现业务问题、架构、可靠性设计与验证方法；参考架构、方案和实际实现范围分别说明。

不在电脑上启动开发环境时，也可以在 GitHub 打开相应文件，点击编辑后提交到 main。发布进度可在 Actions 中查看，绿色成功后刷新网站。上传 PDF 时同时更新公开 Markdown，保持两份内容一致。

## 自动发布

仓库 Pages 的 Source 设为 GitHub Actions。提交到 main 后，.github/workflows/deploy.yml 自动完成类型检查、静态构建、全文搜索索引与发布。

本地需要 Node.js 24 和 pnpm 11.25.0。安装依赖后，用 pnpm dev 预览，pnpm build 构建，pnpm preview 查看生产版本。

网站发布后，请分别用大陆电脑网络和手机流量检查首页、文章、目录、中文搜索与PDF下载；不能仅凭平台部署成功就推断所有线路可达。

## 联系信息与许可

简历下载文件为公开正文，维护附录不进入网站附件。

基于 https://github.com/satnaing/astro-paper 修改，保留 LICENSE 中的原作者版权与 MIT 许可。
