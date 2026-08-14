import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  filmstripStageIndexes,
  relayActiveIndex,
  relayStageState,
  statusWorkflowProgress,
  type StatusWorkflowSnapshot,
} from "../src/components/status-panel/statusPanelCarouselUtils.ts";

function snapshot(overrides: Partial<StatusWorkflowSnapshot> = {}): StatusWorkflowSnapshot {
  return {
    hasSkill: true,
    hasResult: false,
    matchingStatus: null,
    warningExecuted: false,
    hasReport: false,
    isProcessing: false,
    isBatchMatching: false,
    isRunningWarnings: false,
    ...overrides,
  };
}

test("workflow progress only advances from real result facts", () => {
  assert.deepEqual(statusWorkflowProgress(snapshot()).percent, 0);
  assert.equal(statusWorkflowProgress(snapshot({ hasResult: true, matchingStatus: "pending" })).percent, 40);
  assert.equal(statusWorkflowProgress(snapshot({ hasResult: true, matchingStatus: "completed" })).percent, 60);
  assert.equal(statusWorkflowProgress(snapshot({ hasResult: true, matchingStatus: "completed", warningExecuted: true })).percent, 80);
  assert.equal(statusWorkflowProgress(snapshot({ hasResult: true, matchingStatus: "completed", warningExecuted: true, hasReport: true })).percent, 100);
});

test("running labels come from actual processing flags instead of carousel time", () => {
  assert.equal(statusWorkflowProgress(snapshot({ isProcessing: true })).headline, "正在读取 Excel");
  assert.equal(statusWorkflowProgress(snapshot({ hasResult: true, matchingStatus: "pending", isBatchMatching: true })).headline, "正在批量匹配");
  assert.equal(statusWorkflowProgress(snapshot({ hasResult: true, matchingStatus: "completed", isRunningWarnings: true })).headline, "正在运行风险预警");
});

test("filmstrip remains a three-stage window and relay keeps experience pending governance", () => {
  assert.deepEqual(filmstripStageIndexes(0), [0, 1, 2]);
  assert.deepEqual(filmstripStageIndexes(2), [1, 2, 3]);
  assert.deepEqual(filmstripStageIndexes(4), [2, 3, 4]);
  const active = relayActiveIndex(snapshot({ hasResult: true, matchingStatus: "completed", warningExecuted: true, hasReport: true }));
  assert.equal(active, 5);
  assert.equal(relayStageState(4, active), "completed");
  assert.equal(relayStageState(5, active), "current");
});

test("carousel keeps the original donut plus four alternatives and accessibility controls", async () => {
  const source = await readFile(new URL("../src/components/status-panel/StatusPanelCarousel.tsx", import.meta.url), "utf8");
  ["匹配状态环形图", "状态胶片带", "纵向地铁线", "四格状态舱", "任务接力带"].forEach((label) => assert.match(source, new RegExp(label)));
  assert.equal(source.match(/\{ id: "(?:filmstrip|metro|metrics|relay)"/g)?.length, 4);
  assert.match(source, /<div className="status-carousel__viewport">[\s\S]*<DonutView[\s\S]*<div className="status-carousel__dots"/);
  assert.match(source, /is-filmstrip">\s*<p>[\s\S]*<div className="status-carousel__filmstrip"/);
  assert.doesNotMatch(source, /ProgressView|专业处理真实阶段进度|细进度带/);
  assert.doesNotMatch(source, /<small>Total<\/small>/);
  assert.doesNotMatch(source, /status-carousel__view-title/);
  assert.match(source, /CAROUSEL_DELAY_MS = 7000/);
  assert.match(source, /prefers-reduced-motion: reduce/);
  assert.match(source, /ArrowLeft/);
  assert.match(source, /ArrowRight/);
  assert.match(source, /onMouseEnter/);
  assert.match(source, /aria-current/);
});

test("carousel CSS stacks the compact rotating view over the fixed donut", async () => {
  const css = await readFile(new URL("../src/components/status-panel/statusPanelCarousel.css", import.meta.url), "utf8");
  assert.match(css, /width:\s*206px/);
  assert.match(css, /grid-template-rows:\s*100px 84px 32px/);
  assert.match(css, /row-gap:\s*10px/);
  assert.match(css, /height:\s*252px/);
  assert.match(css, /status-carousel__filmstrip[\s\S]*margin-top:\s*10px/);
  assert.match(css, /padding-block:\s*8px/);
  assert.match(css, /--dws-font-family-ui/);
  assert.match(css, /prefers-reduced-motion/);
  assert.doesNotMatch(css, /font-size:\s*(9|10|11)px/);
  assert.doesNotMatch(css, /box-shadow/);
  assert.doesNotMatch(css, /animation:[^;]*\binfinite\b/);
  assert.doesNotMatch(css, /status-carousel__view-title/);
  assert.doesNotMatch(css, /status-carousel__progress-/);
  assert.match(css, /status-carousel__film-frame[\s\S]*border:\s*0/);
  assert.match(css, /status-carousel__workflow-view\.is-filmstrip p[\s\S]*top:\s*-2px/);
  assert.match(css, /status-carousel__donut-center strong[\s\S]*font-family:\s*var\(--dws-font-family-ui\)/);
  assert.match(css, /status-carousel__donut-center strong[\s\S]*font-size:\s*var\(--dws-font-size-20\)/);
  assert.match(css, /status-carousel__donut-center strong[\s\S]*color:\s*var\(--db-text-muted\)/);
});

test("status panel removes the duplicated persistent metric rows but keeps the donut legend", async () => {
  const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const styles = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(appSource, /className="daweiba-status-legend"/);
  assert.doesNotMatch(appSource, /daweiba-status-rows/);
  assert.doesNotMatch(appSource, /daweibaStatusRows/);
  assert.match(styles, /daweiba-module-list[\s\S]*scrollbar-gutter:\s*stable/);
  assert.match(styles, /daweiba-module-list::-(?:webkit-)?scrollbar-thumb[\s\S]*rgba\(148, 163, 184, 0\.32\)/);
});
