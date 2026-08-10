import assert from "node:assert/strict";
import test from "node:test";

import {
  trustedMetricRows,
  trustedProjectId,
  trustedSourceDetails,
} from "../src/utils/trustedExperience.ts";


test("formats controlled event lineage without exposing paths or platform identifiers", () => {
  const rows = trustedSourceDetails({
    event_type: "cell_edit",
    classification_status: "pending_classification",
    task_id: "job-a",
    skill_id: "survey-measurement-v1",
    skill_version: "1.0.0",
    sheet_name: "控制价",
    row_number: 2,
    field_name: "基价",
    artifact_version: "v2",
    artifact_hash: "a".repeat(64),
  });
  const text = JSON.stringify(rows);

  assert.match(text, /人工改单元格/);
  assert.match(text, /待归类（任务隔离）/);
  assert.match(text, /控制价 \/ 第2行 \/ 基价/);
  assert.match(text, /aaaaaaaaaaaaaaaa/);
  assert.doesNotMatch(text, /[A-Z]:\\|platform|secret/i);
});


test("uses only reliable project identifiers for capsule operations", () => {
  assert.equal(trustedProjectId("prj_aaaaaaaaaaaaaaaaaaaaaaaa", "同名项目"), "prj_aaaaaaaaaaaaaaaaaaaaaaaa");
  assert.equal(trustedProjectId("", "prj_bbbbbbbbbbbbbbbbbbbbbbbb"), "prj_bbbbbbbbbbbbbbbbbbbbbbbb");
  assert.equal(trustedProjectId("", "同名项目"), "");
});


test("renders only real count fields and never invents saved time", () => {
  const rows = trustedMetricRows({
    candidate_sources: 2,
    events: { cell_edit: 1, review_opinion: 1 },
    governance: { confirmed: 2, rejected: 0, revoked: 1 },
    retrieval_hits: 3,
    version_corrections: 1,
    suspected_stale: 0,
  });

  assert.equal(rows.length, 9);
  assert.deepEqual(rows.find((row) => row.label === "检索命中"), { label: "检索命中", value: 3 });
  assert.doesNotMatch(JSON.stringify(rows), /节省|工时|估算/);
});
