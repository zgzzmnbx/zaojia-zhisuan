import assert from "node:assert/strict";
import test from "node:test";
import { agentConversationTurns, agentSelectedSkill, agentTaskPhase, agentTaskPhaseLabel } from "../src/components/agent-workspace/agentWorkspaceUtils.ts";

const skills = [
  {
    id: "survey",
    display_name: "勘察测量最高投标限价编制",
    version: "1.0.0",
    status: "active" as const,
    status_label: "已上线",
    domain: "工程造价",
    description: "真实可执行能力",
    capabilities: [],
    asset_count: 1,
    validation_status: "passed",
    is_default: true,
    can_create_task: true,
  },
  {
    id: "planned",
    display_name: "通用服务类造价测算",
    version: "0.1.0",
    status: "planned" as const,
    status_label: "规划中",
    domain: "工程造价",
    description: "尚不可执行",
    capabilities: [],
    asset_count: 0,
    validation_status: "planned",
    is_default: false,
    can_create_task: false,
  },
];

test("derives the deterministic task phase used by the workspace", () => {
  assert.equal(agentTaskPhase({ hasFile: false, hasResult: false, matchingPending: false, warningExecuted: false }), "empty");
  assert.equal(agentTaskPhase({ hasFile: true, hasResult: false, matchingPending: false, warningExecuted: false }), "file-ready");
  assert.equal(agentTaskPhase({ hasFile: true, hasResult: true, matchingPending: true, warningExecuted: false }), "preview-ready");
  assert.equal(agentTaskPhase({ hasFile: true, hasResult: true, matchingPending: false, warningExecuted: true }), "warning-complete");
  assert.equal(agentTaskPhaseLabel("preview-ready"), "待批量匹配");
});

test("uses registry data and locks the task skill snapshot", () => {
  assert.deepEqual(agentSelectedSkill(skills, "survey"), {
    id: "survey",
    displayName: "勘察测量最高投标限价编制",
    version: "1.0.0",
    locked: false,
    executable: true,
  });
  assert.deepEqual(agentSelectedSkill(skills, "planned"), {
    id: "planned",
    displayName: "通用服务类造价测算",
    version: "0.1.0",
    locked: false,
    executable: false,
  });
  assert.equal(agentSelectedSkill(skills, "planned", {
    id: "survey",
    display_name: "勘察测量最高投标限价编制",
    version: "1.0.0",
    manifest_hash: "hash",
    created_at: "2026-07-21T00:00:00Z",
    compatibility_fallback: false,
  }).locked, true);
});

test("starts a visually separated turn at every user instruction", () => {
  const messages = [
    { id: "welcome", role: "assistant" as const, content: "welcome" },
    { id: "u1", role: "user" as const, content: "first" },
    { id: "a1", role: "assistant" as const, content: "answer" },
    { id: "a2", role: "system" as const, content: "progress" },
    { id: "u2", role: "user" as const, content: "second" },
    { id: "a3", role: "assistant" as const, content: "answer 2" },
  ];

  assert.deepEqual(agentConversationTurns(messages).map((turn) => turn.map((message) => message.id)), [
    ["welcome"],
    ["u1", "a1", "a2"],
    ["u2", "a3"],
  ]);
});
