import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  aggregateSheetRisks,
  retrievalChannelData,
  skillCapabilityMatrix,
  warningBulletDomain,
  warningScatterData,
  waterfallEquation,
} from "../src/components/data-visualization/visualizationUtils.ts";

test("warning charts keep absolute deviation and auto-extend beyond the experience range", () => {
  const item = {
    sheet_name: "表2",
    excel_row: 8,
    metric: "基价",
    current_value: 160,
    experience_average: 100,
    experience_min: 90,
    experience_max: 110,
    sample_count: 6,
    deviation_percent: -60,
    severity: "high",
  };
  assert.deepEqual(warningScatterData([item]).map(({ x, y }) => ({ x, y })), [{ x: 6, y: 60 }]);
  const [min, max] = warningBulletDomain(item);
  assert.ok(min < 90);
  assert.ok(max > 160);
});

test("settlement sheet risks share honest counts and waterfall supports both directions", () => {
  assert.deepEqual(aggregateSheetRisks([
    { sheet: "表2", severity: "high" },
    { sheet: "表2", severity: "low" },
    { sheet: "表3", severity: "medium" },
  ]), [
    { sheet: "表2", high: 1, medium: 0, low: 1, total: 2 },
    { sheet: "表3", high: 0, medium: 1, low: 0, total: 1 },
  ]);
  assert.deepEqual(waterfallEquation(120, 100), { reported: 120, reviewed: 100, difference: 20, direction: "reduction", valid: true });
  assert.equal(waterfallEquation(100, 120).direction, "increase");
  assert.equal(waterfallEquation(100, 120).valid, true);
});

test("hybrid retrieval remains parallel channels instead of a fabricated funnel", () => {
  assert.deepEqual(retrievalChannelData({ channels: { bm25: { count: 8 }, structured: [1, 2], vector: 5, fusion: { result_count: 4 }, rerank: { hits: 3 } } }), [
    { key: "bm25", label: "BM25", count: 8 },
    { key: "structured", label: "结构化", count: 2 },
    { key: "vector", label: "向量", count: 5 },
    { key: "fusion", label: "融合", count: 4 },
    { key: "rerank", label: "重排", count: 3 },
  ]);
});

test("Skill matrix hides test Skills and never upgrades undeclared capabilities", () => {
  const rows = skillCapabilityMatrix([
    { id: "survey", display_name: "勘察测量", status: "active", capabilities: ["excel_input", "price_matching", "report"], can_create_task: true },
    { id: "future", display_name: "未来能力", status: "planned", capabilities: ["risk"], can_create_task: false },
    { id: "test-skill", display_name: "测试", status: "active", capabilities: ["risk"], can_create_task: true },
  ]);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].cells[0], "available");
  assert.equal(rows[0].cells[2], "unsupported");
  assert.equal(rows[1].cells[2], "planned");
});

test("VIS-01 through VIS-15 are wired while the dashboard baseline stays additive", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const visuals = await readFile(new URL("../src/components/data-visualization/ProfessionalVisuals.tsx", import.meta.url), "utf8");
  const taskTimeline = await readFile(new URL("../src/components/task-context/TaskTimeline.tsx", import.meta.url), "utf8");
  const charts = await readFile(new URL("../src/components/project-dashboard/ProjectCharts.tsx", import.meta.url), "utf8");
  const funnel = await readFile(new URL("../src/components/project-dashboard/ProjectLifecycleFunnel.tsx", import.meta.url), "utf8");
  assert.match(taskTimeline, /VIS-01/);
  for (let index = 2; index <= 15; index += 1) assert.match(visuals, new RegExp(`VIS-${String(index).padStart(2, "0")}`));
  ["项目处理趋势", "项目状态分布", "大模型调用", "请求模型分布", "风险项目排行", "整体匹配质量", "项目来源分布"].forEach((label) => assert.match(charts, new RegExp(label)));
  assert.match(funnel, /项目处理漏斗/);
  ["ExperienceWarningVisuals", "CandidatePriceDotPlot", "RowRiskMinimap", "WorkloadGroupedBars", "ReviewerStatusMatrix", "ReviewRoundPhaseBand", "TrustedExperienceBars", "RetrievalChannelChart"].forEach((name) => assert.match(app, new RegExp(name)));
});

test("visualization CSS obeys project font-size and motion gates", async () => {
  const css = await readFile(new URL("../src/components/data-visualization/dataVisualization.css", import.meta.url), "utf8");
  assert.match(css, /--dws-font-family-ui/);
  assert.match(css, /prefers-reduced-motion/);
  assert.doesNotMatch(css, /font-size:\s*(9|10)px/);
  assert.doesNotMatch(css, /linear-gradient|radial-gradient|box-shadow/);
});
