# 混合 RAG 实施进度
- 目标：保留 classic 默认路径，交付可选择、可评测、可降级的 hybrid 知识问答底座。
- 基线：知识专项 61 passed（5.66s）；全量后端 489 collected，484 passed，5 skipped，95.32s；前端构建成功。
- 真源与边界：正式 Markdown/Excel/CSV、规则资产和已确认记忆是真源；索引仅为 Git 忽略缓存；hybrid 不接管填价、三个数字、经验池、工作量和报告。
- 评测：classic Recall@5 1.000、nDCG@10 0.950597、无依据误答率 0、P95 1183.850ms；hybrid 黄金/精确保护 Recall@5 均1.000、引用准确率1.000、nDCG@10 0.951188、无依据误答率0、P95 695.061ms。
- 实现：BM25、结构化、local-hash-embedding-v1（384维）、RRF、权威/数字/编码/比例尺/单位硬门控、local-rule-rerank-v1；无新增第三方依赖。
- API/UI：默认缺省 classic；响应带请求/实际模式、通道、证据状态、降级原因；前端切换、偏好、能力禁用、历史冻结和 curated_demo 已验收。
- 故障：索引损坏、向量不可用、重排超时、模型不可用均已注入；`knowledge_qa_hybrid_fault_injection_report.json` 保存红→降级→恢复全绿。
- 发布：云端 UTF-8 包与 Skill 检查通过；绿色版完整依赖构建超时，轻量资产包已验证配置/代码/Manifest随包，未混入提交。
- 最终：前端 56 passed、构建通过、Python 编译通过；后端除范围外健康版本断言外 497 passed、5 skipped，完整统计 497 passed、5 skipped、1 failed；普通 PRD 巡检退出0，strict 仅保留模块08既有缺项；trim_changelog、暂存审计和本地 Git 提交已完成，不推送。
