# RRD-智算助手形象-极简统一形象呼吸动效版

## 文件定位

本文是“问问智算可动虚拟形象”的 Codex 执行版 PRD，重点明确两条硬要求：

1. 形象必须更简约。
2. 不同状态必须沿用统一形象，不允许每个状态换一个机器人。

它服务 `00-PRD/01-模块PRD/04-问问智算AI助手/PRD.md` 中的 P2“可动虚拟形象状态层”，不替代主 PRD，不改动主业务流程，不改变价格 / 系数匹配逻辑。

## 一、设计结论

本轮采用：

```text
极简统一形象：智算胶囊 / Z Core
```

核心方案：

```text
一个统一 SVG 机器人徽标 + 状态环 / 状态点 / 眼点 / 扫描线变化 + idle 呼吸感
```

不采用：

- 每个状态换一套机器人图。
- 复杂五官。
- 复杂机械手、身体、天线、放大镜等装饰。
- Live2D、3D、真人数字人。
- 独立桌宠窗口。
- 直接用 `<img src="xxx.svg">` 加载静态图。
- 多套外部素材混搭。

理由：

1. 右侧智算助手是企业级工作台里的状态层，不是桌宠。
2. 统一形象可以保持品牌识别，不会出现状态切换时形象割裂。
3. 极简形象更适合长期嵌入表格、报告、风险复核等密集信息界面。
4. 状态只改变“行为”和“语义色”，不改变角色身份。

## 二、形象定义

推荐名称：

```text
智算胶囊 / Z Core
```

形象结构：

| 层级 | 内容 | 是否随状态变化 |
| --- | --- | --- |
| 外轮廓 | 圆角胶囊 / 圆角芯片 | 不变 |
| 内屏幕 | 简化面板 | 不变，仅背景色轻微变化 |
| 眼点 | 两个极简圆点 | 位置 / 透明度可轻微变化 |
| 中央符号 | 简化 Z / 短横线 | 不变或轻微呼吸 |
| 状态环 | 外圈细线 | 颜色 / 旋转 / 闪烁变化 |
| 状态点 | 右上角小点 | 颜色变化 |
| 状态符号 | 勾号 / 叹号 / 错误短线 | 只在对应状态出现 |

视觉关键词：

- 极简。
- 统一。
- 低干扰。
- 小尺寸可读。
- 扁平化。
- 企业级 SaaS。
- 允许轻微拟人，不做可爱宠物。

## 三、状态类型

```ts
type ZhisuanAvatarState =
  | "idle"
  | "listening"
  | "thinking"
  | "processing"
  | "warning"
  | "error"
  | "success";
```

状态优先级：

```text
error > thinking > processing > warning > success > listening > idle
```

## 四、统一形象硬要求

### 4.1 不同状态不得更换主体形象

所有状态必须复用同一个 SVG 结构：

- 同一个外轮廓。
- 同一个内屏幕。
- 同一个眼点体系。
- 同一个状态环。
- 同一个右上角状态点。

允许变化：

- 状态环颜色。
- 状态环旋转 / 呼吸 / 短闪。
- 眼点轻微移动。
- 扫描线出现或隐藏。
- 勾号 / 叹号 / 错误符号出现或隐藏。
- 局部背景从蓝灰轻微变为黄 / 红 / 绿提示色。

不允许变化：

- 不允许 idle 是一个机器人、error 是另一个机器人。
- 不允许 warning 出现放大镜机器人。
- 不允许 success 出现完全不同头像。
- 不允许每个状态加载独立 SVG 图片作为主形象。
- 不允许引入风格差异明显的外部图标包拼贴。

### 4.2 只做“状态层变化”

状态表达方式应遵循：

```text
角色不变，状态变化。
```

例如：

- idle：同一个形象轻微呼吸。
- thinking：同一个形象出现扫描线和蓝色旋转环。
- processing：同一个形象外圈旋转。
- warning：同一个形象右上角状态点变黄，出现小叹号。
- error：同一个形象右上角状态点变红，出现错误短线。
- success：同一个形象右上角状态点变绿，出现勾号。

## 五、呼吸感硬要求

`idle` 状态必须有呼吸感。

呼吸感定义：

```text
慢速上下浮动 + 微缩放
```

参数要求：

| 参数 | 要求 |
| --- | --- |
| 动画周期 | 3.0s 到 3.6s |
| 上下浮动 | 0.5px 到 1.2px |
| 缩放范围 | 1.000 到 1.012 |
| easing | ease-in-out |
| 干扰度 | 低，不吸引过多注意 |
| 降低动效 | 必须支持 `prefers-reduced-motion: reduce` |

CSS 参考：

```css
.zhisuan-avatar[data-state="idle"] {
  animation: zhisuan-breathe 3.3s ease-in-out infinite;
}

@keyframes zhisuan-breathe {
  0%, 100% {
    transform: translateY(0) scale(1);
  }
  50% {
    transform: translateY(-1px) scale(1.01);
  }
}
```

## 六、状态动效

| 状态 | 触发场景 | 动效 | 状态色 |
| --- | --- | --- | --- |
| `idle` | 无任务、等待输入 | 轻微呼吸 | 灰蓝 |
| `listening` | 输入框聚焦 / 用户输入 | 轻微前倾，眼点聚焦 | 蓝灰 |
| `thinking` | 知识库检索、模型请求、行级 AI 复核 | 扫描线移动，眼点轻扫 | 蓝 `#2563EB` |
| `processing` | Excel 转换、经验池预警、重算公式、报告生成 | 外圈进度环旋转 | 蓝 `#2563EB` |
| `warning` | 待复核、经验池预警、高风险 | 右上状态点变黄，轻闪一次，叹号出现 | 黄 `#F59E0B` |
| `error` | API 失败、后端异常、文件识别失败、无依据 | 右上状态点变红，短促摇头一次，错误符号出现 | 红 `#B42318` |
| `success` | 转换完成、报告生成、知识库命中 | 右上状态点变绿，勾号出现，小弹一次 | 绿 `#16A34A` |

## 七、组件设计

建议新增：

```text
frontend/src/components/ZhisuanAvatar.tsx
frontend/src/components/ZhisuanAvatar.css
```

组件接口：

```ts
export type ZhisuanAvatarState =
  | "idle"
  | "listening"
  | "thinking"
  | "processing"
  | "warning"
  | "error"
  | "success";

export type ZhisuanAvatarSize = "compact" | "normal" | "large";

export interface ZhisuanAvatarProps {
  state?: ZhisuanAvatarState;
  size?: ZhisuanAvatarSize;
  label?: string;
  className?: string;
}
```

实现要求：

1. SVG 必须内联在 React 组件中。
2. 不允许只用 `<img>` 加载静态 SVG。
3. 所有状态必须共用同一套 SVG DOM。
4. 状态通过 `data-state` 控制。
5. 组件不发起网络请求。
6. 组件不修改任何业务数据。
7. 组件可以被未来 Lottie / Rive 替换，但本次不引入这些依赖。

## 八、嵌入位置

只允许放在：

1. 右侧“问问智算”侧栏顶部身份区。
2. 右侧助手折叠入口的小尺寸状态徽标。
3. 演示模式 / 评委模式讲解节点，如果当前已有对应位置。

不允许：

- 放在表格中央。
- 做成全局悬浮桌宠。
- 遮挡预览表格、下载按钮、列映射、经验池操作区。
- 影响右侧输入框可用性。

## 九、前端状态映射

状态只从现有前端状态派生，不新增后端接口。

伪代码：

```ts
function deriveZhisuanAvatarState(ctx: {
  hasError: boolean;
  isAiThinking: boolean;
  isProcessingExcel: boolean;
  isWarningRunning: boolean;
  isGeneratingReport: boolean;
  hasWarning: boolean;
  inputFocused: boolean;
  justSucceeded: boolean;
}): ZhisuanAvatarState {
  if (ctx.hasError) return "error";
  if (ctx.isAiThinking) return "thinking";
  if (ctx.isProcessingExcel || ctx.isWarningRunning || ctx.isGeneratingReport) return "processing";
  if (ctx.hasWarning) return "warning";
  if (ctx.justSucceeded) return "success";
  if (ctx.inputFocused) return "listening";
  return "idle";
}
```

## 十、业务边界

不得修改：

- Excel 填价主流程。
- 三数字匹配逻辑。
- 知识库匹配逻辑。
- 经验池预警计算逻辑。
- 行级 AI 复核业务逻辑。
- Word 报告生成逻辑。
- 下载接口。
- 后端 API 路由。
- 价格 / 系数裁决边界。

允许修改：

- 右侧 AI Dock 顶部身份区域布局。
- AI Dock 折叠入口视觉。
- 前端样式文件。
- 新增独立 React 组件和 CSS。
- 增加状态文案，不改变业务结论。

## 十一、素材包说明

配套素材包：

```text
zhisuan_avatar_minimal_unified_assets.zip
```

包含：

```text
README.md
ZhisuanAvatar.tsx
ZhisuanAvatar.css
demo.html
zhisuan_avatar_unified.svg
state-map.json
```

说明：

- `zhisuan_avatar_unified.svg` 是统一静态形象参考。
- `demo.html` 可以直接预览同一形象在不同状态下的动效。
- `ZhisuanAvatar.tsx` 是可迁入 React 项目的组件草案。
- `ZhisuanAvatar.css` 包含 idle 呼吸感和不同状态动效。
- 正式实现时以 `ZhisuanAvatar.tsx` 的内联 SVG 为准，不建议用 `<img>` 加载。

## 十二、验收口径

### 12.1 视觉验收

- 所有状态主体形象一致。
- 形象比上一版更简约。
- idle 状态有轻微呼吸感。
- 状态切换不产生“换了一个机器人”的感觉。
- 预警 / 错误 / 成功只通过状态层表达。
- 不出现复杂机械身体、手臂、放大镜、大面积装饰。
- 不出现国企大屏式强发光、粒子、霓虹。

### 12.2 交互验收

- 页面打开后显示 `idle`，能看到轻微呼吸。
- 输入框聚焦后可进入 `listening`。
- AI 请求中进入 `thinking`。
- Excel 转换、经验池预警、重算公式、报告生成时进入 `processing`。
- 有预警或待复核时进入 `warning`。
- 异常时进入 `error`，同时保留文字错误说明。
- 成功后进入 `success`，随后自动回落。
- 折叠态显示 compact 头像，不遮挡业务区。

### 12.3 工程验收

- `npm run frontend:build` 通过。
- 不新增后端接口。
- 不新增重型动画依赖。
- 不改变现有 API 调用、下载、报告、预警、填价结果。
- 支持 `prefers-reduced-motion: reduce`。
- 组件代码集中，便于未来替换为 Lottie / Rive。

## 十三、Codex 执行提示词

```text
请根据《RRD-智算助手形象-极简统一形象呼吸动效版》为造价智算右侧“问问智算”AI 助手增加轻量可动虚拟形象。

本轮目标：
使用一个极简统一形象实现状态可视化。不同状态不得更换机器人主体，只允许状态环、状态点、扫描线、勾号、叹号、错误符号变化。

核心要求：
1. 新增 `frontend/src/components/ZhisuanAvatar.tsx`。
2. 新增 `frontend/src/components/ZhisuanAvatar.css`，或并入现有样式文件，但组件样式必须集中。
3. SVG 必须内联在 React 组件中，不能只用 `<img src="xxx.svg">`。
4. 所有状态必须共用同一套 SVG DOM，不允许每个状态加载不同 SVG 主图。
5. 形象要比上一版更简约：圆角芯片 / 胶囊、内屏幕、两个眼点、状态环、右上状态点即可。
6. idle 状态必须有呼吸感：
   - 周期 3.0s 到 3.6s；
   - translateY 不超过 1.2px；
   - scale 不超过 1.012；
   - 低干扰，不闪烁。
7. 必须支持 `prefers-reduced-motion: reduce`。
8. 不新增后端接口。
9. 不新增 Live2D、3D、Rive、Lottie 等重依赖。
10. 不改变 Excel 填价、三数字匹配、经验池预警、Word 报告、下载、知识库检索和行级复核逻辑。
11. 状态只从现有前端状态派生。
12. 折叠态显示 compact 头像，不遮挡表格和按钮。

状态优先级：
`error > thinking > processing > warning > success > listening > idle`

验收：
1. 打开页面后 idle 状态有轻微呼吸。
2. 所有状态看起来仍是同一个智算形象。
3. 输入框聚焦后可进入 listening。
4. AI 请求中进入 thinking。
5. Excel 转换、经验池预警、重算公式、报告生成时进入 processing。
6. 有预警或待复核时进入 warning。
7. 异常时进入 error，并保留文字错误说明。
8. 成功后进入 success，随后自动回落。
9. `npm run frontend:build` 通过。
10. 不影响原有功能。
```

## 十四、后续升级

第一阶段稳定后，再考虑：

1. 做自有 Lottie，但仍保持统一形象。
2. 做 Rive 状态机，但仍保持同一角色主体。
3. 增加“查库命中 / 无依据 / 生成报告 / 行级复核”等细分状态。
4. 增加“动效强度：关闭 / 低 / 标准”的用户设置。

当前阶段不做以上升级。
