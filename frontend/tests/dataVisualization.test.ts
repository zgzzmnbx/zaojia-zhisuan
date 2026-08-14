import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  retrievalChannelData,
  skillCapabilityMatrix,
  warningBulletDomain,
  warningScatterData,
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

test("accepted visualization set stays wired while VIS-06 through VIS-08 remain removed", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const visuals = await readFile(new URL("../src/components/data-visualization/ProfessionalVisuals.tsx", import.meta.url), "utf8");
  const settlement = await readFile(new URL("../src/components/settlement-audit/SettlementAuditWorkbench.tsx", import.meta.url), "utf8");
  const taskTimeline = await readFile(new URL("../src/components/task-context/TaskTimeline.tsx", import.meta.url), "utf8");
  const charts = await readFile(new URL("../src/components/project-dashboard/ProjectCharts.tsx", import.meta.url), "utf8");
  const funnel = await readFile(new URL("../src/components/project-dashboard/ProjectLifecycleFunnel.tsx", import.meta.url), "utf8");
  assert.match(taskTimeline, /VIS-01/);
  [2, 3, 4, 5, 9, 10, 11, 12, 13, 14, 15].forEach((index) => assert.match(visuals, new RegExp(`VIS-${String(index).padStart(2, "0")}`)));
  [6, 7, 8].forEach((index) => assert.doesNotMatch(visuals, new RegExp(`VIS-${String(index).padStart(2, "0")}`)));
  ["项目处理趋势", "项目状态分布", "大模型调用", "请求模型分布", "风险项目排行", "整体匹配质量", "项目来源分布"].forEach((label) => assert.match(charts, new RegExp(label)));
  assert.match(funnel, /项目处理漏斗/);
  ["ExperienceWarningVisuals", "CandidatePriceDotPlot", "WorkloadGroupedBars", "ReviewerStatusMatrix", "ReviewRoundPhaseBand", "TrustedExperienceBars", "RetrievalChannelChart"].forEach((name) => assert.match(app, new RegExp(name)));
  ["RowRiskMinimap", "SettlementWaterfall", "SheetRiskSmallMultiples"].forEach((name) => {
    assert.doesNotMatch(app, new RegExp(name));
    assert.doesNotMatch(settlement, new RegExp(name));
  });
});

test("candidate dots sit on the axis and keep the top-ranked candidate green", async () => {
  const visuals = await readFile(new URL("../src/components/data-visualization/ProfessionalVisuals.tsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../src/components/data-visualization/dataVisualization.css", import.meta.url), "utf8");
  assert.match(visuals, /recommendedId = items\[0\]\?\.id/);
  assert.match(visuals, /is-recommended/);
  assert.match(css, /\.dv-candidate-dotplot__points::before[^}]*top:\s*50%/);
  assert.match(css, /button[^}]*top:\s*50%[^}]*transform:\s*translateY\(-50%\)/);
  assert.match(css, /button\.is-recommended[^}]*background:\s*#16a34a/);
});

test("visualization CSS obeys project font-size and motion gates", async () => {
  const css = await readFile(new URL("../src/components/data-visualization/dataVisualization.css", import.meta.url), "utf8");
  assert.match(css, /--dws-font-family-ui/);
  assert.match(css, /prefers-reduced-motion/);
  assert.doesNotMatch(css, /font-size:\s*(9|10)px/);
  assert.doesNotMatch(css, /linear-gradient|radial-gradient|box-shadow/);
});

test("warning visuals use clean unified headers, light frames, blue charts, and selectable risk details", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const visuals = await readFile(new URL("../src/components/data-visualization/ProfessionalVisuals.tsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../src/components/data-visualization/dataVisualization.css", import.meta.url), "utf8");
  assert.match(visuals, /visualId="VIS-03" title="偏离率—样本数"/);
  assert.match(visuals, /visualId="VIS-04" title="当前值与经验范围"/);
  assert.doesNotMatch(visuals, /eyebrow="VIS-0[34]/);
  assert.match(visuals, /displayItems = selectedItem \? \[selectedItem\] : items/);
  assert.match(css, /dv-warning-visuals > \.dv-chart-frame[^}]*border:\s*1px solid/);
  assert.match(css, /dv-warning-point\.is-high[^}]*fill:\s*#2563eb/);
  assert.match(css, /dv-warning-point\.is-low[^}]*fill:\s*#60a5fa/);
  assert.match(app, /aria-pressed=\{isChartSelected\}/);
  assert.match(app, /setSelectedWarningKey\(warningKey\)/);
});
