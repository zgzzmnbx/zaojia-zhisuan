import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  evidenceExperienceStatusLabel,
  evidenceToMarkdown,
  type DigitalEmployeeEvidence,
} from "../src/components/skills/digitalEmployeeEvidence.ts";

const evidence: DigitalEmployeeEvidence = {
  schema_version: 1,
  generated_at: "2026-08-13T10:00:00+08:00",
  disclaimer: "本证据包不代表生产级统一身份、组织授权或全场景准确率承诺。",
  skill: {
    id: "survey-measurement-limit-price",
    display_name: "勘察测量最高投标限价编制",
    version: "1.0.0",
    status: "active",
    status_label: "已上线",
    domain: "工程造价/勘察测量",
  },
  readiness: { status: "on_duty", label: "具备上岗证据", reason: "已上线且验证通过" },
  actions: { can_create_task: true },
  position: {
    name: "长输管道勘察测量最高投标限价编制数智员工",
    objective: "完成确定性专业处理",
    scope: ["长输管道勘察测量"],
    inputs: [".xlsx"],
    artifacts: ["Excel 成果", "Word 报告"],
    responsibilities: ["读取任务并调用可信能力"],
    human_responsibilities: ["确认异常与最终成果"],
  },
  principles: [
    { id: "onboard", title: "能上岗", conclusion: "已具备", evidence: "真实 Task 与 Skill" },
    { id: "work", title: "能干活", conclusion: "已具备", evidence: "可信 Tool 与成果" },
    { id: "grow", title: "能成长", conclusion: "受治理", evidence: "候选需人工确认" },
    { id: "boundary", title: "不越权", conclusion: "边界明确", evidence: "不猜价格" },
  ],
  relationship: [
    { id: "task", label: "Task", description: "业务目标", evidence_count: 1 },
    { id: "skill", label: "Skill", description: "冻结能力", evidence_count: 1 },
    { id: "tool", label: "Tool", description: "实际调用", evidence_count: 2 },
    { id: "artifact", label: "Artifact", description: "正式成果", evidence_count: 1 },
    { id: "experience", label: "Experience", description: "治理经验", evidence_count: 2 },
  ],
  capability_package: [{ name: "造价规则匹配 Skill", type: "shared", status: "available", description: "规则匹配" }],
  allowed_capabilities: ["三数字匹配", "Word 报告"],
  restricted_actions: ["不得由大模型直接生成最终价格或调整系数"],
  formal_validation: {
    status: "passed",
    baseline: "V3.1 正式成对验收",
    verified_at: "2026-08-13T09:44:37+08:00",
    sample: "V3.1 输入样例",
    facts: { compared_target_cells: 1254, three_number_difference_count: 0 },
    limitations: ["不代表全场景准确率承诺"],
  },
  task_evidence: {
    state: "available",
    count: 1,
    message: "已聚合 1 个真实 Task。",
    items: [
      {
        task_id: "tsk_1234567890abcdef12345678",
        task_name: "V3.1 正式回归",
        objective: "完成成果",
        source_type: "web",
        status: "completed",
        status_label: "已完成",
        stage: "artifact_generated",
        stage_label: "成果已生成",
        updated_at: "2026-08-13T09:44:37+08:00",
        skill_snapshot: { id: "survey-measurement-limit-price", version: "1.0.0", frozen: true },
        success_criteria: ["输出 Excel 和 Word"],
        human_gates: ["异常人工复核"],
        tools: ["FillEngine.match_workbook"],
        artifacts: [{ type: "excel", display_name: "控制价.xlsx", version: 3, exists: true, download_url: "/api/artifacts/1" }],
        reviews: [{ status_label: "已完成", review_round: 2, participant_statuses: { approved: 1 } }],
        experience: [
          { event_type: "cell_edit", capture_status: "captured", governance_status: "candidate", created_at: "2026-08-13" },
          { event_type: "review_opinion", capture_status: "captured", governance_status: "revoked", created_at: "2026-08-13" },
        ],
        responsibility: { registered_count: 1, roles: ["复核人"], status_counts: { completed: 1 } },
      },
    ],
  },
  experience_metrics: {
    scope_label: "当前本机可信经验运行库",
    candidate_sources: 2,
    events: { cell_edit: 1, review_opinion: 1 },
    governance: { confirmed: 0, rejected: 0, revoked: 1 },
    retrieval_hits: 0,
    version_corrections: 0,
    suspected_stale: 0,
  },
  data_sources: ["Skill Registry 与 Manifest", "Task 聚合与 TaskEvent", "V3.1 正式成对验收事实"],
  incomplete_items: ["生产级统一身份与组织授权尚未接入"],
  aggregation: { status: "complete", warnings: [] },
};

test("exports a same-source markdown evidence package with mandatory boundary fields", () => {
  const markdown = evidenceToMarkdown(evidence);

  assert.match(markdown, /生成时间：2026-08-13T10:00:00\+08:00/);
  assert.match(markdown, /Skill ID：survey-measurement-limit-price/);
  assert.match(markdown, /V3\.1 正式成对验收/);
  assert.match(markdown, /Task `tsk_1234567890abcdef12345678`/);
  assert.match(markdown, /候选经验/);
  assert.match(markdown, /已撤销/);
  assert.match(markdown, /尚未完成事项/);
  assert.match(markdown, /本证据包不代表生产级统一身份、组织授权或全场景准确率承诺/);
});

test("keeps candidate, confirmed, revoked and stale experience labels distinct", () => {
  assert.equal(evidenceExperienceStatusLabel("candidate"), "候选经验");
  assert.equal(evidenceExperienceStatusLabel("confirmed"), "已确认经验");
  assert.equal(evidenceExperienceStatusLabel("revoked"), "已撤销");
  assert.equal(evidenceExperienceStatusLabel("stale"), "疑似失效");
});

test("evidence UI keeps the formal entry, honest states and font gate", () => {
  const component = fs.readFileSync("frontend/src/components/skills/DigitalEmployeeEvidencePanel.tsx", "utf8");
  const css = fs.readFileSync("frontend/src/components/skills/DigitalEmployeeEvidencePanel.css", "utf8");

  assert.match(component, /数智员工上岗证据/);
  assert.match(component, /导出上岗证据包/);
  assert.match(component, /Task → Skill → Tool → Artifact → Experience/);
  assert.match(component, /不会伪造复核完成状态/);
  assert.match(component, /Experience 状态不混淆/);
  assert.doesNotMatch(css, /font-size:\s*(?:9|10|11)px/);
  assert.doesNotMatch(css, /var\(--dws-font-size-11\)/);
  assert.match(css, /@media \(max-width: 1024px\)/);
  assert.match(css, /prefers-reduced-motion: reduce/);
});
