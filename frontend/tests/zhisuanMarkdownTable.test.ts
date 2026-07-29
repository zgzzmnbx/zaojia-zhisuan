import assert from "node:assert/strict";
import test from "node:test";
import { parseMarkdownTableAt } from "../src/utils/zhisuanMarkdownTable.ts";

test("parses a standard Markdown table and its alignment markers", () => {
  const table = parseMarkdownTableAt([
    "| 清单名称 | 单位 | 清单单价 |",
    "| :--- | :---: | ---: |",
    "| 作业带扫线 | m² | 1.66元 |",
  ], 0);

  assert.deepEqual(table, {
    headers: ["清单名称", "单位", "清单单价"],
    alignments: ["left", "center", "right"],
    rows: [["作业带扫线", "m²", "1.66元"]],
    nextLineIndex: 3,
  });
});

test("supports escaped pipes and normalizes short rows", () => {
  const table = parseMarkdownTableAt([
    "名称 | 说明 | 来源",
    "--- | --- | ---",
    "规费 | 费率\\|取费说明",
    "后续普通段落",
  ], 0);

  assert.deepEqual(table?.rows, [["规费", "费率|取费说明", ""]]);
  assert.equal(table?.nextLineIndex, 3);
});

test("does not misclassify ordinary pipe-separated text as a table", () => {
  assert.equal(parseMarkdownTableAt([
    "名称 | 单位",
    "作业带扫线 | m²",
  ], 0), null);
});
