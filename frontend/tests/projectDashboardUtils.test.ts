import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  activeProjectFilterCount,
  artifactSummary,
  chartLayoutForWidth,
  clearFilterChip,
  datePresetForRange,
  dateRangeForPreset,
  defaultProjectFilters,
  EMPTY_FILTERS,
  filterChips,
  projectQuery,
  qualityPercentages,
  type DashboardPayload,
  type ProjectArtifact,
} from "../src/components/project-dashboard/projectDashboardUtils.ts";

test("date presets use inclusive local calendar ranges", () => {
  const today = new Date(2026, 6, 24, 18, 30);
  assert.deepEqual(dateRangeForPreset("7d", today), {
    dateFrom: "2026-07-18",
    dateTo: "2026-07-24",
  });
  assert.deepEqual(dateRangeForPreset("month", today), {
    dateFrom: "2026-07-01",
    dateTo: "2026-07-24",
  });
  assert.deepEqual(dateRangeForPreset("all", today), { dateFrom: "", dateTo: "" });
  assert.equal(datePresetForRange("2026-06-25", "2026-07-24", today), "30d");
  assert.equal(datePresetForRange("2026-07-01", "2026-07-22", today), "custom");
  assert.deepEqual(defaultProjectFilters(today), {
    ...EMPTY_FILTERS,
    dateFrom: "2026-06-25",
    dateTo: "2026-07-24",
  });
});

test("filter button counts only non-default conditions", () => {
  const today = new Date(2026, 6, 24, 18, 30);
  const defaults = defaultProjectFilters(today);
  assert.equal(activeProjectFilterCount(defaults, today), 0);
  assert.equal(activeProjectFilterCount({
    ...defaults,
    compare: true,
    status: "completed",
    lifecycleStage: "reported",
  }, today), 3);
  assert.equal(activeProjectFilterCount({
    ...defaults,
    dateFrom: "2026-07-01",
    dateTo: "2026-07-24",
  }, today), 1);
});

test("dashboard and history share one encoded query contract", () => {
  const query = projectQuery({
    ...EMPTY_FILTERS,
    keyword: "西气东输 二线",
    status: "pending_review",
    quality: "review",
    lifecycleStage: "reported",
    compare: true,
  }, { page: 2, page_size: 20 });
  const params = new URLSearchParams(query);
  assert.equal(params.get("keyword"), "西气东输 二线");
  assert.equal(params.get("status"), "pending_review");
  assert.equal(params.get("quality"), "review");
  assert.equal(params.get("lifecycle_stage"), "reported");
  assert.equal(params.get("compare"), "true");
  assert.equal(params.get("page"), "2");
  assert.equal(params.has("risk"), false);
});

test("matching quality percentages remain stable and sum to 100", () => {
  assert.deepEqual(qualityPercentages({
    standard_hit_rows: 77,
    experience_hint_rows: 13,
    review_rows: 10,
    total_rows: 100,
  }), { standard: 77, experience: 13, review: 10 });
  assert.deepEqual(qualityPercentages({
    standard_hit_rows: 0,
    experience_hint_rows: 0,
    review_rows: 0,
    total_rows: 0,
  }), { standard: 0, experience: 0, review: 0 });
});

test("filter chips translate labels and clear only the selected dimension", () => {
  const dashboard = {
    filter_options: {
      skills: [],
      sources: [{ value: "web", label: "网页填价" }],
      statuses: [{ value: "completed", label: "已完成" }],
      lifecycle_stages: [{ value: "reported", label: "生成报告" }],
    },
  } as DashboardPayload;
  const filters = {
    ...EMPTY_FILTERS,
    status: "completed",
    sourceType: "web",
    dateFrom: "2026-07-01",
    dateTo: "2026-07-24",
    lifecycleStage: "reported",
  };
  assert.deepEqual(filterChips(filters, dashboard).map((item) => item.label), [
    "时间 2026-07-01 — 2026-07-24",
    "状态 已完成",
    "来源 网页填价",
    "阶段 生成报告",
  ]);
  assert.deepEqual(clearFilterChip(filters, "date"), {
    ...filters,
    dateFrom: "",
    dateTo: "",
  });
  assert.equal(clearFilterChip(filters, "status").sourceType, "web");
});

test("artifact summary keeps the latest server-ordered artifact per type", () => {
  const artifacts = [
    { artifact_id: "new", type: "excel", version: 2 },
    { artifact_id: "old", type: "excel", version: 1 },
    { artifact_id: "word", type: "word", version: 1 },
  ] as ProjectArtifact[];
  const summary = artifactSummary(artifacts);
  assert.equal(summary.get("excel")?.artifact_id, "new");
  assert.equal(summary.get("word")?.artifact_id, "word");
});

test("chart layout covers Dock and wide-screen breakpoints", () => {
  assert.equal(chartLayoutForWidth(520), "single");
  assert.equal(chartLayoutForWidth(900), "double");
  assert.equal(chartLayoutForWidth(1440), "wide");
});

test("dashboard stylesheet keeps the component theme under local scope", async () => {
  const css = await readFile(
    new URL("../src/components/project-dashboard/projectDashboard.css", import.meta.url),
    "utf8",
  );
  assert.match(css, /^\.project-dashboard\s*\{/m);
  assert.doesNotMatch(css, /(^|})\s*:root\s*\{/m);
  assert.doesNotMatch(css, /(^|})\s*(html|body)\s*\{/m);
  assert.doesNotMatch(css, /@tailwind|shadcn\/init|--background:/);
  assert.match(css, /\.project-dashboard__analysis\.is-llm-trend/);
  assert.match(css, /\.project-dashboard__analysis\.is-llm-models/);
  assert.match(css, /\.project-dashboard__filter-dialog/);
  assert.match(css, /\.project-dashboard\.is-presentation/);
  assert.match(css, /\.project-dashboard__lifecycle/);
});

test("dashboard silently preloads code and data five seconds after entering the app", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const dashboard = await readFile(
    new URL("../src/components/project-dashboard/ProjectDashboard.tsx", import.meta.url),
    "utf8",
  );
  assert.match(app, /PROJECT_DASHBOARD_PRELOAD_DELAY_MS = 5_000/);
  assert.match(app, /isWelcomeScreenVisible \|\| hasOpenedProjectDashboard/);
  assert.match(app, /setTimeout\(\(\) => \{\s*setHasOpenedProjectDashboard\(true\);\s*\}, PROJECT_DASHBOARD_PRELOAD_DELAY_MS\)/);
  assert.match(app, /hidden=\{activeDaweibaModule !== "fill" \|\| fillWorkspaceView !== "dashboard"\}/);
  assert.match(dashboard, /setTimeout\(\(\) => void load\(controller\.signal\), 120\)/);
  assert.doesNotMatch(dashboard, /if \(!active\) return undefined;[\s\S]{0,200}load\(/);
});

test("project lifecycle funnel exposes cumulative stages as keyboard buttons", async () => {
  const component = await readFile(
    new URL("../src/components/project-dashboard/ProjectLifecycleFunnel.tsx", import.meta.url),
    "utf8",
  );
  assert.match(component, /项目处理漏斗/);
  assert.match(component, /aria-pressed/);
  assert.match(component, /conversion_rate/);
  assert.match(component, /drop_off/);
  assert.match(component, /project-dashboard__lifecycle-connector/);
  assert.doesNotMatch(component, /ArrowRight/);
});

test("project lifecycle funnel is vertical and rendered after analysis charts", async () => {
  const css = await readFile(
    new URL("../src/components/project-dashboard/projectDashboard.css", import.meta.url),
    "utf8",
  );
  const dashboard = await readFile(
    new URL("../src/components/project-dashboard/ProjectDashboard.tsx", import.meta.url),
    "utf8",
  );
  assert.match(css, /\.project-dashboard__lifecycle ol\s*\{[^}]*flex-direction:\s*column/s);
  assert.match(css, /--lifecycle-width:\s*calc\(100% - \(var\(--lifecycle-step\) \* 6%\)\)/);
  assert.ok(
    dashboard.indexOf("<ProjectCharts") < dashboard.indexOf("<ProjectLifecycleFunnel"),
    "lifecycle funnel should appear after the dashboard analysis charts",
  );
  assert.match(dashboard, /lifecycle=\{\(/);
  assert.match(css, /\.project-dashboard__charts\.has-source-chart > \.project-dashboard__lifecycle/);
});

test("fill workbench status panel exposes a real state-driven progress indicator", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(app, /const FILL_WORKFLOW_STEPS/);
  assert.match(app, /warningSummary\?\.executed/);
  assert.match(app, /role="progressbar"/);
  assert.match(app, /aria-current=\{isCurrent \? "step"/);
  assert.match(css, /\.daweiba-fill-workflow-progress__track/);
  assert.match(css, /\.daweiba-fill-insight-panel\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/s);
  assert.match(css, /\.daweiba-fill-workflow-progress\s*\{[^}]*grid-column:\s*1\s*\/\s*-1;[^}]*grid-row:\s*3/s);
  assert.match(css, /\.daweiba-fill-workflow-progress ol\s*\{[^}]*grid-template-columns:\s*repeat\(5,\s*minmax\(0,\s*1fr\)\)/s);
  assert.match(css, /\.daweiba-fill-workflow-progress__track\s*\{[^}]*height:\s*2px;[^}]*background:\s*#eef2f7;/s);
  assert.match(css, /\.daweiba-fill-workflow-progress__track > span\s*\{[^}]*background:\s*#bfd4f8;/s);
  assert.match(css, /\.daweiba-fill-overview-row,[^}]*\.daweiba-fill-status-card\s*\{[^}]*grid-column:\s*1\s*\/\s*-1;[^}]*grid-row:\s*2/s);
  assert.match(css, /\.daweiba-fill-insight-panel\s*\{[^}]*grid-template-rows:\s*auto\s+auto\s+auto\s+minmax\(0,\s*1fr\)\s*!important;[^}]*align-content:\s*stretch/s);
  assert.match(css, /\.daweiba-fill-system-grid,[^}]*\.daweiba-fill-mini-grid\s*\{[^}]*height:\s*100%/s);
  assert.match(app, /style=\{\{\s*width:\s*`\$\{fillWorkflowProgress\}%`\s*\}\}/);
});

test("fill workbench opens column mapping from a zero-footprint action button", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(app, /className=\{`ghost-button mapping-action-button/);
  assert.match(app, /file && isMappingOpen/);
  assert.match(app, /role="dialog"/);
  assert.match(app, /aria-modal="true"/);
  assert.match(app, /className="mapping-dialog-backdrop"/);
  assert.match(app, /aria-label="关闭列映射设置"/);
  assert.match(app, /setIsMappingOpen\(false\);\s*setIsInputFieldSettingsOpen\(true\)/);
  assert.match(app, /modal-backdrop input-field-settings-backdrop/);
  assert.match(css, /#daweiba-input > \.mapping-panel\s*\{[^}]*position:\s*fixed/s);
  assert.match(css, /\.input-field-settings-backdrop\s*\{[^}]*z-index:\s*220/s);
  assert.match(css, /\.action-row\.has-mapping-action\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/s);
  assert.doesNotMatch(app, /data-ui-text-key="button\.pick-file"/);
  assert.doesNotMatch(app, />\s*\{uiText\("button\.pick-file",\s*"选文件"\)\}\s*</s);
});

test("fill workbench reserves more height for the complete status panel", async () => {
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /grid-template-rows:\s*minmax\(0,\s*0\.48fr\)\s*minmax\(0,\s*0\.52fr\)/);
  assert.match(css, /\.is-daweiba-module-fill \.drop-zone\s*\{[^}]*min-height:\s*clamp\(144px,\s*17vh,\s*174px\)/s);
  assert.match(css, /\.is-daweiba-module-fill \.drop-zone\.has-file\s*\{[^}]*min-height:\s*144px/s);
  assert.match(css, /\.daweiba-fill-insight-panel\s*\{[^}]*gap:\s*10px\s*!important/s);
});

test("project ledger name uses progressive disclosure after file selection", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(app, /const \[isProjectNameEditorOpen,\s*setIsProjectNameEditorOpen\]/);
  assert.match(app, /file && \(\s*<div className=\{`project-name-disclosure/s);
  assert.match(app, /isProjectNameEditorOpen && \(\s*<label className="daweiba-project-name-field"/s);
  assert.match(app, /仅用于项目看板和历史台账，不影响填价计算/);
  assert.match(css, /\.project-name-disclosure__trigger\s*\{[^}]*min-height:\s*28px/s);
});

test("dashboard model telemetry uses a smooth area wave and a donut chart", async () => {
  const component = await readFile(
    new URL("../src/components/project-dashboard/ProjectCharts.tsx", import.meta.url),
    "utf8",
  );
  assert.match(component, /<AreaChart/);
  assert.match(component, /type="monotone"/);
  assert.match(component, /id="projectDashboardLlmWave"/);
  assert.match(component, /请求模型种类环形图/);
  assert.match(component, /项目来源分布/);
});
