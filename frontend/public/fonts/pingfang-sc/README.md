# 苹方界面字体

本目录保存造价智算前端同源自托管的简体苹方 WOFF2 字体，用于保证浏览器、Windows 绿色版、Tauri、macOS 与 Linux / UOS 的界面字体一致。

## 字重映射

| 前端文件 | 原始字体 | CSS 字重 | 用途 |
| --- | --- | --- | --- |
| `pingfang-sc-regular.woff2` | 苹方黑体-准-简 | `400` | 正文、表格、辅助说明 |
| `pingfang-sc-medium.woff2` | 苹方黑体-中粗-简（字体内部标识 `Medium`） | `500` | 导航、标签、中等强调 |
| `pingfang-sc-semibold.woff2` | 苹方黑体-中黑-简（字体内部标识 `Semibold`） | `600`、`700` | 标题、按钮、表头、强数字 |

字体以 `Zaojia PingFang SC` 作为项目内 CSS 别名，通过 `frontend/src/styles.css` 的 `@font-face` 加载。代码、日志和技术字段仍使用原有等宽字体；Word 报告字体由实际 DOCX 模板决定。
