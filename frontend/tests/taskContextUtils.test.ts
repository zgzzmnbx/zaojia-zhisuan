import assert from "node:assert/strict";
import test from "node:test";
import {
  taskAvailableActions,
  taskBarLayoutForWidth,
  taskEventStatusLabel,
  taskEventTarget,
  taskEventTone,
  taskStageTarget,
  taskStatusTone,
  type BusinessTask,
  type TaskEvent,
} from "../src/components/task-context/taskContextUtils.ts";

function task(overrides: Partial<BusinessTask> = {}): BusinessTask {
  return {
    task_id: "tsk_aaaaaaaaaaaaaaaaaaaaaaaa",
    project_id: "prj_bbbbbbbbbbbbbbbbbbbbbbbb",
    source: { type: "web", reference: "" },
    task_name: "控制价辅助填价",
    objective: "形成可复核成果",
    instructions: "",
    definition: { expected_artifacts: ["excel", "word"], human_gates: ["冲突项人工复核"] },
    skill_snapshot: { id: "survey", display_name: "勘察测量", version: "1.0.0" },
    input_snapshot: { reference: "输入.xlsx", type: "xlsx", version: 1, sha256: "a".repeat(64) },
    responsibility: {},
    status: "processing",
    status_label: "处理中",
    stage: "rules_executed",
    stage_label: "规则已执行",
    current_run_id: "run_cccccccccccccccccccccccc",
    artifact_version: 1,
    review_round: 0,
    classification_status: "classified",
    links: [],
    created_at: "2026-08-12T10:00:00+08:00",
    updated_at: "2026-08-12T10:01:00+08:00",
    completed_at: "",
    ...overrides,
  };
}

function event(status: string, eventType = "rules_executed"): TaskEvent {
  return {
    event_id: `evt-${status}`,
    event_type: eventType,
    title: "节点",
    status,
    detail: "真实事件",
    source_module: "test",
    reference: null,
    payload: {},
    occurred_at: "2026-08-12T10:00:00+08:00",
    is_placeholder: false,
  };
}

test("business status and timeline status use one normalized vocabulary", () => {
  assert.equal(taskStatusTone("processing"), "processing");
  assert.equal(taskStatusTone("pending_review"), "review");
  assert.equal(taskStatusTone("completed"), "success");
  assert.equal(taskStatusTone("failed"), "failed");
  assert.equal(taskEventTone("not_run"), "neutral");
  assert.equal(taskEventTone("not_applicable"), "neutral");
  assert.equal(taskEventTone("no_candidate"), "neutral");
  assert.equal(taskEventStatusLabel("not_run"), "未运行");
  assert.equal(taskEventStatusLabel("not_applicable"), "不适用");
  assert.equal(taskEventStatusLabel("no_candidate"), "未形成候选");
});

test("unexecuted timeline nodes never expose fake navigation", () => {
  assert.equal(taskEventTarget(event("completed", "artifact_generated")), "preview");
  assert.equal(taskEventTarget(event("pending_review", "human_reviewed")), "collaboration");
  assert.equal(taskEventTarget(event("not_run", "risk_checked")), null);
  assert.equal(taskEventTarget(event("not_applicable", "collaboration_completed")), null);
  assert.equal(taskEventTarget(event("no_candidate", "experience_governed")), null);
});

test("task stage routing keeps one context across professional modules", () => {
  assert.equal(taskStageTarget("skill_frozen"), "fill");
  assert.equal(taskStageTarget("risk_checked"), "preview");
  assert.equal(taskStageTarget("artifact_generated"), "preview");
  assert.equal(taskStageTarget("human_reviewed"), "collaboration");
  assert.equal(taskStageTarget("experience_governed"), "knowledge");
  assert.equal(taskStageTarget("unknown"), null);
});

test("actions hide unavailable targets instead of rendering fake buttons", () => {
  assert.deepEqual(taskAvailableActions(null), { view: false, returnToStage: false, artifacts: false });
  assert.deepEqual(taskAvailableActions(task({ stage: "unknown", artifact_version: 0 })), {
    view: true, returnToStage: false, artifacts: false,
  });
  assert.deepEqual(taskAvailableActions(task()), {
    view: true, returnToStage: true, artifacts: true,
  });
});

test("1366, 1440, 1920 and narrow Dock resolve through container strategy", () => {
  assert.equal(taskBarLayoutForWidth(360), "dock");
  assert.equal(taskBarLayoutForWidth(620), "compact");
  assert.equal(taskBarLayoutForWidth(760), "wide");
  assert.equal(taskBarLayoutForWidth(1366), "wide");
  assert.equal(taskBarLayoutForWidth(1440), "wide");
  assert.equal(taskBarLayoutForWidth(1920), "wide");
});

test("drawer open and page navigation are read-only projections of one task id", () => {
  const original = task();
  const afterPageSwitch = { ...original, timeline: { task_id: original.task_id, items: [], actual_event_count: 0 } };
  assert.equal(afterPageSwitch.task_id, original.task_id);
  assert.equal(afterPageSwitch.current_run_id, original.current_run_id);
  assert.equal(afterPageSwitch.skill_snapshot.version, original.skill_snapshot.version);
  assert.equal(afterPageSwitch.artifact_version, original.artifact_version);
});
