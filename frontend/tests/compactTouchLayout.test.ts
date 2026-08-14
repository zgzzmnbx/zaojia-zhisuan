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

test("竖屏当前模块入口按图标和文字内容展开", () => {
  assert.match(
    css,
    /\.daweiba-icon-link\.is-active\s*\{[\s\S]*?flex:\s*0 0 auto;[\s\S]*?width:\s*auto;/,
  );
});

test("手机专业能力弹层和顶部导航使用视口内布局", () => {
  assert.match(css, /\.global-nav \.professional-skill-selector__menu\s*\{[\s\S]*?position:\s*fixed;/);
  assert.match(css, /min-height:\s*calc\(62px \+ env\(safe-area-inset-top/);
  assert.match(css, /padding-top:\s*calc\(8px \+ env\(safe-area-inset-top/);
});

test("手机表格保留内部横向滚动", () => {
  assert.match(css, /\.table-scroll,[\s\S]*?overflow-x:\s*auto;/);
});

test("竖屏智算发送按钮保持正方形且回答宽内容内部滚动", () => {
  assert.match(css, /\.agent-composer__submit\s*\{[\s\S]*?flex:\s*0 0 44px;[\s\S]*?width:\s*44px;/);
  assert.match(css, /\.agent-message\.assistant \.chat-message-body table\s*\{[\s\S]*?overflow-x:\s*auto;/);
  assert.match(css, /\.agent-workspace__messages\s*\{[\s\S]*?overflow-x:\s*hidden;/);
});

test("竖屏适配层在现有主样式之后加载", () => {
  const baseIndex = main.indexOf('import "./styles.css";');
  const compactIndex = main.indexOf('import "./compact-touch.css";');
  assert.ok(baseIndex >= 0);
  assert.ok(compactIndex > baseIndex);
});
