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
import {
  DEMO_KNOWLEDGE_QUESTIONS,
  isDemoKnowledgeQuestion,
} from "../src/components/knowledge/knowledgeDemoQuestions.ts";

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

test("marks only unchanged standard demo questions for the subtle blue dot", () => {
  assert.equal(DEMO_KNOWLEDGE_QUESTIONS.length, 4);
  assert.equal(isDemoKnowledgeQuestion(DEMO_KNOWLEDGE_QUESTIONS[0]), true);
  assert.equal(isDemoKnowledgeQuestion("勘察测量: 技术工作费调整系数如何确定?"), true);
  assert.equal(isDemoKnowledgeQuestion("勘察测量，实物工作费调整系数如何确定？"), false);
});

test("keeps preset knowledge answers in a visible five-second processing flow", async () => {
  const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(appSource, /PRESET_KNOWLEDGE_PROCESSING_MS\s*=\s*5000/);
  assert.match(appSource, /正在识别演示问题并加载标准知识范围/);
  assert.match(appSource, /已命中演示知识，正在核对标准依据和来源/);
  assert.match(appSource, /标准依据已核对，正在组织结构化答案/);
  assert.match(appSource, /typing:\s*payload\.preset_answer\s*\?\s*false\s*:\s*undefined/);
  assert.match(appSource, /aria-valuenow=\{Math\.round\(progress\)\}/);
  assert.match(appSource, /style=\{\{ width: `\$\{progress\}%` \}\}/);
  assert.match(appSource, /tone === "processing"[\s\S]*rotate\(\$\{frame \* 24\}deg\)/);
  assert.match(appSource, /tone === "knowledge"[\s\S]*completionPulse \* 0\.06/);
  assert.match(appSource, /knowledge-evidence-summary__icon[\s\S]*zhisuan-status-icon__glyph" style=\{motionStyle\}/);
  assert.doesNotMatch(appSource, /knowledge-evidence-summary__icon" aria-hidden="true" style=\{motionStyle\}/);
  assert.match(css, /\.zhisuan-processing-progress\s*>\s*i[\s\S]*transition:\s*width\s+120ms\s+linear/);
  assert.match(css, /\.zhisuan-processing-progress\s*>\s*i\s*\{[^}]*background:\s*var\(--blue\);[^}]*box-shadow:\s*none;/s);
  assert.doesNotMatch(css, /\.zhisuan-processing-progress\s*>\s*i\s*\{[^}]*linear-gradient/s);
  assert.doesNotMatch(css, /animation:\s*zhisuan-processing-progress/);
});

test("routes the row AI entry through ranked AI pricing candidates", async () => {
  const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  assert.match(appSource, /title="AI填价"/);
  assert.match(appSource, /openFillAssist\(row, rowIndex, undefined, \{ autoRunAi: true \}\)/);
  assert.match(appSource, /candidate_recommendations:\s*candidates\.slice\(0, 3\)/);
  assert.match(appSource, /候选列表已经由程序按相似度、来源优先级和可信度完成排序/);
  assert.match(appSource, /只能引用当前结构化候选中的数值/);
  assert.match(appSource, /开始AI填价/);
  assert.doesNotMatch(appSource, /开始AI复核/);
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
