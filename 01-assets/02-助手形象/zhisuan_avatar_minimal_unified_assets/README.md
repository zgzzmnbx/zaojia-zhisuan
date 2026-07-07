# 造价智算虚拟形象：极简统一形象素材包

本素材包按最新要求调整：

- 机器人形象更简约。
- 不同状态沿用统一形象。
- idle 状态必须有呼吸感。
- 状态只通过状态环、状态点、扫描线、勾号、叹号、错误符号表达。

## 文件说明

- `ZhisuanAvatar.tsx`：React 内联 SVG 组件草案。
- `ZhisuanAvatar.css`：状态动效 CSS，包含 idle 呼吸感。
- `demo.html`：可直接双击打开，预览同一形象在不同状态下的动效。
- `zhisuan_avatar_unified.svg`：统一静态形象参考。
- `state-map.json`：状态表与硬约束。

## 给 Codex 的关键提醒

1. 不要把 `zhisuan_avatar_unified.svg` 当成 `<img>` 直接塞进去。
2. 正式实现应使用 `ZhisuanAvatar.tsx` 的内联 SVG。
3. 所有状态必须共用同一套 SVG DOM。
4. 不允许每个状态加载不同机器人图片。
5. idle 必须有呼吸感。
6. 必须支持 `prefers-reduced-motion: reduce`。
