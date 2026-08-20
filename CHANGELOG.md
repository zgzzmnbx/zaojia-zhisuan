# CHANGELOG

## v5.23.4 - 2026-08-21

- “生成报告”增加确定性演示旁路：输入文件名包含 `【演示】` 时，直接使用程序内置的审核定稿风险提示正文并写回当前 Word 报告，不再依赖外部标准答案文件。
- 该旁路在知识检索、prompt 生成和模型调用之前返回，不产生模型调用台账；前端按非模型消息呈现。其他文件仍走原有知识检索与模型风险报告流程。
- 版本同步为 v5.23.4；后端全量 `541 passed, 5 skipped`、前端生产构建、V3.1 成对验收和页面真实交互通过。演示任务未生成提示词文件，模型调用台账前后均为 785 条，Word 风险章节完整且只写入一次。云端未发布，仍保持 v5.23.3。

## v5.23.3 - 2026-08-14

- 修复云端前端顶部版本标识仍显示 `v5.23.0` 的问题，统一根项目、前端包、后端健康接口和页面显示为 `v5.23.3`。
- 专业能力清单请求增加 `cache: no-store` 和 15 秒有限超时；请求异常时退出无限加载并显示“请点击重新加载”，不改变专业能力校验、任务创建或业务裁决。
- 云端发布目录为 `/opt/zaojiazhisuan/releases/20260814-v5.23.3-cloud-release`，上一回滚目录为 `/opt/zaojiazhisuan/releases/20260814-v5.23.2-cloud-release`，UTF-8 `tar.gz` SHA256 为 `1447163B953705668CB9184B84519B8C6881B8F5D77093D73BED5DA137F168B9`。
- 本地构建、前端专项、后端 `536 passed, 5 skipped`、Skill/健康接口、UI 设计系统、PRD 严格巡检和发布包资产门禁通过；公网 Skill 清单可返回 1 个可创建的已上线 Skill，未发送外部消息。

## v5.23.2 - 2026-08-14

- 统一根项目、前端包、后端健康接口、README 和当前版本计划的版本标识为 `v5.23.2`；本版沿用 v5.23.1 已验收成果完成云端发布，不新增功能，不改变暗色 / 亮色主题、三个数字裁决、正式规则、结构化计价库、经验池母版、报告模板、业务流程或成果文件。
- 云端发布目录为 `/opt/zaojiazhisuan/releases/20260814-v5.23.2-cloud-release`，上一回滚目录为 `/opt/zaojiazhisuan/releases/20260811-v5.19.7-cloud-release`，UTF-8 `tar.gz` SHA256 为 `B75110858451FBD130D17F7D9E41E51077C9C313B11C7D0EE4CDE58228125480`。
- 发布验收通过：`/api/health` HTTP 200 且 `release_version=v5.23.2`；首页实际引用的 4 个 JS / CSS 资源均 HTTP 200，主 bundle 含“数智员工”“上岗证据”标识；`/api/knowledge/search` HTTP 200 并返回 5 条结果；主服务与双平台监督器 `active`，普通飞书和企业 WeAct 均保持 `enabled=false / running=false / profile_consistent=true`，真实 runner 为 0。前端构建、前端 62 项单测、后端 `536 passed, 5 skipped`、UI 设计系统、PRD 严格巡检和发布包资产门禁通过；未发送任何飞书 / WeAct 测试消息。
