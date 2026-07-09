# 运行入口 PRD

## 模块目标

当前对外交付维护三类入口：传统开发版、Windows 绿色版和 Windows Tauri 桌面版。

传统开发版用于本机开发调试，依赖本机 Python、Node 和 npm 环境；Windows 绿色版用于发给其他 Windows 电脑直接运行，随包携带 Python、Node、npm、后端依赖和前端依赖。

Windows Tauri 桌面版用于发给其他 Windows 电脑直接双击 exe，随包携带 Python 和后端依赖，前端使用 `frontend/dist` 并由 FastAPI 静态托管，不要求目标电脑安装 Python、Node、npm、Rust 或 Cargo。

## 需求清单

| 状态 | 需求 | 说明 | 验收口径 |
| --- | --- | --- | --- |
| [已完成] | 传统开发版 | FastAPI 后端 `8000` + Vite 前端 `5174`，沿用源码目录和本机开发环境 | 开发机可双击或手动启动，浏览器访问 `http://127.0.0.1:5174/` |
| [已完成] | Windows 绿色版 | 同样采用后端 `8000` + Vite 前端 `5174` 双服务，但随包携带 Python、Node、npm、Python 依赖和 `frontend/node_modules` | 目标 Windows 电脑无需安装 Python / Node / npm，可双击 `启动造价智算.bat` 使用完整网页功能 |
| [已完成] | Windows Tauri 桌面版 | Tauri exe 启动或复用后端 `8000`，用 WebView 打开现有 React 页面；随包携带 Python、Python 依赖和 `frontend/dist` | 目标 Windows 电脑无需安装 Python / Node / npm / Rust / Cargo，可双击 `造价智算-Tauri-MVP.exe` 使用完整桌面版功能 |
| [已完成] | Tauri 桌面壳开发入口 | 作为开发调试和桌面版打包资产 | 开发机可通过 `npm run tauri:dev` 或 `启动管勘智算-Tauri-MVP.bat` 验证 |
| [已完成] | 启动、停止和状态检查 | 绿色版提供启动、停止、状态检查脚本 | 报错可读，服务窗口可见，必要时可停止已启动服务 |
| [已完成] | 大模型 Key 配置与随包 | 绿色版和 Tauri 桌面版打包时复制项目根目录现有 `.env.local`；绿色版仍提供配置脚本 | 未配置 Key 时核心 Excel / Word 流程不受影响；已随包或手动配置 Key 后，智算问答类功能可直接读取 |
| [待开发] | 本地网页版统信兼容 | 不动核心匹配引擎，优先验证 FastAPI 后端 + React 前端在统信 UOS 本地运行 | 统信环境可通过浏览器访问本机服务，完成上传、匹配、预览、下载和报告生成主流程 |
| [待开发] | 平台化服务接口规划 | 面向统一平台和数据治理 | API、权限、安全边界明确 |

## 关联资产

| 类型 | 文件 | 用途 |
| --- | --- | --- |
| 绿色版说明 | `docs/绿色版说明.md` | 绿色版运行、配置、打包和排障说明 |
| 绿色版打包 | `tools/build_green_release.py` | 生成 Windows 绿色版目录和压缩包 |
| Tauri 桌面版打包 | `tools/build_tauri_release.py` | 生成 Windows Tauri 桌面版目录和压缩包 |
| 桌面壳源码 | `src-tauri/` | Tauri 桌面壳开发和 exe 交付资产，不进入网页绿色版 |
| 桌面壳说明 | `docs/Tauri桌面壳MVP说明.md` | Tauri 开发、打包、运行和边界 |
| 桌面壳启动 | `启动管勘智算-Tauri-MVP.bat`、`tools/run_tauri.ps1` | 开发机桌面壳双击 / 命令行入口 |
| 后端入口 | `backend/app/main.py` | 健康检查和 API 服务 |
| 跨平台路径 | `backend/app/paths.py` | 统一路径定位，支撑 Windows 与 Linux / 统信本地网页版兼容 |
| 统信启动草案 | `scripts/start-linux.sh` | Linux / 统信本地网页版启动脚本草案 |
| 兼容检查 | `tools/check_platform_compat.py` | 检查明显 Windows 绝对路径、路径大小写和代码存档边界 |
| 根包配置 | `package.json` | 前端构建、绿色版构建和 Tauri 开发脚本入口 |
| 传统开发启动 | `启动管勘智算-【codex】.bat` | 本机传统开发版双击入口，历史命名暂保留兼容 |

## 功能边界

- 当前不维护旧静态评委版；网页绿色版不使用桌面壳，Tauri 桌面版作为单独 exe 交付物。
- 绿色版只解决 Windows 电脑免安装 Python / Node / npm 的网页运行问题，不重写前端和后端业务逻辑。
- Tauri 桌面壳只负责启动或复用后端并承载现有页面，不改变 React / FastAPI 主界面和业务边界。
- 绿色版和 Tauri 桌面版打包时可以携带 `.env.local`，但不得把 API Key 写死到源码或进入代码存档。
- 启动和导出脚本应避免一闪而过，错误必须可读。
- 统信兼容不得牵动核心匹配引擎、三数字规则、知识库字段、经验池规则和报告生成口径；只处理运行环境、路径、启动脚本、依赖安装和浏览器访问适配。

## 验收口径

- 传统开发版不受影响：本机仍可运行后端 `8000` 和前端 `5174`。
- 绿色版双击入口能启动后端和前端，并自动打开浏览器。
- Tauri 桌面版双击 exe 能启动后端并打开桌面窗口。
- 后端健康检查能返回当前版本。
- 绿色版可以在未安装 Python / Node / npm 的 Windows 电脑上运行。
- 绿色版覆盖上传 Excel、执行匹配、表格预览、下载 Excel、生成 Word 报告、经验池预警、工作量抓取和大模型 Key 配置读取。
- 未配置 DeepSeek API Key 时，主价格匹配、Excel 输出和 Word 报告仍可运行。
