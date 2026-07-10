# 造价智算 Tauri 桌面壳 MVP 说明

## 定位

Tauri 是开发调试和 Windows 桌面 exe 交付入口；它不替代传统网页绿色版，两者并行维护。当前 MVP 只负责：

- 启动或复用本机 `127.0.0.1:8000` 造价智算 FastAPI 后端。
- 等待 `/api/health` 确认服务身份。
- 在 Tauri WebView 窗口中打开现有 React 页面。
- 关闭窗口时结束本次由 Tauri 拉起的后端进程。

React 前端、FastAPI 后端、Excel / Word / 经验池 / 工作量抓取业务逻辑不在 Tauri 壳里重写。

## 目录

```text
package.json
src-tauri/
tools/build_tauri_release.py
docs/Tauri桌面壳MVP说明.md
```

`src-tauri/` 放在项目根目录，便于同时访问 `backend/`、`frontend/` 和绿色版运行目录结构。

## 开发运行

当前机器需要安装 Rust / Cargo、Visual Studio Build Tools C++ 生成工具和 WebView2 运行环境。项目根目录执行：

```powershell
npm install
npm run tauri:dev
```

`npm run tauri:dev` 会先构建 `frontend/dist`，再启动 Tauri。Tauri 启动后会：

1. 检查 `http://127.0.0.1:8000/api/health`。
2. 如果已有造价智算后端，直接复用。
3. 如果端口空闲，从当前项目根目录启动：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
```

4. 将前端静态目录传给后端：

```text
GUANKAN_FRONTEND_DIR=frontend/dist
```

5. 健康检查通过后打开 Tauri 主窗口。

`frontend/public/file-viewer` 会在 Vite 构建时进入 `frontend/dist/file-viewer`。Tauri 中的 Word 报告预览通过 FastAPI 同源读取当前 DOCX、`docx.worker.js` 和 `jszip.min.js`，不依赖公网、CDN 或在线 Office。

Tauri 窗口创建时已关闭默认文件拖放接管，使 WebView2 能把外部 `.xlsx` 文件继续交给页面里的 HTML5 拖拽上传区。主价格匹配、经验池导入和原始工作量抓取的拖入文件交互仍由现有 React 页面处理。

## Windows 编译环境

如果 `npm run tauri:dev` 或双击 `启动管勘智算-Tauri-MVP.bat` 提示 `cargo` 不可用，先安装 Rust：

```powershell
winget install Rustlang.Rustup
```

如果提示 `link.exe is not available`，安装 Visual Studio Build Tools 的 C++ 生成工具：

```powershell
winget install Microsoft.VisualStudio.2022.BuildTools --override "--wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

安装完成后重新打开 PowerShell，或重新双击 `启动管勘智算-Tauri-MVP.bat`。

本项目已在 `src-tauri/.cargo/config.toml` 中放入项目级 Cargo 网络配置：

- 使用 `rsproxy.cn` sparse 镜像源，避免 crates.io 下载超时。
- 放宽 Cargo HTTP 超时和低速限制。
- 关闭 Windows schannel 的证书吊销在线检查，解决 `CRYPT_E_REVOCATION_OFFLINE`。

该配置只影响 `src-tauri/` 子项目，不修改全局 Cargo 配置。

当前 MVP 先使用 `src-tauri/icons/icon.ico` 中的最小占位图标，后续产品化阶段再替换为正式品牌图标。

编译成功后，开发构建产物位于：

```text
src-tauri/target/release/guankanzhisuan-desktop.exe
```

## 桌面版打包

生成 Windows Tauri 桌面版目录和 zip：

```powershell
python tools/build_tauri_release.py --date 2026-07-09 --skip-frontend-install --skip-npm-install
```

输出目录形如：

```text
04-输出版本存档/造价智算-Tauri桌面版-YYYY-MM-DD-vX.X.X
```

目标 Windows 电脑可直接双击：

```text
造价智算-Tauri-MVP.exe
```

或双击：

```text
启动造价智算-Tauri桌面版.bat
```

异常退出后如需清理后端，可双击：

```text
停止造价智算-Tauri桌面版.bat
```

该目录不携带 `runtime/node/`、`frontend/node_modules/` 和 Rust / Cargo；前端使用 `frontend/dist`，由本地 FastAPI 后端托管。

如果项目根目录存在 `.env.local`，打包脚本会复制到 Tauri 桌面版目录；问问智算会读取其中的大模型 Key。`.env.local` 仍不写入源码。

## 绿色版兼容边界

Tauri 壳的后端启动逻辑兼容绿色版目录，但当前 Windows 绿色版不依赖 Tauri：

- 若应用根目录存在 `runtime/python/python.exe`，优先使用该便携 Python。
- 若存在 `runtime/python-libs`，自动加入 `PYTHONPATH`。
- 若存在 `frontend/dist/index.html`，可作为前端静态目录。
- `frontend/dist/file-viewer/vendor/docx/` 必须包含真实的 `docx.worker.js` 与 `jszip.min.js`；静态请求不得 404，也不得回落为 `index.html`。
- 若存在 `.env.local`，后端仍按现有启动链路读取环境变量。

因此桌面壳复用绿色版目录的后端、运行时和规则资产；传统 Windows 绿色版仍按 `启动造价智算.bat` 启动后端 `8000` 和 Vite 前端 `5174`，Tauri 桌面版则由 exe 启动后端并打开 WebView。

生成 Tauri MVP 开发/验证目录的入口为：

```powershell
python tools/build_tauri_release.py --date 2026-07-09 --skip-frontend-install
```

该脚本会先生成绿色版阶段目录，再执行 Tauri release 构建，并把 Tauri exe、启动 bat、停止 bat 和停止 ps1 放入同一目录。日常网页绿色版打包仍使用 `python tools/build_green_release.py`。

## 日志与运行目录

Tauri 壳本身只写后端启动日志：

```text
.runtime/logs/tauri-backend.log
.runtime/logs/tauri-backend-error.log
```

业务运行输出、上传缓存、处理状态仍由后端写入现有目录：

```text
Codex-Temp/runtime/
```

## 端口与清理

- 固定使用 `127.0.0.1:8000`。
- 如果端口被非造价智算服务占用，Tauri 会停止启动并提示关闭占用进程。
- 如果端口已有造价智算后端，Tauri 复用该服务，关闭窗口时不会结束外部已有服务。
- 如果后端由 Tauri 本次启动，关闭 Tauri 主窗口时会结束该后端进程。

## 边界

本次 MVP 不包含：

- 安装包图标与品牌化安装向导。
- 代码签名。
- 自动更新。
- 系统托盘常驻。
- 内置 API Key 设置页。
- 日志面板。
- 端口切换 UI。
- 完整 sidecar/资源内嵌产品化方案。

这些能力建议在 MVP 稳定后作为桌面产品化阶段继续做。


