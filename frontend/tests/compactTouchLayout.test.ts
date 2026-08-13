import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync(new URL("../src/compact-touch.css", import.meta.url), "utf8");
const main = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");

test("竖屏适配样式只通过窄屏媒体查询进入", () => {
  const firstRule = css.indexOf("@media");
  assert.ok(firstRule > 0);
  assert.match(css.slice(0, firstRule), /^\s*\/\*[\s\S]*?\*\/\s*$/);
  assert.match(css, /@media \(max-width: 1024px\)/);
  assert.doesNotMatch(css, /@media \(min-width:/);
});

test("触控适配包含桌面保护、动态视口、安全区和最小触控尺寸", () => {
  assert.match(css, /1025px 及以上/);
  assert.match(css, /100dvh/);
  assert.match(css, /safe-area-inset-bottom/);
  assert.match(css, /min-height: 44px/);
  assert.match(css, /touch-action: manipulation/);
});

test("竖屏适配层在现有主样式之后加载", () => {
  const baseIndex = main.indexOf('import "./styles.css";');
  const compactIndex = main.indexOf('import "./compact-touch.css";');
  assert.ok(baseIndex >= 0);
  assert.ok(compactIndex > baseIndex);
});
