import { defineAstroPaperConfig } from "./src/types/config";
export default defineAstroPaperConfig({
  site: {
    url: "https://lucas-ttt.github.io/",
    title: "Lucas_AI",
    description: "Lucas_AI 的项目作品集与工程笔记，聚焦 RAG 知识服务、Agent 与电商经营分析。",
    author: "Lucas_AI",
    profile: "https://lucas-ttt.github.io/about/",
    ogImage: "social-card.svg",
    lang: "zh-CN", timezone: "Asia/Shanghai", dir: "ltr",
  },
  posts: { perPage: 8, perIndex: 3 },
  features: { lightAndDarkMode: true, dynamicOgImage: false, showArchives: true, showBackButton: true, editPost: { enabled: false }, search: "pagefind" },
  socials: [{ name: "mail", url: "mailto:J1666830991@gmail.com" }],
  shareLinks: [],
});
