# Lucas_AI · AI 工程实践

基于 AstroPaper 的中文项目作品集与博客，展示企业技术支持知识库、归因分析系统以及相关工程笔记。

网站发布地址：https://lucas-ttt.github.io/ （以 GitHub Actions 发布成功为准）。

## 日常编辑

- 写文章：src/content/posts/，复制一篇Markdown并修改标题、摘要、日期和标签。
- 修改项目名称、说明和进度：src/data/projects.ts。
- 修改首页：src/pages/index.astro。
- 修改个人介绍：src/content/pages/about.md。
- 修改站点配置：astro-paper.config.ts。
- 简历页面：src/pages/resume.astro；下载附件：public/downloads/。

文章中的“## 目录”会根据后面的标题生成可折叠目录。draft: true 为草稿，发布时改为 false。

当前两个AI业务项目按真实阶段标注；网站发布不代表业务系统已经上线。

## 自动发布

仓库 Pages 的 Source 设为 GitHub Actions。提交到 main 后，.github/workflows/deploy.yml 自动完成类型检查、静态构建、全文搜索索引与发布。

本地需要 Node.js 24 和 pnpm 11.25.0。安装依赖后，用 pnpm dev 预览，pnpm build 构建，pnpm preview 查看生产版本。

网站发布后，请分别用大陆电脑网络和手机流量检查首页、文章、目录、中文搜索与PDF下载；不能仅凭平台部署成功就推断所有线路可达。

## 联系信息与许可

用户已明确允许将手机号、邮箱及简历发布到此公开仓库。

基于 https://github.com/satnaing/astro-paper 修改，保留 LICENSE 中的原作者版权与 MIT 许可。
