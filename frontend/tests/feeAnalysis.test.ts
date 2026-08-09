import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { buildFeeAnalysis } from "../src/components/agent-workspace/feeAnalysis.ts";
import {
  FEE_ANALYSIS_REVEAL_DELAYS_MS,
  FEE_ANALYSIS_REVEAL_STAGE_COUNT,
  feeAnalysisRevealStageAt,
} from "../src/components/agent-workspace/feeAnalysisReveal.ts";
import { detectZhisuanCommand } from "../src/components/agent-workspace/zhisuanCommands.ts";

const preview = {
  headers: ["序号", "项目", "费用（万元）", "备注"],
  rows: [],
  sheets: [
    {
      sheet_name: "费用汇总",
      headers: ["序号", "项目", "费用（万元）", "备注"],
      rows: [
        [1, "长输管道线路工程勘察测量费用", 0, "测算明细见附表1"],
        [2, "通用工程测量费用", 1018.64, "测算明细见附表2"],
        [3, "地质测绘费用", 17.29, "测算明细见附表3"],
        [4, "通用工程勘察费用", 1890.18, "测算明细见附表4"],
        ["小计", "", 2926.11, ""],
        [5, "浮动后勘察费", 2633.50, ""],
        [6, "其他相关费用", 39.36, ""],
        ["合计（含税）", "", 2672.86, ""],
        ["合计（不含税）", "", 2521.57, ""],
        ["增值税", "", 151.29, ""],
      ],
    },
  ],
};

test("builds non-overlapping final and professional fee compositions", () => {
  const analysis = buildFeeAnalysis(preview);
  assert.ok(analysis);
  assert.equal(analysis.unit, "万元");
  assert.equal(analysis.totalWithTax, 2672.86);
  assert.deepEqual(analysis.finalComposition.map((item) => item.label), ["浮动后勘察费", "其他相关费用"]);
  assert.deepEqual(analysis.professionalComposition.map((item) => item.label), [
    "长输管道线路工程勘察测量费用",
    "通用工程测量费用",
    "地质测绘费用",
    "通用工程勘察费用",
  ]);
  assert.equal(Math.round(analysis.finalComposition.reduce((sum, item) => sum + item.share, 0) * 100), 100);
  assert.equal(Math.round(analysis.professionalComposition.reduce((sum, item) => sum + item.share, 0) * 100), 100);
});

test("does not invent fee charts without a fee summary sheet", () => {
  assert.equal(buildFeeAnalysis({ sheet_name: "表2", headers: ["项目", "金额"], rows: [["测量", 1]] }), null);
});

test("routes both fee insight phrases to the deterministic chart command", () => {
  assert.equal(detectZhisuanCommand("图表分析"), "fee-analysis");
  assert.equal(detectZhisuanCommand("费用洞察"), "fee-analysis");
  assert.equal(detectZhisuanCommand("请做一次费用洞察"), "fee-analysis");
  assert.equal(detectZhisuanCommand("图表分析是怎么生成的？"), null);
});

test("animates fee charts on entry while respecting reduced motion", () => {
  const componentSource = readFileSync(
    new URL("../src/components/agent-workspace/ZhisuanFeeAnalysisCharts.tsx", import.meta.url),
    "utf8",
  );
  const stylesheet = readFileSync(
    new URL("../src/components/agent-workspace/feeAnalysis.css", import.meta.url),
    "utf8",
  );

  assert.match(componentSource, /--fee-animation-delay/);
  assert.match(componentSource, /--fee-animation-duration/);
  assert.match(componentSource, /animationTimelineMs = 1500/);
  assert.match(componentSource, /FEE_ANALYSIS_REVEAL_DELAYS_MS\.map/);
  assert.match(componentSource, /matchMedia\("\(prefers-reduced-motion: reduce\)"\)/);
  assert.match(componentSource, /setRevealStage\(FEE_ANALYSIS_REVEAL_STAGE_COUNT\)/);
  assert.match(stylesheet, /@keyframes fee-analysis-donut-fill/);
  assert.match(stylesheet, /@keyframes fee-analysis-bar-fill/);
  assert.match(stylesheet, /@media \(prefers-reduced-motion: no-preference\)/);
  assert.match(stylesheet, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(stylesheet, /--fee-animation-duration, 1500ms/);
});

test("reveals fee insight modules from top to bottom", () => {
  assert.equal(FEE_ANALYSIS_REVEAL_STAGE_COUNT, 8);
  assert.deepEqual([...FEE_ANALYSIS_REVEAL_DELAYS_MS].sort((left, right) => left - right), [
    ...FEE_ANALYSIS_REVEAL_DELAYS_MS,
  ]);
  assert.equal(feeAnalysisRevealStageAt(0), 0);
  assert.equal(feeAnalysisRevealStageAt(180), 1);
  assert.equal(feeAnalysisRevealStageAt(820), 3);
  assert.equal(feeAnalysisRevealStageAt(1340), 5);
  assert.equal(feeAnalysisRevealStageAt(1680), 6);
  assert.equal(feeAnalysisRevealStageAt(2280), 7);
  assert.equal(feeAnalysisRevealStageAt(2780), 8);
});
