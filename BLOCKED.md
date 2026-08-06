# 阻塞记录

- 既有文档阻塞：`python tools/check_prd_consistency.py --strict` 仍因模块08外部申报书缺失退出1；模块18硬检查为8项完成、0项缺失，普通一致性检查退出0。本任务不修改模块08既有资料缺项。
- 任务范围冲突：版本已按要求升级到 v5.19.5，但现有 `backend/tests/test_api.py::test_health_endpoint` 硬编码断言 v5.19.4；该测试文件不在本任务允许修改清单内，未改动或放宽。最终全量回归因此为 497 passed、5 skipped、1 failed（仅此断言）。若要全量绿灯，需要用户授权修改该版本断言，或明确保留后端健康接口的旧版本兼容值。
- 非代码阻塞（已切换替代验收）：`python tools/build_green_release.py --output-dir Codex-Temp/green-release-check --version 5.19.5 --date 2026-08-06 --skip-frontend-install --no-zip` 在完整运行依赖下载 / 安装阶段 124 秒超时，未生成完整包；未重试同一慢路径。已用 `--skip-wheelhouse --skip-python-libs` 完成绿色版资产携带检查，并确认 `project-default-settings.json`、`backend/app/knowledge_qa.py` 和 `RELEASE_MANIFEST.json` 随包存在；云端 UTF-8 完整发布包及 Skill 检查已通过。原因属于当前发布机依赖供应 / 网络阶段，不影响本地代码、classic 默认或 hybrid 手动验收。
