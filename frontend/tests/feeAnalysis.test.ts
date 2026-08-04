import assert from "node:assert/strict";
import test from "node:test";
import { buildFeeAnalysis } from "../src/components/agent-workspace/feeAnalysis.ts";
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
