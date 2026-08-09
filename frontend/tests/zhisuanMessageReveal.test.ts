import test from "node:test";
import assert from "node:assert/strict";
import {
  nextZhisuanMessageReveal,
  zhisuanMessageRevealDelay,
} from "../src/utils/zhisuanMessageReveal.ts";

test("visual message reveals one paragraph block at a time", () => {
  const content = [
    "批量匹配完成。",
    "",
    "本轮结果：",
    "- 输入明细：100 行",
    "- 已填数据：99 行",
    "",
    "下一步建议：",
    "可以继续运行经验池预警。",
  ].join("\n");

  const first = nextZhisuanMessageReveal(content, "", "block");
  const second = nextZhisuanMessageReveal(content, first, "block");
  const third = nextZhisuanMessageReveal(content, second, "block");

  assert.equal(first, "批量匹配完成。\n\n");
  assert.equal(second, "批量匹配完成。\n\n本轮结果：\n- 输入明细：100 行\n- 已填数据：99 行\n\n");
  assert.equal(third, content);
});

test("single-paragraph visual message appears as one complete block", () => {
  const content = "费用洞察已生成。图表读取当前任务真实费用汇总。";
  assert.equal(nextZhisuanMessageReveal(content, "", "block"), content);
});

test("plain message keeps the existing character reveal pace", () => {
  assert.equal(nextZhisuanMessageReveal("普通消息", "", "character"), "普通");
  assert.equal(nextZhisuanMessageReveal("普通消息", "普通", "character"), "普通消息");
  assert.equal(zhisuanMessageRevealDelay("character"), 24);
  assert.equal(zhisuanMessageRevealDelay("block"), 260);
});
