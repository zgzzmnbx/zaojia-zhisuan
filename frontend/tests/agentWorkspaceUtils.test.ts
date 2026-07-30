import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  agentComposerSpaceCompletion,
  agentConversationTurns,
  agentSelectedSkill,
  agentTaskPhase,
  agentTaskPhaseLabel,
  knowledgeQuestionPrompt,
  shouldShowKnowledgeQuestionSuggestions,
} from "../src/components/agent-workspace/agentWorkspaceUtils.ts";

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

test("completes a bare # into the knowledge command on Space", () => {
  assert.equal(agentComposerSpaceCompletion("#"), "#知识库：");
  assert.equal(agentComposerSpaceCompletion("说明 #"), null);
  assert.equal(agentComposerSpaceCompletion("@"), null);
  assert.equal(agentComposerSpaceCompletion("#知识库"), null);
  assert.equal(agentComposerSpaceCompletion(""), null);
});

test("shows maintainable knowledge questions only while the prefix is empty", () => {
  assert.equal(shouldShowKnowledgeQuestionSuggestions("#知识库"), true);
  assert.equal(shouldShowKnowledgeQuestionSuggestions("#知识库："), true);
  assert.equal(shouldShowKnowledgeQuestionSuggestions("#知识库: "), true);
  assert.equal(shouldShowKnowledgeQuestionSuggestions("#知识库：技术系数"), false);
  assert.equal(shouldShowKnowledgeQuestionSuggestions("普通问题"), false);
  assert.equal(knowledgeQuestionPrompt("  第二层经验提示是什么意思？  "), "#知识库：第二层经验提示是什么意思？");
});

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

test("composer send action uses the project primary blue with accessible states", async () => {
  const css = await readFile(new URL("../src/components/agent-workspace/agentWorkspace.css", import.meta.url), "utf8");
  assert.match(css, /\.shell\.layout-daweiba \.agent-workspace \.agent-composer__send\s*\{[^}]*background:\s*#2563eb;[^}]*color:\s*#ffffff;/s);
  assert.match(css, /\.shell\.layout-daweiba \.agent-workspace \.agent-composer__send:hover:not\(:disabled\)\s*\{[^}]*background:\s*#1d4ed8;/s);
  assert.match(css, /\.shell\.layout-daweiba \.agent-workspace \.agent-composer__send:disabled\s*\{[^}]*background:\s*#e8eef8;[^}]*color:\s*#94a3b8;/s);
  assert.match(css, /\.shell\.layout-daweiba \.agent-workspace \.agent-composer__send:focus-visible\s*\{[^}]*outline-color:\s*#2563eb;/s);
});
