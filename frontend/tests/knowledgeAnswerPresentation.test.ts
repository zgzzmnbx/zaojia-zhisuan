import assert from "node:assert/strict";
import test from "node:test";
import {
  compactKnowledgeSourceName,
  removeVerboseEvidenceSection,
  uniqueKnowledgeSources,
} from "../src/utils/knowledgeAnswerPresentation.ts";

test("removes a verbose evidence section while preserving following guidance", () => {
  const answer = [
    "智算解释：",
    "结论和表格。",
    "",
    "正式依据：",
    "1. D:/资料/第一册.md / 表2",
    "2. D:/资料/第二册.md / 表2",
    "",
    "提示：本回答只解释依据。",
  ].join("\n");

  assert.equal(
    removeVerboseEvidenceSection(answer),
    "智算解释：\n结论和表格。\n\n提示：本回答只解释依据。",
  );
});

test("recognizes bold list-style section headings emitted by the model", () => {
  const answer = [
    "智算解释：",
    "结论。",
    "",
    "- **正式依据：**",
    "  - **资料1**：第一册，Excel 第53行。",
    "  - **资料2**：第二册，Excel 第53行。",
    "",
    "- **提示：**",
    "  - 本回答只解释依据。",
  ].join("\n");

  assert.equal(
    removeVerboseEvidenceSection(answer),
    "智算解释：\n结论。\n\n- **提示：**\n  - 本回答只解释依据。",
  );
});

test("removes model and legacy project-memory detail sections", () => {
  const answer = [
    "智算解释：",
    "结论。",
    "",
    "项目记忆：",
    "1. 项目记忆完整审计信息。",
    "",
    "提示：保留这句话。",
    "",
    "已确认知识记忆（补充）：",
    "1. 通用知识｜标题｜确认时间。",
  ].join("\n");

  assert.equal(
    removeVerboseEvidenceSection(answer),
    "智算解释：\n结论。\n\n提示：保留这句话。",
  );
});

test("keeps ordinary text that merely mentions formal evidence", () => {
  const answer = "智算解释：正式依据优先于项目记忆。";
  assert.equal(removeVerboseEvidenceSection(answer), answer);
});

test("compacts file names and removes duplicate source entries", () => {
  const sources = [
    { library_name: "造价通用知识库", source_file: "D:/资料/第一册.md", title_path: "表2" },
    { library_name: "造价通用知识库", source_file: "D:/资料/第一册.md", title_path: "表2" },
    { library_name: "项目正式知识库", source_file: "D:/规则/规则卡片.md", title_path: "第3条" },
  ];

  assert.equal(compactKnowledgeSourceName(sources[0].source_file), "第一册.md");
  assert.deepEqual(uniqueKnowledgeSources(sources), [sources[0], sources[2]]);
});
