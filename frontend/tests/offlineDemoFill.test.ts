import assert from "node:assert/strict";
import test from "node:test";
import {
  OFFLINE_DEMO_FILL_PRESET_ID,
  OFFLINE_DEMO_FILL_PROCESSING_MS,
  isOfflineDemoFillContext,
} from "../src/utils/offlineDemoFill.ts";

const targetContext = {
  sheetName: "表2-通用工程测量费用",
  rowNumber: 6,
  values: {
    内容: "首级控制测量",
    类别: "GPS测量E级",
    比例尺: "中等",
    单位: "个",
    "基价（元）": "3203",
  },
};

test("enables the offline AI-fill preset only for the exact demo row", () => {
  assert.equal(isOfflineDemoFillContext(targetContext), true);
  assert.equal(isOfflineDemoFillContext({
    ...targetContext,
    values: { ...targetContext.values, "基价（元）": "" },
  }), true);
  assert.equal(isOfflineDemoFillContext({ ...targetContext, rowNumber: 5 }), false);
  assert.equal(isOfflineDemoFillContext({ ...targetContext, sheetName: "表3-地质测绘" }), false);
  assert.equal(isOfflineDemoFillContext({
    ...targetContext,
    values: { ...targetContext.values, 类别: "GPS测量C级" },
  }), false);
  assert.equal(isOfflineDemoFillContext({
    ...targetContext,
    values: { ...targetContext.values, "基价（元）": "500000" },
  }), false);
});

test("keeps the row preset identifier and visible processing delay stable", () => {
  assert.equal(OFFLINE_DEMO_FILL_PRESET_ID, "offline-demo-fill-table2-row6");
  assert.equal(OFFLINE_DEMO_FILL_PROCESSING_MS, 4_000);
});
