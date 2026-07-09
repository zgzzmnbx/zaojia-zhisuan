# 统信 UOS 兼容性开发说明

## 定位

本说明用于后续把“造价智算”迁移到 Linux / 统信 UOS 环境时减少返工。本轮目标是兼容性准备，不是立即完成统信安装包或 deb 包打包。

当前 Windows 主线不迁移：现有传统开发版和 Windows 绿色版继续保留。统信方向优先验证“本地网页版”，也就是 Python FastAPI 后端 + React 前端服务或构建产物配合后端运行。

## 本轮边界

- 不重构核心匹配引擎。
- 不改变 `基价 / 单价`、`实物工作费调整系数`、`技术工作费调整系数` 的裁决逻辑。
- 不让大模型参与最终价格或系数裁决。
- 不移动真实知识库、规则表、经验池模板、测试样例。
- 不删除或替换现有 Windows 启动器。
- 不强行完成 Linux / deb 打包。

## 优先验证路径

统信兼容性第一阶段建议只验证本地网页版：

```bash
cd /path/to/project
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd frontend
npm install
npm run build
cd ..
export GUANKAN_FRONTEND_DIR="$PWD/frontend/dist"
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

也可以使用预留草案脚本：

```bash
bash scripts/start-linux.sh
```

打开：

```text
http://127.0.0.1:8000/
```

## 兼容性重点

后续统信迁移重点关注以下问题：

- 路径：业务代码优先使用 `pathlib.Path` 和项目根目录相对路径，不写死 `C:\`、`D:\`。
- 权限：运行输出写入 `Codex-Temp/runtime/`，不要要求写入系统目录。
- 大小写：前端相对 import 必须和真实文件名大小写一致。
- 环境变量：大模型 Key 优先读进程环境变量，也允许本地 `.env.local`；`.env.local` 不进入代码存档或正式输出包。
- 运行目录：后端、脚本、打包流程应能从项目根目录推导关键路径。
- 中文文件名：知识库、规则表、模板仍保留中文文件名；统信环境需要确认文件系统、终端和 Python 运行时均使用 UTF-8。
- 依赖安装：Python 依赖按 `backend/requirements.txt` 安装；前端按 `frontend/package.json` 安装。
- 启动脚本：Windows `.bat` 保留；Linux / 统信使用 `scripts/start-linux.sh` 或文档命令。
- 输出文件：Excel / Word 输出仍写入运行时任务目录，不覆盖原始输入。

## 检查命令

每次做兼容性准备或路径相关修改后运行：

```bash
python tools/check_platform_compat.py
```

该脚本检查：

- Python / TypeScript / Rust / 脚本文件中的明显 Windows 绝对路径。
- 后端业务代码中的 `os.startfile`、`win32`、`powershell`、`cmd.exe` 等 Windows 专属调用。
- 前端相对 import 的大小写和缺失目标。
- 关键目录和文件是否能通过项目根目录相对路径定位。
- `.env.local` 是否被 `.gitignore` 和代码存档脚本排除。

已知 Windows 主线文件会作为 `WARN` 输出，不阻断检查；新的跨平台风险会作为 `FAIL` 输出并返回非零退出码。

当前不上统信时，本检查不作为日常开发默认步骤，不挂入 Windows 启动器、前端构建、后端测试、代码存档或绿色版流程。只有涉及统信 / Linux、路径、权限、启动脚本、打包规则和输出目录兼容性时再手动运行，避免拖慢平时开发节奏。

## Linux 安装包后续阶段

Linux / deb 打包放在后续阶段处理。进入该阶段前至少需要确认：

- 统信目标机是否具备 Node.js 和 Python 运行环境，或是否需要随包携带运行时。
- 是否需要 Linux 专属图标、权限和桌面文件。
- 当前 Windows 绿色版启动逻辑是否需要抽象为跨平台启动层。
- Windows 绿色版资源和 Linux 发布资源是否分开维护。

本轮不把上述内容作为完成项，只保留路线和检查口径。
