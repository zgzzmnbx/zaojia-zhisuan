import assert from "node:assert/strict";
import test from "node:test";
import { parseZhisuanInlineMarkdown } from "../src/utils/zhisuanInlineMarkdown.ts";

test("parses the supported inline Markdown formats", () => {
  assert.deepEqual(
    parseZhisuanInlineMarkdown(
      "**加粗**、*斜体*、***同时***、~~删除~~、`代码`、[来源](https://example.com/a)",
    ),
    [
      { type: "strong", children: [{ type: "text", value: "加粗" }] },
      { type: "text", value: "、" },
      { type: "emphasis", children: [{ type: "text", value: "斜体" }] },
      { type: "text", value: "、" },
      { type: "strong-emphasis", children: [{ type: "text", value: "同时" }] },
      { type: "text", value: "、" },
      { type: "delete", children: [{ type: "text", value: "删除" }] },
      { type: "text", value: "、" },
      { type: "code", value: "代码" },
      { type: "text", value: "、" },
      {
        type: "link",
        href: "https://example.com/a",
        children: [{ type: "text", value: "来源" }],
      },
    ],
  );
});

test("does not create executable links and preserves malformed Markdown as text", () => {
  assert.deepEqual(
    parseZhisuanInlineMarkdown("[危险](javascript:alert(1)) 与 **未闭合"),
    [{ type: "text", value: "[危险](javascript:alert(1)) 与 **未闭合" }],
  );
});

test("supports escaped Markdown punctuation", () => {
  assert.deepEqual(
    parseZhisuanInlineMarkdown("\\*\\*不是强调\\*\\*"),
    [{ type: "text", value: "**不是强调**" }],
  );
});
