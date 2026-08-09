import assert from "node:assert/strict";
import test from "node:test";
import {
  latestReviewTasksByPlatform,
  summarizeReviewProgress,
  type ReviewProgressTask,
} from "../src/components/agent-workspace/reviewProgress.ts";
import { detectZhisuanCommand } from "../src/components/agent-workspace/zhisuanCommands.ts";

function task(overrides: Partial<ReviewProgressTask>): ReviewProgressTask {
  return {
    task_id: "task-1",
    source_job_id: "job-1",
    is_web_result_review: true,
    platform: "default",
    participants: [],
    deadline: "2026-08-13T00:18:00+08:00",
    status: "reviewing",
    status_label: "复核中",
    review_round: 1,
    created_at: "2026-08-10T08:00:00+08:00",
    ...overrides,
  };
}

test("detects review progress commands without hijacking explanatory questions", () => {
  assert.equal(detectZhisuanCommand("审核进度查询"), "review-progress");
  assert.equal(detectZhisuanCommand("查询复核进度"), "review-progress");
  assert.equal(detectZhisuanCommand("复核到哪了"), "review-progress");
  assert.equal(detectZhisuanCommand("如何查询审核进度"), null);
});

test("summarizes approved, pending and returned reviewers from real participant states", () => {
  const summary = summarizeReviewProgress([
    task({
      participants: [
        { role: "编制人", name: "编制人", status: "已领取" },
        { role: "复核人", name: "甲", status: "已通过" },
        { role: "复核人", name: "乙", status: "待复核" },
      ],
    }),
    task({
      task_id: "task-2",
      platform: "weact_cost",
      participants: [{ role: "复核人", name: "丙", status: "已退回", comment: "请补充依据" }],
    }),
  ]);
  assert.deepEqual(summary, {
    total: 3,
    approved: 1,
    pending: 1,
    returned: 1,
    processed: 2,
    processedPercent: 67,
    tone: "returned",
    label: "有退回意见",
  });
});

test("keeps only the newest current-job task for each platform", () => {
  const tasks = latestReviewTasksByPlatform([
    task({ task_id: "old-feishu", created_at: "2026-08-09T08:00:00+08:00" }),
    task({ task_id: "new-feishu", created_at: "2026-08-10T08:00:00+08:00" }),
    task({ task_id: "weact", platform: "weact_cost", created_at: "2026-08-10T07:00:00+08:00" }),
    task({ task_id: "other-job", source_job_id: "job-2" }),
    task({ task_id: "not-review", is_web_result_review: false }),
  ], "job-1");
  assert.deepEqual(tasks.map((item) => item.task_id), ["new-feishu", "weact"]);
});
