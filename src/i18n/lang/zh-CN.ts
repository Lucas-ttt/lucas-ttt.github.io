import type { UIStrings } from "../types";

export default {
  nav: {
    home: "首页",
    posts: "文章",
    tags: "主题",
    about: "关于",
    archives: "归档",
    search: "搜索",
  },
  post: {
    publishedAt: "发布于",
    updatedAt: "更新于",
    sharePostIntro: "分享文章：",
    sharePostOn: "分享到 {{platform}}",
    sharePostViaEmail: "通过邮件分享",
    tagLabel: "主题",
    backToTop: "返回顶部",
    goBack: "返回",
    editPage: "编辑页面",
    previousPost: "上一篇",
    nextPost: "下一篇",
  },
  pagination: {
    prev: "上一页",
    next: "下一页",
    page: "页",
  },
  home: {
    socialLinks: "联系入口",
    featured: "精选文章",
    recentPosts: "最新文章",
    allPosts: "全部文章",
  },
  footer: {
    copyright: "版权所有",
    allRightsReserved: "保留所有权利。",
  },
  pages: {
    tagTitle: "主题",
    tagDesc: "该主题下的文章",

    tagsTitle: "主题",
    tagsDesc: "按主题浏览工程笔记。",

    postsTitle: "文章",
    postsDesc: "记录实现过程、技术取舍与验证方法。",

    archivesTitle: "归档",
    archivesDesc: "按时间浏览所有文章。",

    searchTitle: "搜索",
    searchDesc: "搜索文章、项目主题与关键技术。",
  },
  a11y: {
    skipToContent: "跳转到正文",
    openMenu: "展开导航",
    closeMenu: "收起导航",
    toggleTheme: "切换深浅色",
    searchPlaceholder: "搜索文章…",
    noResults: "未找到相关内容",
    goToPreviousPage: "上一页",
    goToNextPage: "下一页",
  },
  notFound: {
    title: "404 页面不存在",
    message: "没有找到这个页面",
    goHome: "返回首页",
  },
} satisfies UIStrings;
