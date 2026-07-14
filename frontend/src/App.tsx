import { CSSProperties, ChangeEvent, DragEvent, KeyboardEvent, MouseEvent, PointerEvent as ReactPointerEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Bot,
  BookOpen,
  ChevronDown,
  CheckCircle2,
  Columns3,
  Database,
  Download,
  ExternalLink,
  FileSpreadsheet,
  FileText,
  Settings,
  Loader2,
  MessageSquareText,
  MonitorUp,
  PanelTop,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";
import { DaweibaLayoutV2 } from "./DaweibaLayoutV2";
import ZhisuanAvatar, { type ZhisuanAvatarState } from "./components/ZhisuanAvatar";
import WordReportPreview, { type WordReportPreviewStatus } from "./components/report/WordReportPreview";

const DEFAULT_API_BASE = import.meta.env.DEV ? "http://127.0.0.1:8000" : "";
const API_BASE = import.meta.env.VITE_API_BASE ?? DEFAULT_API_BASE;
const API_BASE_LABEL = API_BASE.replace(/^https?:\/\//, "") || window.location.host;
const DIGITAL_PROJECT_ASSISTANT_URL =
  import.meta.env.VITE_DIGITAL_PROJECT_ASSISTANT_URL || "http://127.0.0.1:5175/?embed=1&theme=light";
const APP_NAME = "造价智算";
const APP_SUBTITLE = "工程造价辅助智能体";
const OLD_APP_NAME = "管勘智算";
const OLD_APP_SUBTITLES = [
  "长输管道勘察测量最高投标限价智能体",
  "长输管道工程勘察测量最高投标限价编制智能体",
  "长输管道勘察测量最高投标限价编制智能体",
];
const APP_VERSION = "v5.8.17";
const WELCOME_SCREEN_VARIANT = "light" as "light" | "dark";
const KNOWLEDGE_QA_ENTRY_COUNT = 3922;
const KNOWLEDGE_QA_SOURCE_COUNT = 17;
const PRICE_KNOWLEDGE_ROW_COUNT = 560;
const FORCE_KNOWLEDGE_PREFIXES = ["查库：", "查库:", "@知识库", "#知识库"] as const;
const ROW_AI_CONTEXT_FIELD_GROUPS = [
  { label: "匹配状态", aliases: ["匹配状态"] },
  { label: "匹配说明", aliases: ["匹配说明", "填价说明", "匹配报告"] },
  { label: "候选数量", aliases: ["候选数量", "候选数"] },
  { label: "预警参数", aliases: ["预警参数"] },
  { label: "预警细节", aliases: ["预警细节"] },
  { label: "基价/单价", aliases: ["基价", "单价", "输出-价格列", "价格"] },
  { label: "实物工作费调整系数", aliases: ["实物工作费调整系数", "实物工作系数", "实物工作费系数", "实物系数", "工作费系数"] },
  { label: "技术工作费调整系数", aliases: ["技术工作费调整系数", "技术系数"] },
] as const;
const LLM_PRESETS = [
  {
    id: "deepseek-v4-flash",
    name: "深度求索",
    description: "官方 deepseek-v4-flash",
    provider: "deepseek",
    model: "deepseek-v4-flash",
    baseUrl: "https://api.deepseek.com",
  },
  {
    id: "siliconflow-deepseek-v4-flash",
    name: "硅基流动",
    description: "deepseek-ai/DeepSeek-V4-Flash",
    provider: "siliconflow",
    model: "deepseek-ai/DeepSeek-V4-Flash",
    baseUrl: "https://api.siliconflow.cn/v1/chat/completions",
  },
] as const;

type LlmSettings = {
  provider: string;
  model: string;
  baseUrl: string;
};

const DEFAULT_LLM_SETTINGS: LlmSettings = {
  provider: LLM_PRESETS[0].provider,
  model: LLM_PRESETS[0].model,
  baseUrl: LLM_PRESETS[0].baseUrl,
};
const PROCESSING_STAGES = [
  {
    min: 0,
    title: "读取输入",
    shortLabel: "读取中",
    description: "正在读取输入表、列映射和候选 sheet。",
  },
  {
    min: 28,
    title: "结构化匹配",
    shortLabel: "匹配中",
    description: "正在按知识库和规则层执行基价、实物工作费系数、技术工作费系数匹配。",
  },
  {
    min: 68,
    title: "Excel 公式重算中",
    shortLabel: "重算中",
    description: "正在调用 Excel 重算费用汇总和公式缓存，确保报告金额与输出表一致。",
  },
  {
    min: 86,
    title: "生成报告与预览",
    shortLabel: "收尾中",
    description: "正在刷新表格预览并生成 Word 报告；经验池预警可在转换完成后手动运行。",
  },
] as const;
const MAPPING_FIELDS = [
  "要素1",
  "要素2",
  "要素3",
  "要素4",
  "要素5",
  "单位",
  "输出-价格列",
  "输出-实物工作费调整系数",
  "输出-技术工作费调整系数",
] as const;
const REQUIRED_MAPPING_FIELDS = ["要素1", "单位", "输出-价格列"] as const;
const ELEMENT_FIELDS = ["要素1", "要素2", "要素3", "要素4", "要素5"] as const;
const EMPTY_ELEMENT_COLUMN = "空元素列";
const OUTPUT_ROW_FILTER_STORAGE_KEY = "guankanzhisuan-output-row-filter-settings";
const WELCOME_SCREEN_HIDDEN_STORAGE_KEY = "guankanzhisuan-welcome-screen-hidden";
const WELCOME_SCREEN_VERSION_STORAGE_KEY = "guankanzhisuan-welcome-screen-version";
const WELCOME_SCREEN_VERSION = "brand-v5.8.17";
const ZHISUAN_QUICK_SETTINGS_VERSION = 2;
const LEFT_COLUMN_COLLAPSED_STORAGE_KEY = "guankanzhisuan-left-column-collapsed";
type MappingField = (typeof MAPPING_FIELDS)[number];
type ColumnMapping = Record<MappingField, string>;
type DaweibaModuleId = "fill" | "preview" | "experience" | "workload" | "report" | "knowledge" | "collaboration" | "digital-project-assistant";

const UI_TUNER_TARGETS = [
  { id: "hero", name: "主标题区域" },
  { id: "input-panel", name: "上传输入面板" },
  { id: "drop-zone", name: "上传拖拽框" },
  { id: "primary-button", name: "主按钮" },
  { id: "secondary-button", name: "选文件按钮" },
  { id: "mapping-panel", name: "列映射面板" },
  { id: "settings-button", name: "设置按钮" },
  { id: "section-heading", name: "模块标题头" },
  { id: "sheet-tabs", name: "Sheet 标签栏" },
  { id: "mapping-field", name: "字段映射项" },
  { id: "check-field", name: "复选项" },
  { id: "mapping-row-field", name: "映射行控制" },
  { id: "download-row", name: "下载按钮区" },
  { id: "result-card", name: "结果提示卡" },
  { id: "brief-panel", name: "转换概览面板" },
  { id: "summary-hero", name: "转换百分比卡片" },
  { id: "stats-grid", name: "指标卡片区域" },
  { id: "preview-section", name: "预览模块" },
  { id: "preview-window", name: "预览窗口" },
  { id: "preview-summary-footer", name: "预览底部摘要" },
  { id: "warning-action-row", name: "预警操作条" },
  { id: "warning-panel", name: "预警信息卡片" },
  { id: "experience-section", name: "经验池模块" },
  { id: "experience-panel", name: "经验池内容面板" },
  { id: "experience-file-card", name: "经验池文件卡片" },
  { id: "experience-field-row", name: "经验池字段行" },
  { id: "experience-mapping-panel", name: "经验池映射面板" },
  { id: "workload-section", name: "工作量模块" },
  { id: "workload-panel", name: "工作量内容面板" },
  { id: "workload-file-grid", name: "工作量文件区域" },
  { id: "workload-file-card", name: "工作量文件卡片" },
  { id: "workload-field-row", name: "工作量字段行" },
  { id: "workload-mapping-panel", name: "工作量映射面板" },
  { id: "workload-source-mapping-panel", name: "工作量表映射子面板" },
  { id: "workload-target-mapping-panel", name: "控制价表映射子面板" },
  { id: "ai-dock", name: "智算助手" },
  { id: "ai-status-grid", name: "AI 状态卡片区" },
  { id: "llm-panel", name: "AI 风险操作区" },
] as const;
type UiTunerTargetId = (typeof UI_TUNER_TARGETS)[number]["id"];

const UI_TEXT_TARGETS = [
  { id: "hero.title", name: `主标题：${APP_NAME}`, defaultText: APP_NAME },
  { id: "hero.subtitle", name: `副标题：${APP_SUBTITLE}`, defaultText: APP_SUBTITLE },
  { id: "hero.lead", name: "首页说明：本地规则引擎硬校验匹配...", defaultText: "本地规则引擎硬校验匹配，生成填价结果、Word 报告和可核验预览。" },
  { id: "upload.title.empty", name: "上传区标题：拖拽 Excel 到这里", defaultText: "拖拽 Excel 到这里" },
  { id: "upload.subtitle.empty", name: "上传区说明：或点击选择 .xlsx 文件", defaultText: "或点击选择 .xlsx 文件" },
  { id: "button.process.ready", name: "按钮：开始转换", defaultText: "开始转换" },
  { id: "button.process.running", name: "按钮：正在转换", defaultText: "正在转换" },
  { id: "button.pick-file", name: "按钮：选文件", defaultText: "选文件" },
  { id: "mapping.title", name: "列映射标题：列映射设置", defaultText: "列映射设置" },
  { id: "summary.title", name: "概览标题：转换后概览", defaultText: "转换后概览" },
  { id: "preview.title", name: "预览标题：可视化表格窗口", defaultText: "可视化表格窗口" },
  { id: "experience.title", name: "经验池标题：独立经验池导入与预警数据", defaultText: "独立经验池导入与预警数据" },
  { id: "workload.title", name: "工作量模块标题：原始工作量抓取模块", defaultText: "原始工作量抓取模块" },
  { id: "ai.eyebrow", name: "AI 小标题：随行助手", defaultText: "随行助手" },
  { id: "ai.title", name: "AI 标题：智算", defaultText: "智算" },
] as const;
type UiTextTargetId = (typeof UI_TEXT_TARGETS)[number]["id"];

function isUiTextTargetId(value: string | undefined): value is UiTextTargetId {
  return Boolean(value && UI_TEXT_TARGETS.some((item) => item.id === value));
}

function workloadFieldLabel(field: string) {
  return WORKLOAD_FIELD_DISPLAY_LABELS[field] ?? field;
}

function workloadLogPreviewTone(message: string) {
  if (message.includes("一对多预警")) return "duplicate";
  if (message.includes("未抓取")) return "missing";
  return "matched";
}

function isWorkloadIssueLog(item: WorkloadLogPreviewItem) {
  return (
    item.status === "warning"
    || item.message.includes("一对多")
    || item.message.includes("未抓取")
    || item.message.includes("未匹配")
  );
}

type UiStyleValues = {
  paddingX?: number;
  paddingY?: number;
  fontSize?: number;
  radius?: number;
  gap?: number;
  marginTop?: number;
  opacity?: number;
};

type UiPreferences = {
  enabled: boolean;
  styles: Record<string, UiStyleValues>;
  text: Record<string, string>;
};

type UiPreferencesPayload = {
  defaults: UiPreferences;
  preferences: Partial<UiPreferences>;
  file_path: string;
};

const EMPTY_UI_PREFERENCES: UiPreferences = {
  enabled: false,
  styles: {},
  text: {},
};

type ReviewRow = {
  excel_row: number;
  status: string;
  message: string;
  values: Record<string, string | number | null>;
};

type TablePreview = {
  sheet_name?: string;
  header_row?: number;
  headers: Array<string | number | null>;
  rows: Array<Array<string | number | null>>;
  row_numbers?: number[];
};

type ManualEditRecord = {
  sheet: string;
  row_number: number;
  column_number: number;
  column_letter: string;
  header: string;
  original_value: string | number | boolean | null;
  new_value: string | number | boolean | null;
  updated_at: string;
};

type Summary = {
  total_data_rows: number;
  price_column: string;
  filled_rows: number;
  matched_rows: number;
  unchanged_rows: number;
  review_rows: number;
  conflict_rows: number;
  physical_matched_rows: number;
  physical_experience_rows: number;
  physical_review_rows: number;
  technical_matched_rows: number;
  technical_experience_rows: number;
  technical_review_rows: number;
  output_excel: string;
  output_report: string;
  report_text: string;
  table_preview: TablePreview & {
    sheets?: TablePreview[];
  };
  review_details: ReviewRow[];
  warning_summary?: WarningSummary;
  warning_details?: WarningDetail[];
  matching_status?: "pending" | "completed";
};

type ProcessResult = {
  job_id: string;
  summary: Summary;
  downloads: {
    excel: string;
    report: string;
  };
  manual_edits?: ManualEditRecord[];
  needs_recalculate?: boolean;
};

type FeishuNotificationType = "task_started" | "progress" | "task_completed" | "task_failed";
type FeishuNotificationSwitches = Record<FeishuNotificationType, boolean>;
type FeishuDeliveryRecord = {
  timestamp: string;
  notification_type: FeishuNotificationType | "test";
  success: boolean;
  http_status?: number | null;
  business_code?: number | string | null;
  job_id?: string;
  error?: string;
};
type FeishuWebhookStatus = {
  configured: boolean;
  enabled: boolean;
  security_enabled: boolean;
  active_profile: string;
  profiles: FeishuWebhookProfile[];
  app_url: string;
  notifications: FeishuNotificationSwitches;
  last_delivery?: FeishuDeliveryRecord | null;
};
type FeishuWebhookProfile = { profile_id: string; label: string; host?: string; security_enabled?: boolean };
type FeishuAppBotProfile = { profile_id: string; label: string; app_id_suffix?: string; domain_host?: string };
type FeishuAppBotTask = { task_id: string; file_name: string; status: string; stage: string; error?: string; created_at: string; updated_at: string; risk_total?: number; risk_high?: number; };
type FeishuAppBotStatus = { configured: boolean; enabled: boolean; running: boolean; active_profile: string; profiles: FeishuAppBotProfile[]; connection_mode: string; concurrency: number; retention_days: number; counts: Record<string, number>; current_task?: FeishuAppBotTask | null; recent_tasks: FeishuAppBotTask[]; };
type FeishuBotConsoleEvent = {
  timestamp: string;
  level: "info" | "success" | "warning" | "error";
  category: "process" | "config" | "connection" | "message" | "knowledge" | "task";
  message: string;
  task_id?: string;
  profile_id?: string;
  source?: string;
};

const DEFAULT_FEISHU_NOTIFICATION_SWITCHES: FeishuNotificationSwitches = {
  task_started: true,
  progress: true,
  task_completed: true,
  task_failed: true,
};

const FEISHU_NOTIFICATION_LABELS: Record<FeishuDeliveryRecord["notification_type"], string> = {
  test: "测试",
  task_started: "任务开始",
  progress: "任务进度",
  task_completed: "任务完成",
  task_failed: "任务失败",
};

const FEISHU_BOT_CONSOLE_CATEGORY_LABELS: Record<FeishuBotConsoleEvent["category"], string> = {
  process: "进程",
  config: "配置",
  connection: "连接",
  message: "消息",
  knowledge: "知识库",
  task: "任务",
};

function formatFeishuConsoleTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

const EMPTY_FEISHU_WEBHOOK_STATUS: FeishuWebhookStatus = {
  configured: false,
  enabled: false,
  security_enabled: false,
  active_profile: "default",
  profiles: [],
  app_url: "",
  notifications: DEFAULT_FEISHU_NOTIFICATION_SWITCHES,
  last_delivery: null,
};

type PreviewCellUpdateResult = ProcessResult & {
  manual_edit: ManualEditRecord;
  formula_recalculated?: boolean;
  needs_recalculate?: boolean;
};

type ColumnOption = {
  letter: string;
  header: string;
  label: string;
};

type InspectResult = {
  header_row: number;
  headers: string[];
  columns: ColumnOption[];
  suggested_mapping: ColumnMapping;
  sheets?: SheetInspectResult[];
};

type SheetInspectResult = {
  sheet_name: string;
  enabled: boolean;
  header_row: number;
  headers: string[];
  columns: ColumnOption[];
  suggested_mapping: ColumnMapping;
};

type SheetMappingConfig = {
  sheet_name: string;
  enabled: boolean;
  header_row: number;
  columns: ColumnOption[];
  column_mapping: ColumnMapping;
};

type ChatMessage = {
  role: "system" | "user" | "assistant";
  content: string;
  id?: string;
  displayContent?: string;
  isTyping?: boolean;
  source?: "model" | "system" | "command" | "thinking";
  rowDetailContext?: RowAiContext;
};

type ZhisuanCommand = "batch-match" | "experience-warning" | "risk-report" | "download-excel" | "download-word";
type ZhisuanQuickKind = "command" | "suggestion";
type ZhisuanQuickItem = {
  id: string;
  label: string;
  prompt: string;
  kind: ZhisuanQuickKind;
  command?: ZhisuanCommand;
  source?: "builtin" | "custom";
};
type ZhisuanQuickSettings = {
  enabledIds: string[];
  customPrompts: string[];
  autoHide: boolean;
  version: number;
};
type ZhisuanDockStyle = "default" | "analysis" | "companion";
type ZhisuanDockVisibilityKey = "rowReview" | "conclusion" | "review" | "warning" | "ruleNotice" | "debugInfo";
type ZhisuanDockVisibilitySettings = Record<ZhisuanDockVisibilityKey, boolean>;
type ZhisuanWindowSettings = {
  chatHeight: number;
  dockWidth: number;
  useViewportHeight: boolean;
  quickSettings: ZhisuanQuickSettings;
  dockVisibility: ZhisuanDockVisibilitySettings;
  welcomeMessage: string;
  dockStyle: ZhisuanDockStyle;
};
type ZhisuanWindowSettingsPayload = Partial<Omit<ZhisuanWindowSettings, "quickSettings" | "dockVisibility">> & {
  quickSettings?: Partial<ZhisuanQuickSettings>;
  dockVisibility?: Partial<ZhisuanDockVisibilitySettings>;
};

const ZHISUAN_WELCOME_MESSAGE =
  "你好，我是智算。你把 Excel 拖进来，我负责盯住字段、转换、预警、报告和每一行复核。价格还是由结构化规则裁决，我只做解释、总结和提醒。";
const ZHISUAN_WORD_REPORT_ACTION = "[[ZHISUAN_WORD_REPORT_ACTION]]";
const ZHISUAN_PREVIEW_ACTION = "[[ZHISUAN_PREVIEW_ACTION]]";
const ZHISUAN_BATCH_MATCH_ACTION = "[[ZHISUAN_BATCH_MATCH_ACTION]]";

const ZHISUAN_BUILTIN_QUICK_ITEMS: ZhisuanQuickItem[] = [
  { id: "batch-match", label: "批量匹配", prompt: "批量匹配", kind: "command", command: "batch-match" },
  { id: "experience-warning", label: "经验池预警分析", prompt: "经验池预警分析", kind: "command", command: "experience-warning" },
  { id: "risk-report", label: "输出风险报告", prompt: "输出风险报告", kind: "command", command: "risk-report" },
  { id: "download-excel", label: "输出excel表格", prompt: "输出excel表格", kind: "command", command: "download-excel" },
  { id: "download-word", label: "输出word报告", prompt: "输出word报告", kind: "command", command: "download-word" },
];
const ZHISUAN_QUICK_PROMPT_BLOCKLIST = new Set([
  "哪些行优先复核？",
  "为什么这行待复核？",
  "本次预警主要集中在哪？",
  "生成 AI 审查摘要",
  "生成AI审查摘要",
  "解释第二层经验提示",
  "第二层经验提示是什么意思？",
  "解释附加系数不能连乘",
  "解释系数",
  "附加调整系数为什么不能连乘？",
]);
const DEFAULT_ZHISUAN_QUICK_SETTINGS: ZhisuanQuickSettings = {
  enabledIds: ZHISUAN_BUILTIN_QUICK_ITEMS.map((item) => item.id),
  customPrompts: ["@知识库："],
  autoHide: true,
  version: ZHISUAN_QUICK_SETTINGS_VERSION,
};
const DEFAULT_ZHISUAN_DOCK_VISIBILITY_SETTINGS: ZhisuanDockVisibilitySettings = {
  rowReview: false,
  conclusion: false,
  review: false,
  warning: false,
  ruleNotice: false,
  debugInfo: false,
};
const ZHISUAN_DOCK_VISIBILITY_OPTIONS: Array<{
  id: ZhisuanDockVisibilityKey;
  name: string;
  description: string;
}> = [
  { id: "rowReview", name: "行级AI复核模块", description: "显示独立行级复核面板；关闭时点击表格 AI 只把问题送到“问问智算”。" },
  { id: "conclusion", name: "本次结论", description: "显示填价完成数和本次结论摘要。" },
  { id: "review", name: "待复核", description: "显示待复核数量和复核提醒。" },
  { id: "warning", name: "预警", description: "显示经验池预警运行状态。" },
  { id: "ruleNotice", name: "智算只做解释与提示", description: "显示结构化规则裁决边界说明。" },
  { id: "debugInfo", name: "调试信息", description: "显示最近 10 次大模型请求内容。" },
];
const ZHISUAN_DOCK_STYLE_OPTIONS: Array<{ id: ZhisuanDockStyle; name: string; description: string }> = [
  { id: "default", name: "默认", description: "保持当前页面一致风格" },
  { id: "analysis", name: "智算分析台", description: "更像专业审查面板" },
  { id: "companion", name: "随行光带", description: "更像贴身 AI 助手" },
];
const DEFAULT_ZHISUAN_WINDOW_SETTINGS: ZhisuanWindowSettings = {
  chatHeight: 430,
  dockWidth: 400,
  useViewportHeight: false,
  quickSettings: DEFAULT_ZHISUAN_QUICK_SETTINGS,
  dockVisibility: DEFAULT_ZHISUAN_DOCK_VISIBILITY_SETTINGS,
  welcomeMessage: ZHISUAN_WELCOME_MESSAGE,
  dockStyle: "default",
};
const ZHISUAN_AVATAR_STATE_LABELS: Record<ZhisuanAvatarState, string> = {
  idle: "待命",
  listening: "听取输入",
  thinking: "思考中",
  processing: "处理中",
  warning: "需复核",
  error: "异常",
  success: "已完成",
};

type LlmDebugInfo = {
  provider: string;
  model: string;
  base_url: string;
  temperature: number;
  max_tokens: number;
  messages: ChatMessage[];
  prompt_markdown?: string;
};

type LlmDebugRecord = LlmDebugInfo & {
  source: string;
  createdAt: string;
};

type KnowledgeSource = {
  source_file: string;
  source_type: string;
  title_path: string;
  snippet: string;
  score: number;
  module?: string;
};

type KnowledgeAskResponse = {
  answer: string;
  sources: KnowledgeSource[];
  evidence_found: boolean;
  forced_knowledge?: boolean;
  debug?: LlmDebugInfo | null;
};

type PreviewColumn = {
  label: string;
  index: number;
  kind: "text" | "number" | "status" | "note" | "warning";
};

type PreviewCellEditState = {
  sheetName: string;
  sourceIndex: number;
  rowNumber: number;
  columnIndex: number;
  columnNumber: number;
  originalValue: string;
  draftValue: string;
};

type PreviewColumnPreferences = {
  defaultLabels: string[];
  sheetOverrides: Record<string, string[]>;
  headerRows: Record<string, number>;
  maxDisplayChars: number;
  columnWidths: Record<string, Record<string, number>>;
};

type PreviewColumnPreferencesPayload = {
  defaults: Partial<PreviewColumnPreferences>;
  preferences: Partial<PreviewColumnPreferences>;
  file_path: string;
};

type ProjectDefaultSettingsPayload = {
  file_path?: string;
  previewColumns?: Partial<PreviewColumnPreferences>;
  zhisuanWindow?: ZhisuanWindowSettingsPayload;
  inputMapping?: {
    headerRow?: number;
    outputMatchReport?: boolean;
    onlyMatchRowsWithValue?: boolean;
    matchValueFilterField?: string;
    mergeVerticalCells?: boolean;
    mergeHorizontalCells?: boolean;
    fieldPreferences?: Partial<Record<MappingField, string[]>>;
  };
  workloadCapture?: {
    selectedFields?: string[];
    writeMode?: string;
    onlyCaptureRowsWithValue?: boolean;
    valueFilterField?: string;
    source?: {
      adjacentFallbackEnabled?: boolean;
      elementSequenceEnabled?: boolean;
      fieldPreferences?: Partial<Record<WorkloadSourceField, string[]>>;
    };
    target?: {
      adjacentFallbackEnabled?: boolean;
      elementSequenceEnabled?: boolean;
      fieldPreferences?: Partial<Record<WorkloadTargetField, string[]>>;
    };
  };
};

type RowAiContext = {
  sheetName: string;
  rowNumber: number;
  values: Record<string, string>;
  previewRow: Array<string | number | null>;
  sourceIndex: number;
};

type WarningSummary = {
  pool_enabled: boolean;
  executed?: boolean;
  candidate_rows?: number;
  checked_rows: number;
  no_comparable_rows?: number;
  warning_rows: number;
  high_rows: number;
  low_rows?: number;
  medium_rows?: number;
  metric_counts?: Record<string, number>;
  match_mode_counts?: Record<string, number>;
  low_risk_threshold_percent?: number;
  high_risk_threshold_percent?: number;
  summary_text?: string;
};

type WarningDetail = {
  sheet_name: string;
  excel_row: number;
  metric: string;
  current_value: number;
  experience_values: number[];
  experience_average?: number;
  experience_min: number;
  experience_max: number;
  sample_count: number;
  deviation_percent?: number;
  low_risk_threshold_percent?: number;
  high_risk_threshold_percent?: number;
  severity: "high" | "low" | "none" | string;
  severity_label?: string;
  message: string;
  suggested_action?: string;
  row_key?: string;
  match_mode?: string;
  match_mode_detail?: string;
  experience_values_text?: string;
  experience_range_text?: string;
  source_rows: Array<{
    source_file: string;
    source_sheet: string;
    source_row: number;
    value: number;
    note?: string;
  }>;
};

type ExperienceImportSummary = {
  pool_path: string;
  source_file: string;
  imported_rows: number;
  skipped_rows: number;
  selected_fields: string[];
};

type WarningProgress = {
  status: "idle" | "running" | "completed" | "failed" | string;
  processed_rows: number;
  total_rows: number;
  matched_rows: number;
  warning_rows: number;
  error?: string;
};

type ExperienceWarningSettings = {
  low_risk_warning_ratio: number;
  high_risk_warning_ratio: number;
  only_check_rows_with_value: boolean;
  value_filter_field: WarningFilterField;
};

const WARNING_FILTER_FIELDS = ["数量"] as const;
type WarningFilterField = (typeof WARNING_FILTER_FIELDS)[number];
type OutputRowFilterSettings = {
  enabled: boolean;
  value_filter_field: WarningFilterField;
};

const EXPERIENCE_FIELD_OPTIONS = ["基价", "实物工作费调整系数", "技术工作费调整系数"] as const;
const EXPERIENCE_MAPPING_FIELDS = [
  "要素1",
  "要素2",
  "要素3",
  "要素4",
  "要素5",
  "单位",
  "基价",
  "工程量",
  "实物工作费调整系数",
  "技术工作费调整系数",
  "其他参数1",
  "其他参数2",
  "原表备注1",
  "原表备注2",
  "原表备注3",
] as const;
const REQUIRED_EXPERIENCE_FIELDS = ["要素1", "单位"] as const;
type ExperienceMappingField = (typeof EXPERIENCE_MAPPING_FIELDS)[number];
type ExperienceColumnMapping = Record<ExperienceMappingField, string>;
const EMPTY_WARNING_PROGRESS: WarningProgress = {
  status: "idle",
  processed_rows: 0,
  total_rows: 0,
  matched_rows: 0,
  warning_rows: 0,
};
const DEFAULT_EXPERIENCE_WARNING_SETTINGS: ExperienceWarningSettings = {
  low_risk_warning_ratio: 5,
  high_risk_warning_ratio: 20,
  only_check_rows_with_value: true,
  value_filter_field: "数量",
};
const DEFAULT_OUTPUT_ROW_FILTER_SETTINGS: OutputRowFilterSettings = {
  enabled: true,
  value_filter_field: DEFAULT_EXPERIENCE_WARNING_SETTINGS.value_filter_field,
};
const WARNING_FILTER_FIELD_ALIASES: Record<WarningFilterField, string[]> = {
  数量: ["数量", "工程量", "工程数量", "工程量合计"],
};
type ExperienceFieldPreferences = Record<ExperienceMappingField, string[]>;

type ExperienceFieldPreferencesPayload = {
  fields: ExperienceMappingField[];
  defaults: Partial<Record<ExperienceMappingField, string[]>>;
  preferences: Partial<Record<ExperienceMappingField, string[]>>;
  file_path: string;
};

type ExperienceWarningSettingsPayload = {
  defaults: ExperienceWarningSettings;
  settings: ExperienceWarningSettings;
  filter_fields?: WarningFilterField[];
  file_path: string;
};

type ExperienceSheetInspectResult = {
  sheet_name: string;
  enabled: boolean;
  header_row: number;
  headers: string[];
  columns: ColumnOption[];
  suggested_mapping: ExperienceColumnMapping;
};

type ExperienceInspectResult = {
  header_row: number;
  headers: string[];
  columns: ColumnOption[];
  suggested_mapping: ExperienceColumnMapping;
  sheets?: ExperienceSheetInspectResult[];
};

type ExperienceSheetMappingConfig = {
  sheet_name: string;
  enabled: boolean;
  header_row: number;
  columns: ColumnOption[];
  column_mapping: ExperienceColumnMapping;
};

type InputFieldPreferences = Record<MappingField, string[]>;

type InputFieldPreferencesPayload = {
  fields: MappingField[];
  defaults: Partial<Record<MappingField, string[]>>;
  preferences: Partial<Record<MappingField, string[]>>;
  mapping_defaults?: ProjectDefaultSettingsPayload["inputMapping"];
  file_path: string;
};

const WORKLOAD_SOURCE_FIELDS = [
  "要素1",
  "要素2",
  "要素3",
  "要素4",
  "要素5",
  "单位",
  "数量",
  "实物工作费调整系数",
  "技术工作费调整系数",
  "委托方备注",
] as const;
const WORKLOAD_TARGET_FIELDS = [
  "要素1",
  "要素2",
  "要素3",
  "要素4",
  "要素5",
  "单位",
  "数量(信息抓取)",
  "实物工作费调整系数(信息抓取)",
  "技术工作费调整系数(信息抓取)",
  "委托方备注(信息抓取)",
  "抓取日志",
] as const;
const WORKLOAD_CAPTURE_FIELD_OPTIONS = [
  "数量(信息抓取)",
  "实物工作费调整系数(信息抓取)",
  "技术工作费调整系数(信息抓取)",
  "委托方备注(信息抓取)",
] as const;
const WORKLOAD_OPTIONAL_TARGET_FIELDS = [
  "实物工作费调整系数(信息抓取)",
  "技术工作费调整系数(信息抓取)",
  "委托方备注(信息抓取)",
] as const;
const REQUIRED_WORKLOAD_KEY_FIELDS = ["要素1", "单位"] as const;
const WORKLOAD_TARGET_TO_SOURCE_FIELD: Record<string, string> = {
  "数量(信息抓取)": "数量",
  "实物工作费调整系数(信息抓取)": "实物工作费调整系数",
  "技术工作费调整系数(信息抓取)": "技术工作费调整系数",
  "委托方备注(信息抓取)": "委托方备注",
};
const WORKLOAD_FIELD_DISPLAY_LABELS: Record<string, string> = {
  数量: "数量（待抓取）",
  实物工作费调整系数: "实物工作费调整系数（待抓取）",
  技术工作费调整系数: "技术工作费调整系数（待抓取）",
  委托方备注: "委托方备注（待抓取）",
  "数量(信息抓取)": "数量（待抓取）",
  "实物工作费调整系数(信息抓取)": "实物工作费调整系数（待抓取）",
  "技术工作费调整系数(信息抓取)": "技术工作费调整系数（待抓取）",
  "委托方备注(信息抓取)": "委托方备注（待抓取）",
};
type WorkloadSourceField = (typeof WORKLOAD_SOURCE_FIELDS)[number];
type WorkloadTargetField = (typeof WORKLOAD_TARGET_FIELDS)[number];
type WorkloadRole = "source" | "target";
type WorkloadSourceMapping = Record<WorkloadSourceField, string>;
type WorkloadTargetMapping = Record<WorkloadTargetField, string>;
type WorkloadFieldPreferences = Record<WorkloadSourceField, string[]>;
type WorkloadTargetFieldPreferences = Record<WorkloadTargetField, string[]>;

type WorkloadFieldPreferencesPayload = {
  fields: string[];
  defaults: Partial<Record<string, string[]>>;
  preferences: Partial<Record<string, string[]>>;
  adjacent_fallback_enabled?: boolean;
  element_sequence_enabled?: boolean;
  file_path: string;
};

type WorkloadSheetInspectResult = {
  sheet_name: string;
  enabled: boolean;
  header_row: number;
  headers: string[];
  columns: ColumnOption[];
  suggested_mapping: Record<string, string>;
};

type WorkloadInspectResult = {
  header_row: number;
  headers: string[];
  columns: ColumnOption[];
  suggested_mapping: Record<string, string>;
  sheets?: WorkloadSheetInspectResult[];
};

type WorkloadSheetMappingConfig<T extends Record<string, string>> = {
  sheet_name: string;
  enabled: boolean;
  header_row: number;
  columns: ColumnOption[];
  column_mapping: T;
};

type WorkloadCaptureSummary = {
  source_file: string;
  target_file?: string;
  output_workload?: string;
  output_target?: string;
  selected_fields: string[];
  source_rows: number;
  target_rows: number;
  filled_rows: number;
  overwritten_rows?: number;
  skipped_existing_rows?: number;
  written_cells?: number;
  overwritten_cells?: number;
  skipped_existing_cells?: number;
  warning_rows: number;
  unmatched_source_rows: number;
  duplicate_warning_rows: number;
  write_mode?: "conservative" | "overwrite" | string;
  issue_log_preview?: WorkloadLogPreviewItem[];
  log_preview: WorkloadLogPreviewItem[];
};

type WorkloadLogPreviewItem = {
  sheet_name: string;
  excel_row: number;
  status: string;
  message: string;
};

type RiskItem = {
  id: string;
  source: string;
  severity: string;
  severity_label?: string;
  risk_type: string;
  title: string;
  sheet_name?: string;
  excel_row?: number;
  metric?: string;
  message: string;
  suggested_action?: string;
  key_text?: string;
  current_value?: string | number;
  reference_value?: string | number;
  deviation_percent?: string | number;
};

type RiskSummaryPayload = {
  summary: {
    total: number;
    severity_counts: Record<string, number>;
    type_counts: Record<string, number>;
  };
  items: RiskItem[];
};

type GovernanceIssue = {
  category: string;
  title?: string;
  severity: string;
  sheet?: string;
  row?: number;
  key_text?: string;
  message: string;
  suggestion: string;
};

type GovernanceReport = {
  report_path?: string;
  summary: {
    total_rows: number;
    valid_key_rows: number;
    issue_count: number;
    categories: Record<string, number>;
  };
  issues: GovernanceIssue[];
};

type FillAssistCandidate = {
  id: string;
  source: string;
  source_label: string;
  value: string | number;
  metric: string;
  confidence: string;
  confidence_label: string;
  similarity?: number;
  sample_count?: number;
  reason: string;
  risk_tips: string[];
  basis: string;
};

type StandardTraceItem = {
  kind: string;
  title: string;
  text: string;
  source: string;
  source_rows?: Array<Record<string, string | number | null>>;
};

type FillAssistPayload = {
  context: {
    sheet_name: string;
    excel_row: number;
    target_header: string;
    target_column: number;
    current_value: string | number | null;
    row: Record<string, string | number | null>;
    diagnostics: Record<string, string | number>;
  };
  candidates: FillAssistCandidate[];
  trace?: StandardTraceItem[];
};

type FillAssistDialogState = FillAssistPayload & {
  trace: StandardTraceItem[];
  selectedCandidateId: string;
  note: string;
  isLoading: boolean;
  isConfirming: boolean;
  error: string;
};

function fillAssistSourceDisplay(candidate: FillAssistCandidate) {
  if (candidate.source === "experience_pool") return "经验池";
  if (candidate.source.startsWith("knowledge")) return "知识库";
  return candidate.source_label || "候选来源";
}

function fillAssistSourceClass(candidate: FillAssistCandidate) {
  if (candidate.source === "experience_pool") return "is-experience";
  if (candidate.source.startsWith("knowledge")) return "is-knowledge";
  return "is-other";
}

function standardTraceKindClass(trace: StandardTraceItem) {
  if (trace.kind.includes("经验")) return "is-experience";
  if (trace.kind.includes("匹配")) return "is-match";
  return "is-rule";
}

type PreviewJumpTarget = {
  sheetName: string;
  excelRow: number;
  metric?: string;
};

type WorkloadCaptureResult = {
  job_id: string;
  summary: WorkloadCaptureSummary;
  downloads?: {
    workload?: string;
    target?: string;
  };
};

type WorkloadApplyToCurrentResult = ProcessResult & {
  workload_summary: WorkloadCaptureSummary;
  workload_downloads?: {
    workload?: string;
  };
};

const EMPTY_MAPPING = MAPPING_FIELDS.reduce(
  (mapping, field) => ({ ...mapping, [field]: "" }),
  {} as ColumnMapping,
);
const EMPTY_INPUT_FIELD_PREFERENCES = MAPPING_FIELDS.reduce(
  (mapping, field) => ({ ...mapping, [field]: [] }),
  {} as InputFieldPreferences,
);
const EMPTY_EXPERIENCE_MAPPING = EXPERIENCE_MAPPING_FIELDS.reduce(
  (mapping, field) => ({ ...mapping, [field]: "" }),
  {} as ExperienceColumnMapping,
);
const EMPTY_EXPERIENCE_FIELD_PREFERENCES = EXPERIENCE_MAPPING_FIELDS.reduce(
  (mapping, field) => ({ ...mapping, [field]: [] }),
  {} as ExperienceFieldPreferences,
);
const EMPTY_WORKLOAD_SOURCE_MAPPING = WORKLOAD_SOURCE_FIELDS.reduce(
  (mapping, field) => ({ ...mapping, [field]: "" }),
  {} as WorkloadSourceMapping,
);
const EMPTY_WORKLOAD_TARGET_MAPPING = WORKLOAD_TARGET_FIELDS.reduce(
  (mapping, field) => ({ ...mapping, [field]: "" }),
  {} as WorkloadTargetMapping,
);
const EMPTY_WORKLOAD_FIELD_PREFERENCES = WORKLOAD_SOURCE_FIELDS.reduce(
  (mapping, field) => ({ ...mapping, [field]: [] }),
  {} as WorkloadFieldPreferences,
);
const EMPTY_WORKLOAD_TARGET_FIELD_PREFERENCES = WORKLOAD_TARGET_FIELDS.reduce(
  (mapping, field) => ({ ...mapping, [field]: [] }),
  {} as WorkloadTargetFieldPreferences,
);
const DEFAULT_PREVIEW_CELL_MAX_DISPLAY_CHARS = 8;
const MIN_PREVIEW_COLUMN_WIDTH_PX = 72;
const MAX_PREVIEW_COLUMN_WIDTH_PX = 420;
const DEFAULT_CORE_PREVIEW_LABELS = [
  "要素1",
  "要素2",
  "要素3",
  "要素4",
  "要素5",
  "单位",
  "单价",
  "实物工作费调整系数",
  "技术工作费调整系数",
  "预警参数",
  "预警细节",
] as const;

function readInitialLeftColumnCollapsed() {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(LEFT_COLUMN_COLLAPSED_STORAGE_KEY) === "true";
}

function normalizeExperienceFieldPreferences(
  source?: Partial<Record<ExperienceMappingField, string[]>>,
): ExperienceFieldPreferences {
  return EXPERIENCE_MAPPING_FIELDS.reduce((mapping, field) => {
    const values = source?.[field] ?? [];
    const cleaned = values.map((value) => value.trim()).filter(Boolean);
    return { ...mapping, [field]: Array.from(new Set(cleaned)) };
  }, {} as ExperienceFieldPreferences);
}

function normalizeInputFieldPreferences(
  source?: Partial<Record<MappingField, string[]>>,
): InputFieldPreferences {
  return MAPPING_FIELDS.reduce((mapping, field) => {
    const values = source?.[field] ?? [];
    const cleaned = values.map((value) => value.trim()).filter(Boolean);
    return { ...mapping, [field]: Array.from(new Set(cleaned)) };
  }, {} as InputFieldPreferences);
}

function normalizeWorkloadFieldPreferences(
  source?: Partial<Record<WorkloadSourceField, string[]>>,
): WorkloadFieldPreferences {
  return WORKLOAD_SOURCE_FIELDS.reduce((mapping, field) => {
    const values = source?.[field] ?? [];
    const cleaned = values.map((value) => value.trim()).filter(Boolean);
    return { ...mapping, [field]: Array.from(new Set(cleaned)) };
  }, {} as WorkloadFieldPreferences);
}

function normalizeWorkloadTargetFieldPreferences(
  source?: Partial<Record<WorkloadTargetField, string[]>>,
): WorkloadTargetFieldPreferences {
  return WORKLOAD_TARGET_FIELDS.reduce((mapping, field) => {
    const values = source?.[field] ?? [];
    const cleaned = values.map((value) => value.trim()).filter(Boolean);
    return { ...mapping, [field]: Array.from(new Set(cleaned)) };
  }, {} as WorkloadTargetFieldPreferences);
}

function preferenceText(values: string[]) {
  return values.join("\n");
}

function parsePreferenceText(value: string) {
  return Array.from(
    new Set(
      value
        .replace(/，/g, "\n")
        .replace(/,/g, "\n")
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

function clampPreviewColumnWidth(value: unknown) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return null;
  return Math.max(MIN_PREVIEW_COLUMN_WIDTH_PX, Math.min(MAX_PREVIEW_COLUMN_WIDTH_PX, Math.round(numericValue)));
}

function previewColumnWidthKeys(column: PreviewColumn) {
  const keys = [`#${column.index}`];
  const labelKey = column.label.trim();
  if (labelKey) keys.push(labelKey);
  return Array.from(new Set(keys));
}

function normalizePreviewColumnPreferences(raw?: Partial<PreviewColumnPreferences>): PreviewColumnPreferences {
  const defaultLabels = Array.isArray(raw?.defaultLabels)
    ? Array.from(new Set(raw.defaultLabels.map((value) => String(value).trim()).filter(Boolean)))
    : [...DEFAULT_CORE_PREVIEW_LABELS];
  const rawOverrides = raw?.sheetOverrides && typeof raw.sheetOverrides === "object" ? raw.sheetOverrides : {};
  const sheetOverrides = Object.entries(rawOverrides).reduce<Record<string, string[]>>((mapping, [sheetName, labels]) => {
    if (!Array.isArray(labels)) return mapping;
    const cleaned = Array.from(new Set(labels.map((value) => String(value).trim()).filter(Boolean)));
    if (!sheetName.trim() || cleaned.length === 0) return mapping;
    return { ...mapping, [sheetName.trim()]: cleaned };
  }, {});
  const rawHeaderRows = raw?.headerRows && typeof raw.headerRows === "object" ? raw.headerRows : {};
  const headerRows = Object.entries(rawHeaderRows).reduce<Record<string, number>>((mapping, [sheetName, value]) => {
    const rowNumber = Number(value);
    if (!sheetName.trim() || !Number.isFinite(rowNumber) || rowNumber < 1) return mapping;
    return { ...mapping, [sheetName.trim()]: Math.floor(rowNumber) };
  }, {});
  const rawMaxDisplayChars = Number(raw?.maxDisplayChars ?? DEFAULT_PREVIEW_CELL_MAX_DISPLAY_CHARS);
  const maxDisplayChars = Number.isFinite(rawMaxDisplayChars)
    ? Math.max(4, Math.min(40, Math.floor(rawMaxDisplayChars)))
    : DEFAULT_PREVIEW_CELL_MAX_DISPLAY_CHARS;
  const rawColumnWidths = raw?.columnWidths && typeof raw.columnWidths === "object" ? raw.columnWidths : {};
  const columnWidths = Object.entries(rawColumnWidths).reduce<Record<string, Record<string, number>>>(
    (mapping, [sheetName, widths]) => {
      if (!sheetName.trim() || !widths || typeof widths !== "object") return mapping;
      const cleanedWidths = Object.entries(widths).reduce<Record<string, number>>((widthMapping, [columnLabel, width]) => {
        const cleanedLabel = columnLabel.trim();
        const clampedWidth = clampPreviewColumnWidth(width);
        if (!cleanedLabel || clampedWidth === null) return widthMapping;
        return { ...widthMapping, [cleanedLabel]: clampedWidth };
      }, {});
      if (Object.keys(cleanedWidths).length === 0) return mapping;
      return { ...mapping, [sheetName.trim()]: cleanedWidths };
    },
    {},
  );
  return { defaultLabels, sheetOverrides, headerRows, maxDisplayChars, columnWidths };
}

function normalizeWarningFilterFieldValue(value: unknown): WarningFilterField {
  const field = String(value ?? "数量").trim();
  return (WARNING_FILTER_FIELDS as readonly string[]).includes(field) ? field as WarningFilterField : "数量";
}

function normalizeWorkloadSourceFieldValue(value: unknown): WorkloadSourceField {
  const field = String(value ?? "数量").trim();
  return (WORKLOAD_SOURCE_FIELDS as readonly string[]).includes(field) ? field as WorkloadSourceField : "数量";
}

function normalizeWorkloadSelectedFields(values: unknown): string[] {
  if (!Array.isArray(values)) return [...WORKLOAD_CAPTURE_FIELD_OPTIONS];
  const selected = values
    .map((value) => String(value).trim())
    .filter((value) => (WORKLOAD_CAPTURE_FIELD_OPTIONS as readonly string[]).includes(value));
  return selected.length > 0 ? Array.from(new Set(selected)) : [...WORKLOAD_CAPTURE_FIELD_OPTIONS];
}

function normalizeWorkloadWriteModeValue(value: unknown): "conservative" | "overwrite" {
  return value === "overwrite" ? "overwrite" : "conservative";
}

function readInitialPreviewColumnPreferences() {
  return normalizePreviewColumnPreferences();
}

function normalizeOutputRowFilterSettings(raw?: Partial<OutputRowFilterSettings>): OutputRowFilterSettings {
  const rawField = String(raw?.value_filter_field ?? DEFAULT_OUTPUT_ROW_FILTER_SETTINGS.value_filter_field);
  const valueFilterField = (WARNING_FILTER_FIELDS as readonly string[]).includes(rawField)
    ? rawField as WarningFilterField
    : DEFAULT_OUTPUT_ROW_FILTER_SETTINGS.value_filter_field;
  return {
    enabled: raw?.enabled ?? DEFAULT_OUTPUT_ROW_FILTER_SETTINGS.enabled,
    value_filter_field: valueFilterField,
  };
}

function readInitialOutputRowFilterSettings() {
  if (typeof window === "undefined") {
    return DEFAULT_OUTPUT_ROW_FILTER_SETTINGS;
  }
  try {
    const raw = window.localStorage.getItem(OUTPUT_ROW_FILTER_STORAGE_KEY);
    if (!raw) return DEFAULT_OUTPUT_ROW_FILTER_SETTINGS;
    return normalizeOutputRowFilterSettings(JSON.parse(raw) as Partial<OutputRowFilterSettings>);
  } catch {
    return DEFAULT_OUTPUT_ROW_FILTER_SETTINGS;
  }
}

function clampZhisuanChatHeight(value: unknown) {
  if (value === null || value === undefined || String(value).trim() === "") {
    return DEFAULT_ZHISUAN_WINDOW_SETTINGS.chatHeight;
  }
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return DEFAULT_ZHISUAN_WINDOW_SETTINGS.chatHeight;
  return Math.max(300, Math.min(720, Math.round(numericValue)));
}

function clampZhisuanDockWidth(value: unknown) {
  if (value === null || value === undefined || String(value).trim() === "") {
    return DEFAULT_ZHISUAN_WINDOW_SETTINGS.dockWidth;
  }
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return DEFAULT_ZHISUAN_WINDOW_SETTINGS.dockWidth;
  return Math.max(300, Math.min(560, Math.round(numericValue)));
}

function normalizeZhisuanQuickSettings(raw?: Partial<ZhisuanQuickSettings>): ZhisuanQuickSettings {
  const builtinIds = new Set(ZHISUAN_BUILTIN_QUICK_ITEMS.map((item) => item.id));
  const storedVersion = Number(raw?.version ?? 1);
  const normalizedVersion = Number.isFinite(storedVersion) ? storedVersion : 1;
  const enabledIds = Array.isArray(raw?.enabledIds)
    ? raw.enabledIds.map(String).filter((id) => builtinIds.has(id))
    : DEFAULT_ZHISUAN_QUICK_SETTINGS.enabledIds;
  const migratedEnabledIds =
    normalizedVersion < ZHISUAN_QUICK_SETTINGS_VERSION && !enabledIds.includes("batch-match")
      ? ["batch-match", ...enabledIds]
      : enabledIds;
  const customPrompts = Array.isArray(raw?.customPrompts)
    ? Array.from(
      new Set(
        raw.customPrompts
          .map((value) => String(value).trim())
          .filter((value) => value && !ZHISUAN_QUICK_PROMPT_BLOCKLIST.has(value)),
      ),
    ).slice(0, 12)
    : [];
  return {
    enabledIds: migratedEnabledIds,
    customPrompts,
    autoHide: raw?.autoHide ?? DEFAULT_ZHISUAN_QUICK_SETTINGS.autoHide,
    version: ZHISUAN_QUICK_SETTINGS_VERSION,
  };
}

function normalizeZhisuanDockVisibilitySettings(raw?: Partial<ZhisuanDockVisibilitySettings>): ZhisuanDockVisibilitySettings {
  return {
    rowReview: Boolean(raw?.rowReview),
    conclusion: Boolean(raw?.conclusion),
    review: Boolean(raw?.review),
    warning: Boolean(raw?.warning),
    ruleNotice: Boolean(raw?.ruleNotice),
    debugInfo: Boolean(raw?.debugInfo),
  };
}

function normalizeZhisuanDockStyle(value: unknown): ZhisuanDockStyle {
  return value === "analysis" || value === "companion" ? value : "default";
}

function normalizeZhisuanWindowSettings(raw?: ZhisuanWindowSettingsPayload): ZhisuanWindowSettings {
  const welcomeMessage = String(raw?.welcomeMessage ?? "").replace(/\r/g, "").trim();
  return {
    chatHeight: clampZhisuanChatHeight(raw?.chatHeight),
    dockWidth: clampZhisuanDockWidth(raw?.dockWidth),
    useViewportHeight: raw?.useViewportHeight ?? DEFAULT_ZHISUAN_WINDOW_SETTINGS.useViewportHeight,
    quickSettings: normalizeZhisuanQuickSettings(raw?.quickSettings),
    dockVisibility: normalizeZhisuanDockVisibilitySettings(raw?.dockVisibility),
    welcomeMessage: welcomeMessage || DEFAULT_ZHISUAN_WINDOW_SETTINGS.welcomeMessage,
    dockStyle: normalizeZhisuanDockStyle(raw?.dockStyle),
  };
}

function readInitialWelcomeScreenVisible() {
  if (typeof window === "undefined") return true;
  const hidden = window.localStorage.getItem(WELCOME_SCREEN_HIDDEN_STORAGE_KEY) === "1";
  const storedVersion = window.localStorage.getItem(WELCOME_SCREEN_VERSION_STORAGE_KEY);
  return !(hidden && storedVersion === WELCOME_SCREEN_VERSION);
}

function clampUiNumber(value: unknown, min: number, max: number) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return undefined;
  return Math.max(min, Math.min(max, Math.round(numericValue * 100) / 100));
}

function normalizeUiStyleValues(raw?: Partial<UiStyleValues>): UiStyleValues {
  const next: UiStyleValues = {};
  const paddingX = clampUiNumber(raw?.paddingX, 0, 96);
  const paddingY = clampUiNumber(raw?.paddingY, 0, 96);
  const fontSize = clampUiNumber(raw?.fontSize, 10, 72);
  const radius = clampUiNumber(raw?.radius, 0, 60);
  const gap = clampUiNumber(raw?.gap, 0, 64);
  const marginTop = clampUiNumber(raw?.marginTop, -120, 120);
  const opacity = clampUiNumber(raw?.opacity, 20, 100);
  if (paddingX !== undefined) next.paddingX = paddingX;
  if (paddingY !== undefined) next.paddingY = paddingY;
  if (fontSize !== undefined) next.fontSize = fontSize;
  if (radius !== undefined) next.radius = radius;
  if (gap !== undefined) next.gap = gap;
  if (marginTop !== undefined) next.marginTop = marginTop;
  if (opacity !== undefined) next.opacity = opacity;
  return next;
}

function normalizeUiPreferences(raw?: Partial<UiPreferences>): UiPreferences {
  const rawStyles = raw?.styles && typeof raw.styles === "object" ? raw.styles : {};
  const rawText = raw?.text && typeof raw.text === "object" ? raw.text : {};
  const styles = Object.entries(rawStyles).reduce<Record<string, UiStyleValues>>((mapping, [key, value]) => {
    const cleanedKey = key.trim();
    if (!cleanedKey || !value || typeof value !== "object") return mapping;
    const cleanedValues = normalizeUiStyleValues(value);
    return Object.keys(cleanedValues).length > 0 ? { ...mapping, [cleanedKey]: cleanedValues } : mapping;
  }, {});
  const text = Object.entries(rawText).reduce<Record<string, string>>((mapping, [key, value]) => {
    const cleanedKey = key.trim();
    if (!cleanedKey) return mapping;
    const cleanedValue = migrateUiText(cleanedKey, String(value).replace(/\r/g, "").slice(0, 200));
    return { ...mapping, [cleanedKey]: cleanedValue };
  }, {});
  return {
    enabled: Boolean(raw?.enabled),
    styles,
    text,
  };
}

function migrateUiText(key: string, value: string): string {
  const trimmedValue = value.trim();
  if (key === "hero.title" && trimmedValue === OLD_APP_NAME) {
    return APP_NAME;
  }
  if (key === "hero.subtitle" && OLD_APP_SUBTITLES.includes(trimmedValue)) {
    return APP_SUBTITLE;
  }
  return value;
}

export function App() {
  if (window.location.pathname === "/v2-preview") {
    return <DaweibaLayoutV2 />;
  }
  return <DaweibaApp />;
}

function DaweibaApp() {
  const [file, setFile] = useState<File | null>(null);
  const [columns, setColumns] = useState<ColumnOption[]>([]);
  const [headerRow, setHeaderRow] = useState(4);
  const [columnMapping, setColumnMapping] = useState<ColumnMapping>(EMPTY_MAPPING);
  const [sheetConfigs, setSheetConfigs] = useState<SheetMappingConfig[]>([]);
  const [activeSheetName, setActiveSheetName] = useState("");
  const [outputMatchReport, setOutputMatchReport] = useState(true);
  const [mergeVerticalCells, setMergeVerticalCells] = useState(true);
  const [mergeHorizontalCells, setMergeHorizontalCells] = useState(true);
  const [onlyMatchRowsWithValue, setOnlyMatchRowsWithValue] = useState(true);
  const [matchValueFilterField, setMatchValueFilterField] = useState<WarningFilterField>("数量");
  const [result, setResult] = useState<ProcessResult | null>(null);
  const [error, setError] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [isBatchMatching, setIsBatchMatching] = useState(false);
  const [isGeneratingRisk, setIsGeneratingRisk] = useState(false);
  const [isChatting, setIsChatting] = useState(false);
  const [isInspecting, setIsInspecting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isExperienceDragging, setIsExperienceDragging] = useState(false);
  const [workloadDraggingRole, setWorkloadDraggingRole] = useState<WorkloadRole | null>(null);
  const [isMappingOpen, setIsMappingOpen] = useState(false);
  const [isInputFieldSettingsOpen, setIsInputFieldSettingsOpen] = useState(false);
  const [isLoadingInputFieldSettings, setIsLoadingInputFieldSettings] = useState(false);
  const [isSavingInputFieldSettings, setIsSavingInputFieldSettings] = useState(false);
  const [inputFieldDefaults, setInputFieldDefaults] = useState<InputFieldPreferences>(EMPTY_INPUT_FIELD_PREFERENCES);
  const [inputFieldDraft, setInputFieldDraft] = useState<InputFieldPreferences>(EMPTY_INPUT_FIELD_PREFERENCES);
  const [inputFieldPreferencesPath, setInputFieldPreferencesPath] = useState("");
  const [isLlmSettingsOpen, setIsLlmSettingsOpen] = useState(false);
  const [isPageSettingsOpen, setIsPageSettingsOpen] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isLlmDebugOpen, setIsLlmDebugOpen] = useState(false);
  const [isAiDockCollapsed, setIsAiDockCollapsed] = useState(false);
  const [activePreviewSheetName, setActivePreviewSheetName] = useState("");
  const [isPreviewSettingsOpen, setIsPreviewSettingsOpen] = useState(false);
  const [activePreviewSettingsSheetName, setActivePreviewSettingsSheetName] = useState("");
  const [previewColumnPreferences, setPreviewColumnPreferences] = useState<PreviewColumnPreferences>(readInitialPreviewColumnPreferences);
  const [previewDefaultLabelsDraft, setPreviewDefaultLabelsDraft] = useState(preferenceText([...DEFAULT_CORE_PREVIEW_LABELS]));
  const [isRefreshingPreviewSettings, setIsRefreshingPreviewSettings] = useState(false);
  const [editingPreviewCell, setEditingPreviewCell] = useState<PreviewCellEditState | null>(null);
  const [savingPreviewCellKey, setSavingPreviewCellKey] = useState("");
  const [isRecalculatingPreview, setIsRecalculatingPreview] = useState(false);
  const [previewManualEditMessage, setPreviewManualEditMessage] = useState("");
  const [reportPreviewRevision, setReportPreviewRevision] = useState(0);
  const [reportPreviewUpdateMessage, setReportPreviewUpdateMessage] = useState("");
  const [reportPreviewStatus, setReportPreviewStatus] = useState<WordReportPreviewStatus>("idle");
  const [outputRowFilterSettings, setOutputRowFilterSettings] = useState<OutputRowFilterSettings>(readInitialOutputRowFilterSettings);
  const [pendingPreviewJump, setPendingPreviewJump] = useState<PreviewJumpTarget | null>(null);
  const [focusedPreviewJump, setFocusedPreviewJump] = useState<PreviewJumpTarget | null>(null);
  const [progressPercent, setProgressPercent] = useState(0);
  const [rowAiContext, setRowAiContext] = useState<RowAiContext | null>(null);
  const [rowAiQuestion, setRowAiQuestion] = useState("解释这行要素含义，并判断当前基价和两个系数是否合理。");
  const [rowAiAnswer, setRowAiAnswer] = useState("");
  const [isRowAiLoading, setIsRowAiLoading] = useState(false);
  const [rowAiDetailPrompt, setRowAiDetailPrompt] = useState<RowAiContext | null>(null);
  const [activeDaweibaModule, setActiveDaweibaModule] = useState<DaweibaModuleId>("fill");
  const [digitalProjectAssistantFrameKey, setDigitalProjectAssistantFrameKey] = useState(0);
  const [digitalProjectAssistantFrameStatus, setDigitalProjectAssistantFrameStatus] = useState<"loading" | "ready" | "timeout">("loading");
  const [feishuWebhookStatus, setFeishuWebhookStatus] = useState<FeishuWebhookStatus>(EMPTY_FEISHU_WEBHOOK_STATUS);
  const [feishuWebhookHistory, setFeishuWebhookHistory] = useState<FeishuDeliveryRecord[]>([]);
  const [feishuWebhookDraft, setFeishuWebhookDraft] = useState("");
  const [feishuSecretDraft, setFeishuSecretDraft] = useState("");
  const [feishuAppUrlDraft, setFeishuAppUrlDraft] = useState("");
  const [feishuEnabledDraft, setFeishuEnabledDraft] = useState(false);
  const [feishuNotificationDraft, setFeishuNotificationDraft] = useState<FeishuNotificationSwitches>(DEFAULT_FEISHU_NOTIFICATION_SWITCHES);
  const [isLoadingFeishuWebhook, setIsLoadingFeishuWebhook] = useState(false);
  const [isSavingFeishuWebhook, setIsSavingFeishuWebhook] = useState(false);
  const [isTestingFeishuWebhook, setIsTestingFeishuWebhook] = useState(false);
  const [feishuWebhookFeedback, setFeishuWebhookFeedback] = useState("");
  const [feishuAppBotStatus, setFeishuAppBotStatus] = useState<FeishuAppBotStatus | null>(null);
  const [isTogglingFeishuAppBot, setIsTogglingFeishuAppBot] = useState(false);
  const [feishuBotConsoleEvents, setFeishuBotConsoleEvents] = useState<FeishuBotConsoleEvent[]>([]);
  const [isFeishuBotConsoleOpen, setIsFeishuBotConsoleOpen] = useState(false);
  const [isFeishuBotConsoleLive, setIsFeishuBotConsoleLive] = useState(true);
  const [isLoadingFeishuBotConsole, setIsLoadingFeishuBotConsole] = useState(false);
  const feishuBotConsoleRef = useRef<HTMLDivElement | null>(null);
  const [isLeftColumnCollapsed, setIsLeftColumnCollapsed] = useState(readInitialLeftColumnCollapsed);
  const [isWelcomeScreenVisible, setIsWelcomeScreenVisible] = useState(readInitialWelcomeScreenVisible);
  const [hideWelcomeNextTime, setHideWelcomeNextTime] = useState(false);
  const [uiPreferences, setUiPreferences] = useState<UiPreferences>(EMPTY_UI_PREFERENCES);
  const [uiPreferencesDraft, setUiPreferencesDraft] = useState<UiPreferences>(EMPTY_UI_PREFERENCES);
  const [uiPreferencesPath, setUiPreferencesPath] = useState("");
  const [isUiTunerOpen, setIsUiTunerOpen] = useState(false);
  const [isLoadingUiPreferences, setIsLoadingUiPreferences] = useState(false);
  const [isSavingUiPreferences, setIsSavingUiPreferences] = useState(false);
  const [activeUiTarget, setActiveUiTarget] = useState<UiTunerTargetId>("hero");
  const [activeUiTextKey, setActiveUiTextKey] = useState<UiTextTargetId>("hero.title");
  const [isUiPickMode, setIsUiPickMode] = useState(false);
  const [llmSettings, setLlmSettings] = useState(DEFAULT_LLM_SETTINGS);
  const [riskReport, setRiskReport] = useState("");
  const [riskSummary, setRiskSummary] = useState<RiskSummaryPayload | null>(null);
  const [isRiskSummaryLoading, setIsRiskSummaryLoading] = useState(false);
  const [experienceGovernance, setExperienceGovernance] = useState<GovernanceReport | null>(null);
  const [isExperienceGovernanceLoading, setIsExperienceGovernanceLoading] = useState(false);
  const [isDemoLoading, setIsDemoLoading] = useState(false);
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [fillAssistDialog, setFillAssistDialog] = useState<FillAssistDialogState | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [isChatInputFocused, setIsChatInputFocused] = useState(false);
  const [avatarSuccessUntil, setAvatarSuccessUntil] = useState(0);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [zhisuanWindowDefaults, setZhisuanWindowDefaults] = useState<ZhisuanWindowSettings>(normalizeZhisuanWindowSettings);
  const [zhisuanChatHeight, setZhisuanChatHeight] = useState(DEFAULT_ZHISUAN_WINDOW_SETTINGS.chatHeight);
  const [zhisuanChatHeightDraft, setZhisuanChatHeightDraft] = useState(String(DEFAULT_ZHISUAN_WINDOW_SETTINGS.chatHeight));
  const [zhisuanDockWidth, setZhisuanDockWidth] = useState(DEFAULT_ZHISUAN_WINDOW_SETTINGS.dockWidth);
  const [zhisuanDockWidthDraft, setZhisuanDockWidthDraft] = useState(String(DEFAULT_ZHISUAN_WINDOW_SETTINGS.dockWidth));
  const [useZhisuanDockViewportHeight, setUseZhisuanDockViewportHeight] = useState(DEFAULT_ZHISUAN_WINDOW_SETTINGS.useViewportHeight);
  const [zhisuanQuickSettings, setZhisuanQuickSettings] = useState<ZhisuanQuickSettings>(DEFAULT_ZHISUAN_WINDOW_SETTINGS.quickSettings);
  const [zhisuanDockVisibility, setZhisuanDockVisibility] = useState<ZhisuanDockVisibilitySettings>(DEFAULT_ZHISUAN_WINDOW_SETTINGS.dockVisibility);
  const [customQuickCommandDraft, setCustomQuickCommandDraft] = useState(() => preferenceText(DEFAULT_ZHISUAN_WINDOW_SETTINGS.quickSettings.customPrompts));
  const [zhisuanWelcomeMessage, setZhisuanWelcomeMessage] = useState(DEFAULT_ZHISUAN_WINDOW_SETTINGS.welcomeMessage);
  const [zhisuanWelcomeDraft, setZhisuanWelcomeDraft] = useState(DEFAULT_ZHISUAN_WINDOW_SETTINGS.welcomeMessage);
  const [isZhisuanWelcomeLoaded, setIsZhisuanWelcomeLoaded] = useState(false);
  const [zhisuanDockStyle, setZhisuanDockStyle] = useState<ZhisuanDockStyle>(DEFAULT_ZHISUAN_WINDOW_SETTINGS.dockStyle);
  const [llmDebugHistory, setLlmDebugHistory] = useState<LlmDebugRecord[]>([]);
  const [experienceFile, setExperienceFile] = useState<File | null>(null);
  const [selectedExperienceFields, setSelectedExperienceFields] = useState<string[]>([...EXPERIENCE_FIELD_OPTIONS]);
  const [onlyImportExperienceRowsWithValue, setOnlyImportExperienceRowsWithValue] = useState(true);
  const [experienceValueFilterField, setExperienceValueFilterField] = useState<ExperienceMappingField>("工程量");
  const [experienceSheetConfigs, setExperienceSheetConfigs] = useState<ExperienceSheetMappingConfig[]>([]);
  const [activeExperienceSheetName, setActiveExperienceSheetName] = useState("");
  const [isInspectingExperience, setIsInspectingExperience] = useState(false);
  const [isExperienceMappingOpen, setIsExperienceMappingOpen] = useState(false);
  const [isExperienceImportCollapsed, setIsExperienceImportCollapsed] = useState(true);
  const [isExperienceFieldSettingsOpen, setIsExperienceFieldSettingsOpen] = useState(false);
  const [isLoadingExperienceFieldSettings, setIsLoadingExperienceFieldSettings] = useState(false);
  const [isSavingExperienceFieldSettings, setIsSavingExperienceFieldSettings] = useState(false);
  const [experienceFieldDefaults, setExperienceFieldDefaults] = useState<ExperienceFieldPreferences>(EMPTY_EXPERIENCE_FIELD_PREFERENCES);
  const [experienceFieldDraft, setExperienceFieldDraft] = useState<ExperienceFieldPreferences>(EMPTY_EXPERIENCE_FIELD_PREFERENCES);
  const [experienceFieldPreferencesPath, setExperienceFieldPreferencesPath] = useState("");
  const [isImportingExperience, setIsImportingExperience] = useState(false);
  const [experienceImportSummary, setExperienceImportSummary] = useState<ExperienceImportSummary | null>(null);
  const [isRunningWarnings, setIsRunningWarnings] = useState(false);
  const [warningProgress, setWarningProgress] = useState<WarningProgress>(EMPTY_WARNING_PROGRESS);
  const [isExperienceWarningSettingsOpen, setIsExperienceWarningSettingsOpen] = useState(false);
  const [isLoadingExperienceWarningSettings, setIsLoadingExperienceWarningSettings] = useState(false);
  const [isSavingExperienceWarningSettings, setIsSavingExperienceWarningSettings] = useState(false);
  const [experienceWarningSettings, setExperienceWarningSettings] = useState<ExperienceWarningSettings>(DEFAULT_EXPERIENCE_WARNING_SETTINGS);
  const [experienceWarningSettingsDraft, setExperienceWarningSettingsDraft] = useState<ExperienceWarningSettings>(DEFAULT_EXPERIENCE_WARNING_SETTINGS);
  const [experienceWarningSettingsPath, setExperienceWarningSettingsPath] = useState("");
  const [experienceWarningFilterFields, setExperienceWarningFilterFields] = useState<WarningFilterField[]>([...WARNING_FILTER_FIELDS]);
  const [workloadFile, setWorkloadFile] = useState<File | null>(null);
  const [workloadTargetFile, setWorkloadTargetFile] = useState<File | null>(null);
  const [selectedWorkloadFields, setSelectedWorkloadFields] = useState<string[]>([...WORKLOAD_CAPTURE_FIELD_OPTIONS]);
  const [workloadWriteMode, setWorkloadWriteMode] = useState<"conservative" | "overwrite">("conservative");
  const [onlyCaptureWorkloadRowsWithValue, setOnlyCaptureWorkloadRowsWithValue] = useState(true);
  const [workloadValueFilterField, setWorkloadValueFilterField] = useState<WorkloadSourceField>("数量");
  const [workloadSourceConfigs, setWorkloadSourceConfigs] = useState<WorkloadSheetMappingConfig<WorkloadSourceMapping>[]>([]);
  const [workloadTargetConfigs, setWorkloadTargetConfigs] = useState<WorkloadSheetMappingConfig<WorkloadTargetMapping>[]>([]);
  const [activeWorkloadSourceSheetName, setActiveWorkloadSourceSheetName] = useState("");
  const [activeWorkloadTargetSheetName, setActiveWorkloadTargetSheetName] = useState("");
  const [isInspectingWorkload, setIsInspectingWorkload] = useState(false);
  const [isWorkloadMappingOpen, setIsWorkloadMappingOpen] = useState(false);
  const [isWorkloadFieldSettingsOpen, setIsWorkloadFieldSettingsOpen] = useState(false);
  const [isLoadingWorkloadFieldSettings, setIsLoadingWorkloadFieldSettings] = useState(false);
  const [isSavingWorkloadFieldSettings, setIsSavingWorkloadFieldSettings] = useState(false);
  const [workloadFieldDefaults, setWorkloadFieldDefaults] = useState<WorkloadFieldPreferences>(EMPTY_WORKLOAD_FIELD_PREFERENCES);
  const [workloadFieldDraft, setWorkloadFieldDraft] = useState<WorkloadFieldPreferences>(EMPTY_WORKLOAD_FIELD_PREFERENCES);
  const [workloadFieldPreferencesPath, setWorkloadFieldPreferencesPath] = useState("");
  const [workloadAdjacentFallbackEnabled, setWorkloadAdjacentFallbackEnabled] = useState(true);
  const [workloadElementSequenceEnabled, setWorkloadElementSequenceEnabled] = useState(true);
  const [isWorkloadTargetFieldSettingsOpen, setIsWorkloadTargetFieldSettingsOpen] = useState(false);
  const [isLoadingWorkloadTargetFieldSettings, setIsLoadingWorkloadTargetFieldSettings] = useState(false);
  const [isSavingWorkloadTargetFieldSettings, setIsSavingWorkloadTargetFieldSettings] = useState(false);
  const [workloadTargetFieldDefaults, setWorkloadTargetFieldDefaults] = useState<WorkloadTargetFieldPreferences>(EMPTY_WORKLOAD_TARGET_FIELD_PREFERENCES);
  const [workloadTargetFieldDraft, setWorkloadTargetFieldDraft] = useState<WorkloadTargetFieldPreferences>(EMPTY_WORKLOAD_TARGET_FIELD_PREFERENCES);
  const [workloadTargetFieldPreferencesPath, setWorkloadTargetFieldPreferencesPath] = useState("");
  const [workloadTargetAdjacentFallbackEnabled, setWorkloadTargetAdjacentFallbackEnabled] = useState(true);
  const [workloadTargetElementSequenceEnabled, setWorkloadTargetElementSequenceEnabled] = useState(false);
  const [isRunningWorkloadCapture, setIsRunningWorkloadCapture] = useState(false);
  const [workloadProgressPercent, setWorkloadProgressPercent] = useState(0);
  const [workloadProgressText, setWorkloadProgressText] = useState("");
  const [workloadCaptureResult, setWorkloadCaptureResult] = useState<WorkloadCaptureResult | null>(null);
  const [workloadPreviewCountdown, setWorkloadPreviewCountdown] = useState<number | null>(null);
  const [showAllWarnings, setShowAllWarnings] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const experienceFileInputRef = useRef<HTMLInputElement | null>(null);
  const workloadFileInputRef = useRef<HTMLInputElement | null>(null);
  const workloadTargetFileInputRef = useRef<HTMLInputElement | null>(null);
  const chatLogRef = useRef<HTMLDivElement | null>(null);
  const chatInputRef = useRef<HTMLTextAreaElement | null>(null);
  const didWelcomeRef = useRef(false);
  const lastProcessingStageRef = useRef("");
  const lastDaweibaResultKeyRef = useRef("");
  const previewGuideResultKeyRef = useRef("");
  const previewScrollRef = useRef<HTMLDivElement | null>(null);
  const previewFocusTimeoutRef = useRef<number | null>(null);
  const cancelPreviewEditRef = useRef(false);
  const committingPreviewEditRef = useRef(false);
  const activeResultJobIdRef = useRef<string | null>(null);
  const processRequestSequenceRef = useRef(0);

  useEffect(() => {
    activeResultJobIdRef.current = result?.job_id ?? null;
    setReportPreviewRevision(0);
    setReportPreviewUpdateMessage("");
    setReportPreviewStatus("idle");
  }, [result?.job_id]);

  useEffect(() => {
    if (reportPreviewStatus === "ready") {
      setReportPreviewUpdateMessage("");
    }
  }, [reportPreviewStatus]);

  useEffect(() => {
    if (!isRunningWorkloadCapture) return;
    setWorkloadProgressPercent((current) => (current > 0 ? current : 6));
    const timer = window.setInterval(() => {
      setWorkloadProgressPercent((current) => {
        const next = current < 28 ? current + 6 : current < 58 ? current + 4 : current < 82 ? current + 3 : current + 1;
        return Math.min(next, 94);
      });
    }, 500);
    return () => window.clearInterval(timer);
  }, [isRunningWorkloadCapture]);

  useEffect(() => {
    if (!isRunningWorkloadCapture && workloadProgressPercent <= 0) return;
    if (workloadProgressPercent < 28) {
      setWorkloadProgressText("正在读取工作量表和当前预览控制价表...");
      return;
    }
    if (workloadProgressPercent < 58) {
      setWorkloadProgressText("正在按要素1-5、单位和术语归并规则匹配...");
      return;
    }
    if (workloadProgressPercent < 82) {
      setWorkloadProgressText("正在写入数量、系数和备注...");
      return;
    }
    if (workloadProgressPercent < 100) {
      setWorkloadProgressText("正在刷新表格预览和标注工作量表...");
      return;
    }
    setWorkloadProgressText("抓取完成，正在刷新结果...");
  }, [isRunningWorkloadCapture, workloadProgressPercent]);

  useEffect(() => {
    if (workloadPreviewCountdown === null) return undefined;
    if (workloadPreviewCountdown <= 0) {
      setWorkloadPreviewCountdown(null);
      setActiveDaweibaModule("preview");
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setWorkloadPreviewCountdown((current) => (current === null ? null : Math.max(0, current - 1)));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [workloadPreviewCountdown]);

  useEffect(() => {
    if (workloadPreviewCountdown === null) return undefined;
    const cancelCountdown = () => setWorkloadPreviewCountdown(null);
    window.addEventListener("pointerdown", cancelCountdown, { capture: true });
    return () => window.removeEventListener("pointerdown", cancelCountdown, { capture: true });
  }, [workloadPreviewCountdown]);

  useEffect(() => {
    window.localStorage.setItem(LEFT_COLUMN_COLLAPSED_STORAGE_KEY, String(isLeftColumnCollapsed));
  }, [isLeftColumnCollapsed]);

  useEffect(() => {
    if (!isZhisuanWelcomeLoaded) return;
    if (didWelcomeRef.current) return;
    didWelcomeRef.current = true;
    appendZhisuanMessage(zhisuanWelcomeMessage);
  }, [isZhisuanWelcomeLoaded, zhisuanWelcomeMessage]);

  useEffect(() => {
    const typingMessage = chatMessages.find(
      (message) =>
        message.role === "assistant"
        && message.isTyping
        && (message.displayContent ?? "").length < message.content.length,
    );
    if (!typingMessage) return undefined;
    const timer = window.setTimeout(() => {
      setChatMessages((current) =>
        current.map((message) => {
          if (message.id !== typingMessage.id) return message;
          const currentText = message.displayContent ?? "";
          const nextText = message.content.slice(0, currentText.length + 2);
          return {
            ...message,
            displayContent: nextText,
            isTyping: nextText.length < message.content.length,
          };
        }),
      );
    }, 24);
    return () => window.clearTimeout(timer);
  }, [chatMessages]);

  useEffect(() => {
    chatLogRef.current?.scrollTo({
      top: chatLogRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [chatMessages]);

  useEffect(() => {
    const successMarker = [
      result?.summary.output_excel,
      warningProgress.status === "completed" ? `warning-${warningProgress.processed_rows}-${warningProgress.warning_rows}` : "",
      riskReport ? `risk-${riskReport.length}` : "",
      previewManualEditMessage.includes("完成") || previewManualEditMessage.includes("成功")
        ? previewManualEditMessage
        : "",
    ].filter(Boolean).join("|");
    if (!successMarker) return undefined;
    setAvatarSuccessUntil(Date.now() + 2200);
    const timer = window.setTimeout(() => setAvatarSuccessUntil(0), 2200);
    return () => window.clearTimeout(timer);
  }, [
    result?.summary.output_excel,
    warningProgress.status,
    warningProgress.processed_rows,
    warningProgress.warning_rows,
    riskReport,
    previewManualEditMessage,
  ]);

  useEffect(() => {
    void loadUiPreferences();
  }, []);

  useEffect(() => {
    void loadProjectDefaultSettings();
  }, []);

  useEffect(() => {
    if (activeDaweibaModule !== "collaboration") return;
    void loadFeishuWebhookData();
  }, [activeDaweibaModule]);

  useEffect(() => {
    if (activeDaweibaModule !== "collaboration" || !isFeishuBotConsoleOpen || !isFeishuBotConsoleLive) return undefined;
    const timer = window.setInterval(() => void loadFeishuBotConsole(true), 3000);
    return () => window.clearInterval(timer);
  }, [activeDaweibaModule, isFeishuBotConsoleOpen, isFeishuBotConsoleLive]);

  useEffect(() => {
    if (activeDaweibaModule !== "collaboration" || !isFeishuBotConsoleOpen || !feishuBotConsoleRef.current) return;
    feishuBotConsoleRef.current.scrollTop = feishuBotConsoleRef.current.scrollHeight;
  }, [activeDaweibaModule, isFeishuBotConsoleOpen, feishuBotConsoleEvents]);

  useEffect(() => {
    if (!isFeishuBotConsoleOpen) return undefined;
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setIsFeishuBotConsoleOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isFeishuBotConsoleOpen]);

  useEffect(() => {
    if (activeDaweibaModule !== "digital-project-assistant" || digitalProjectAssistantFrameStatus !== "loading") return undefined;
    const timer = window.setTimeout(() => setDigitalProjectAssistantFrameStatus("timeout"), 10000);
    return () => window.clearTimeout(timer);
  }, [activeDaweibaModule, digitalProjectAssistantFrameKey, digitalProjectAssistantFrameStatus]);

  useEffect(() => {
    setPreviewDefaultLabelsDraft(preferenceText(previewColumnPreferences.defaultLabels));
  }, [previewColumnPreferences]);

  useEffect(() => {
    window.localStorage.setItem(
      OUTPUT_ROW_FILTER_STORAGE_KEY,
      JSON.stringify(outputRowFilterSettings),
    );
  }, [outputRowFilterSettings]);

  useEffect(() => {
    if (!isProcessing) return undefined;
    setProgressPercent(1);
    const timer = window.setInterval(() => {
      setProgressPercent((current) => {
        if (current < 28) return Math.min(28, current + 4);
        if (current < 68) return Math.min(68, current + 3);
        if (current < 86) return Math.min(86, current + 1.2);
        if (current < 96) return Math.min(96, current + 0.8);
        if (current < 98.5) return Math.min(98.5, current + 0.25);
        return current;
      });
    }, 240);
    return () => window.clearInterval(timer);
  }, [isProcessing]);

  const completion = useMemo(() => {
    if (!result?.summary.total_data_rows) return 0;
    return Math.round((result.summary.filled_rows / result.summary.total_data_rows) * 100);
  }, [result]);

  const isBatchMatchPending = result?.summary.matching_status === "pending";
  const displayCompletion = isProcessing ? progressPercent : isBatchMatchPending ? 35 : completion;
  const processingStage = useMemo(() => getProcessingStage(displayCompletion), [displayCompletion]);

  useEffect(() => {
    if (!isProcessing) {
      lastProcessingStageRef.current = "";
      return;
    }
    if (lastProcessingStageRef.current === processingStage.title) return;
    lastProcessingStageRef.current = processingStage.title;
    appendZhisuanMessage(`${processingStage.title}：${processingStage.description}`, "system");
  }, [isProcessing, processingStage]);

  useEffect(() => {
    const resultKey = result?.summary.output_excel ?? "";
    if (!resultKey) {
      lastDaweibaResultKeyRef.current = "";
      return;
    }
    if (lastDaweibaResultKeyRef.current === resultKey) return;
    lastDaweibaResultKeyRef.current = resultKey;
  }, [result]);

  const fileSize = useMemo(() => {
    if (!file) return "";
    if (file.size < 1024 * 1024) return `${Math.max(1, Math.round(file.size / 1024))} KB`;
    return `${(file.size / 1024 / 1024).toFixed(1)} MB`;
  }, [file]);

  const mappedFieldCount = useMemo(
    () => MAPPING_FIELDS.filter((field) => Boolean(activeMapping()[field])).length,
    [columnMapping, sheetConfigs, activeSheetName],
  );
  const mappedExperienceFieldCount = useMemo(
    () => EXPERIENCE_MAPPING_FIELDS.filter((field) => Boolean(activeExperienceMapping()[field])).length,
    [experienceSheetConfigs, activeExperienceSheetName],
  );
  const mappedWorkloadSourceFieldCount = useMemo(
    () => WORKLOAD_SOURCE_FIELDS.filter((field) => Boolean(activeWorkloadSourceMapping()[field])).length,
    [workloadSourceConfigs, activeWorkloadSourceSheetName],
  );
  const mappedWorkloadTargetFieldCount = useMemo(
    () => WORKLOAD_TARGET_FIELDS.filter((field) => Boolean(activeWorkloadTargetMapping()[field])).length,
    [workloadTargetConfigs, activeWorkloadTargetSheetName],
  );

  const previewSheets = useMemo(() => {
    if (!result) return [];
    return previewSheetsFromTablePreview(result.summary.table_preview);
  }, [result]);

  const activePreview = useMemo(() => {
    return (
      previewSheets.find((sheet) => sheet.sheet_name === activePreviewSheetName) ??
      previewSheets[0] ??
      { sheet_name: "", headers: [], rows: [] }
    );
  }, [activePreviewSheetName, previewSheets]);

  const activePreviewSettingsSheet = useMemo(() => {
    return (
      previewSheets.find((sheet) => previewSheetKey(sheet) === activePreviewSettingsSheetName) ??
      activePreview
    );
  }, [activePreview, activePreviewSettingsSheetName, previewSheets]);

  const previewColumns = useMemo(
    () => buildPreviewColumns(activePreview, result?.summary.price_column, previewColumnPreferences),
    [activePreview, previewColumnPreferences, result],
  );
  const visiblePreviewRows = useMemo(
    () => filterPreviewRows(activePreview, outputRowFilterSettings),
    [activePreview, outputRowFilterSettings],
  );
  const hiddenPreviewRowCount = Math.max(0, activePreview.rows.length - visiblePreviewRows.length);
  const focusedPreviewColumnIndex = useMemo(() => {
    if (!focusedPreviewJump) return -1;
    if (normalizePreviewSheetName(activePreview.sheet_name) !== normalizePreviewSheetName(focusedPreviewJump.sheetName)) {
      return -1;
    }
    return findPreviewMetricColumnIndex(activePreview, previewColumns, result?.summary.price_column, focusedPreviewJump.metric);
  }, [activePreview, focusedPreviewJump, previewColumns, result]);
  const excelDownloadHref = useMemo(() => {
    if (!result?.downloads.excel) return "#";
    const url = new URL(`${API_BASE}${result.downloads.excel}`, window.location.href);
    if (outputRowFilterSettings.enabled) {
      url.searchParams.set("hide_empty_rows", "true");
      url.searchParams.set("value_filter_field", outputRowFilterSettings.value_filter_field);
    }
    return url.toString();
  }, [outputRowFilterSettings, result]);
  const previewSettingColumns = useMemo(
    () => buildAvailablePreviewColumns(activePreviewSettingsSheet, result?.summary.price_column),
    [activePreviewSettingsSheet, result],
  );
  const warningSummary = result?.summary.warning_summary;
  const warningDetails = result?.summary.warning_details ?? [];
  const hasCurrentReport = Boolean(
    result?.downloads.report
    && result.summary.output_report
    && !isBatchMatchPending,
  );
  const canDownloadOutputs = Boolean(result?.downloads.excel && hasCurrentReport);
  const reportDownloadHref = hasCurrentReport && result ? `${API_BASE}${result.downloads.report}` : "";
  const visibleWarnings = showAllWarnings ? warningDetails : warningDetails.slice(0, 6);
  const visibleWorkloadIssueLogs = useMemo(
    () => {
      if (!workloadCaptureResult) return [];
      const issueLogs = workloadCaptureResult.summary.issue_log_preview;
      if (issueLogs?.length) return issueLogs.filter(isWorkloadIssueLog).slice(0, 20);
      return [];
    },
    [workloadCaptureResult],
  );
  const wideHighWarningRows = warningSummary?.executed ? Number(warningSummary.high_rows ?? 0) : 0;
  const wideLowWarningRows = warningSummary?.executed ? Number(warningSummary.low_rows ?? warningSummary.medium_rows ?? 0) : 0;
  const wideReviewRows = result?.summary.review_rows ?? 0;
  const wideTotalRows = Math.max(1, result?.summary.total_data_rows ?? 100);
  const wideMatchedRows = result?.summary.matched_rows ?? 0;
  const wideStableRows = Math.max(0, wideMatchedRows - wideHighWarningRows - wideLowWarningRows - wideReviewRows);
  const wideStablePercent = result ? Math.round((wideStableRows / wideTotalRows) * 1000) / 10 : Math.round(displayCompletion);
  const wideLowEndPercent = result
    ? Math.min(100, wideStablePercent + Math.round((wideLowWarningRows / wideTotalRows) * 1000) / 10)
    : Math.min(100, Math.round(displayCompletion));
  const isWideRingEmpty = wideStableRows <= 0 && wideLowWarningRows <= 0 && wideHighWarningRows <= 0;
  const wideRingStyle = {
    "--wide-ok": `${wideStablePercent}%`,
    "--wide-low": `${wideLowEndPercent}%`,
  } as CSSProperties;
  const visibleZhisuanQuickItems = useMemo(
    () => [
      ...ZHISUAN_BUILTIN_QUICK_ITEMS.filter((item) => zhisuanQuickSettings.enabledIds.includes(item.id)).map((item) => ({
        ...item,
        source: "builtin" as const,
      })),
      ...zhisuanQuickSettings.customPrompts.map((prompt, index) => ({
        id: `custom-${index}-${prompt}`,
        label: prompt,
        prompt,
        kind: "suggestion" as const,
        source: "custom" as const,
      })),
    ],
    [zhisuanQuickSettings],
  );
  const showZhisuanStatusGrid = zhisuanDockVisibility.conclusion
    || zhisuanDockVisibility.review
    || zhisuanDockVisibility.warning;
  const warningProgressPercent = useMemo(() => {
    if (warningProgress.total_rows > 0) {
      return Math.min(100, Math.round((warningProgress.processed_rows / warningProgress.total_rows) * 100));
    }
    return warningProgress.status === "completed" ? 100 : 0;
  }, [warningProgress]);
  const zhisuanAvatarState = useMemo<ZhisuanAvatarState>(() => {
    const hasAvatarError = Boolean(error || warningProgress.error || fillAssistDialog?.error);
    const isAvatarThinking = isChatting || isRowAiLoading || chatMessages.some((message) => message.role === "assistant" && message.isTyping);
    const isAvatarProcessing = Boolean(
      isProcessing
      || isBatchMatching
      || isInspecting
      || isDemoLoading
      || isRecalculatingPreview
      || savingPreviewCellKey
      || isRunningWarnings
      || isGeneratingRisk
      || isRiskSummaryLoading
      || isExperienceGovernanceLoading
      || isInspectingExperience
      || isImportingExperience
      || isRunningWorkloadCapture,
    );
    const hasAvatarWarning = Boolean(
      warningDetails.length > 0
      || (warningSummary?.executed && Number(warningSummary.warning_rows ?? 0) > 0)
      || (result?.summary.review_rows ?? 0) > 0,
    );
    if (hasAvatarError) return "error";
    if (isAvatarThinking) return "thinking";
    if (isAvatarProcessing) return "processing";
    if (hasAvatarWarning) return "warning";
    if (avatarSuccessUntil > Date.now()) return "success";
    if (isChatInputFocused || chatInput.trim()) return "listening";
    return "idle";
  }, [
    error,
    warningProgress.error,
    fillAssistDialog?.error,
    isChatting,
    isRowAiLoading,
    chatMessages,
    isProcessing,
    isBatchMatching,
    isInspecting,
    isDemoLoading,
    isRecalculatingPreview,
    savingPreviewCellKey,
    isRunningWarnings,
    isGeneratingRisk,
    isRiskSummaryLoading,
    isExperienceGovernanceLoading,
    isInspectingExperience,
    isImportingExperience,
    isRunningWorkloadCapture,
    warningDetails.length,
    warningSummary,
    result,
    avatarSuccessUntil,
    isChatInputFocused,
    chatInput,
  ]);
  const zhisuanAvatarLabel = ZHISUAN_AVATAR_STATE_LABELS[zhisuanAvatarState];

  function activeSheetConfig() {
    return sheetConfigs.find((config) => config.sheet_name === activeSheetName) ?? null;
  }

  function activeColumns() {
    return activeSheetConfig()?.columns ?? columns;
  }

  function activeMapping() {
    return activeSheetConfig()?.column_mapping ?? columnMapping;
  }

  function activeExperienceSheetConfig() {
    return experienceSheetConfigs.find((config) => config.sheet_name === activeExperienceSheetName) ?? null;
  }

  function activeExperienceColumns() {
    return activeExperienceSheetConfig()?.columns ?? [];
  }

  function activeExperienceMapping() {
    return activeExperienceSheetConfig()?.column_mapping ?? EMPTY_EXPERIENCE_MAPPING;
  }

  function activeWorkloadSourceConfig() {
    return workloadSourceConfigs.find((config) => config.sheet_name === activeWorkloadSourceSheetName) ?? null;
  }

  function activeWorkloadTargetConfig() {
    return workloadTargetConfigs.find((config) => config.sheet_name === activeWorkloadTargetSheetName) ?? null;
  }

  function activeWorkloadColumns(role: WorkloadRole) {
    return role === "source"
      ? activeWorkloadSourceConfig()?.columns ?? []
      : activeWorkloadTargetConfig()?.columns ?? [];
  }

  function activeWorkloadMapping(role: WorkloadRole) {
    return role === "source"
      ? activeWorkloadSourceConfig()?.column_mapping ?? EMPTY_WORKLOAD_SOURCE_MAPPING
      : activeWorkloadTargetConfig()?.column_mapping ?? EMPTY_WORKLOAD_TARGET_MAPPING;
  }

  function activeWorkloadSourceMapping() {
    return activeWorkloadSourceConfig()?.column_mapping ?? EMPTY_WORKLOAD_SOURCE_MAPPING;
  }

  function activeWorkloadTargetMapping() {
    return activeWorkloadTargetConfig()?.column_mapping ?? EMPTY_WORKLOAD_TARGET_MAPPING;
  }

  const activeUiStyle = uiPreferencesDraft.styles[activeUiTarget] ?? {};
  const activeUiTextTarget = UI_TEXT_TARGETS.find((target) => target.id === activeUiTextKey) ?? UI_TEXT_TARGETS[0];
  const activeUiTextValue = uiPreferencesDraft.text[activeUiTextKey] ?? activeUiTextTarget.defaultText;

  function applyUiPreferencesDraft(next: UiPreferences) {
    const normalized = normalizeUiPreferences(next);
    setUiPreferencesDraft(normalized);
    setUiPreferences(normalized);
  }

  function uiText(key: UiTextTargetId, fallback: string) {
    return Object.prototype.hasOwnProperty.call(uiPreferences.text, key) ? uiPreferences.text[key] : fallback;
  }

  function uiStyle(target: UiTunerTargetId): CSSProperties {
    if (!uiPreferences.enabled) return {};
    const values = uiPreferences.styles[target];
    if (!values) return {};
    const style: CSSProperties = {};
    if (values.paddingX !== undefined) style.paddingInline = `${values.paddingX}px`;
    if (values.paddingY !== undefined) style.paddingBlock = `${values.paddingY}px`;
    if (values.fontSize !== undefined) style.fontSize = `${values.fontSize}px`;
    if (values.radius !== undefined) style.borderRadius = `${values.radius}px`;
    if (values.gap !== undefined) style.gap = `${values.gap}px`;
    if (values.marginTop !== undefined) style.marginTop = `${values.marginTop}px`;
    if (values.opacity !== undefined) style.opacity = values.opacity / 100;
    return style;
  }

  async function loadUiPreferences(openAfterLoad = false) {
    setIsLoadingUiPreferences(true);
    try {
      const response = await fetch(`${API_BASE}/api/ui-preferences`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取页面用户设置失败：${response.status}`);
      }
      const payload = (await response.json()) as UiPreferencesPayload;
      const next = normalizeUiPreferences(payload.preferences ?? payload.defaults ?? EMPTY_UI_PREFERENCES);
      setUiPreferences(next);
      setUiPreferencesDraft(next);
      setUiPreferencesPath(payload.file_path ?? "");
      if (openAfterLoad) {
        setIsUiTunerOpen(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取页面用户设置失败");
    } finally {
      setIsLoadingUiPreferences(false);
    }
  }

  function openUiTuner() {
    setIsPageSettingsOpen(false);
    void loadUiPreferences(true);
  }

  async function saveUiPreferences() {
    setIsSavingUiPreferences(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/ui-preferences`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences: uiPreferencesDraft }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `保存页面用户设置失败：${response.status}`);
      }
      const payload = (await response.json()) as UiPreferencesPayload;
      const next = normalizeUiPreferences(payload.preferences ?? uiPreferencesDraft);
      setUiPreferences(next);
      setUiPreferencesDraft(next);
      setUiPreferencesPath(payload.file_path ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存页面用户设置失败");
    } finally {
      setIsSavingUiPreferences(false);
    }
  }

  function updateUiEnabled(enabled: boolean) {
    applyUiPreferencesDraft({ ...uiPreferencesDraft, enabled });
  }

  function updateUiStyleValue(field: keyof UiStyleValues, value: string) {
    const nextStyle = { ...activeUiStyle };
    if (value === "") {
      delete nextStyle[field];
    } else {
      const normalized = normalizeUiStyleValues({ [field]: Number(value) });
      const normalizedValue = normalized[field];
      if (normalizedValue !== undefined) {
        nextStyle[field] = normalizedValue;
      }
    }
    applyUiPreferencesDraft({
      ...uiPreferencesDraft,
      styles: {
        ...uiPreferencesDraft.styles,
        [activeUiTarget]: nextStyle,
      },
    });
  }

  function resetActiveUiStyle() {
    const nextStyles = { ...uiPreferencesDraft.styles };
    delete nextStyles[activeUiTarget];
    applyUiPreferencesDraft({ ...uiPreferencesDraft, styles: nextStyles });
  }

  function updateUiTextValue(value: string) {
    applyUiPreferencesDraft({
      ...uiPreferencesDraft,
      text: {
        ...uiPreferencesDraft.text,
        [activeUiTextKey]: value,
      },
    });
  }

  function resetActiveUiText() {
    const nextText = { ...uiPreferencesDraft.text };
    delete nextText[activeUiTextKey];
    applyUiPreferencesDraft({ ...uiPreferencesDraft, text: nextText });
  }

  function resetAllUiPreferences() {
    applyUiPreferencesDraft(EMPTY_UI_PREFERENCES);
    setIsUiPickMode(false);
  }

  function handleUiPick(event: MouseEvent<HTMLElement>) {
    if (!isUiPickMode) return;
    const target = event.target as HTMLElement | null;
    if (!target || target.closest(".ui-tuner-panel, .settings-modal, .modal-backdrop")) return;
    const textTarget = target.closest<HTMLElement>("[data-ui-text-key]");
    const textKey = textTarget?.dataset.uiTextKey;
    const tunable = target.closest<HTMLElement>("[data-ui-key]");
    const key = tunable?.dataset.uiKey as UiTunerTargetId | undefined;
    const hasStyleTarget = Boolean(key && UI_TUNER_TARGETS.some((item) => item.id === key));
    const hasTextTarget = isUiTextTargetId(textKey);
    if (!hasStyleTarget && !hasTextTarget) return;
    event.preventDefault();
    event.stopPropagation();
    if (hasStyleTarget && key) setActiveUiTarget(key);
    if (hasTextTarget) setActiveUiTextKey(textKey);
    setIsUiPickMode(false);
    setIsUiTunerOpen(true);
  }

  function makeZhisuanMessageId() {
    return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function appendUserCommand(content: string) {
    setIsChatOpen(true);
    setIsAiDockCollapsed(false);
    setChatMessages((current) => [
      ...current,
      {
        id: makeZhisuanMessageId(),
        role: "user",
        content,
        displayContent: content,
        isTyping: false,
        source: "command",
      },
    ]);
  }

  function appendZhisuanMessage(
    content: string,
    source: ChatMessage["source"] = "system",
    options: { typing?: boolean; rowDetailContext?: RowAiContext } = {},
  ) {
    const id = makeZhisuanMessageId();
    const shouldType = options.typing ?? true;
    setIsChatOpen(true);
    setChatMessages((current) => [
      ...current,
      {
        id,
        role: "assistant",
        content,
        displayContent: shouldType ? "" : content,
        isTyping: shouldType,
        source,
        rowDetailContext: options.rowDetailContext,
      },
    ]);
    return id;
  }

  function replaceZhisuanMessage(
    id: string,
    content: string,
    source: ChatMessage["source"] = "model",
    options: { typing?: boolean; rowDetailContext?: RowAiContext } = {},
  ) {
    const shouldType = options.typing ?? true;
    setChatMessages((current) =>
      current.map((message) =>
        message.id === id
          ? {
              ...message,
              content,
              displayContent: shouldType ? "" : content,
              isTyping: shouldType,
              source,
              rowDetailContext: options.rowDetailContext ?? message.rowDetailContext,
            }
          : message,
      ),
    );
  }

  function revealZhisuanMessage(id?: string) {
    if (!id) return;
    setChatMessages((current) =>
      current.map((message) =>
        message.id === id && message.role === "assistant"
          ? { ...message, displayContent: message.content, isTyping: false }
          : message,
      ),
    );
  }

  function describeTopWarnings(details: WarningDetail[]) {
    const high = details.filter((warning) => warning.severity === "high").slice(0, 5);
    const low = details.filter((warning) => warning.severity === "low").slice(0, 5);
    const format = (warning: WarningDetail) =>
      `${warning.sheet_name} 第${warning.excel_row}行 ${warning.metric}：${warning.message}`;
    const highText = high.length ? high.map(format).join("\n") : "暂无高风险。";
    const lowText = low.length ? low.map(format).join("\n") : "暂无低风险。";
    return `我把预警结果收拢好了。\n高风险前5条：\n${highText}\n\n低风险前5条：\n${lowText}`;
  }

  function summarizeResultForZhisuan(payload: ProcessResult) {
    const summary = payload.summary;
    if (summary.matching_status === "pending") {
      return [
        "已完成表格读取和可视化预览。",
        `我识别到 ${summary.total_data_rows} 行待处理明细，还没有批量填写价格和两个系数。`,
        "请点击下方按钮进入表格预览页，再在预览窗口点击“批量匹配”。我会按知识库和规则层开始逐行填价，并同步刷新 Excel、公式和报告。",
        ZHISUAN_PREVIEW_ACTION,
      ].join("\n");
    }
    return [
      "批量匹配完成，我先给你报个数。",
      `输入 ${summary.total_data_rows} 行，已填 ${summary.filled_rows} 行，结构匹配 ${summary.matched_rows} 行，待复核 ${summary.review_rows} 行。`,
      "下一步可以让我跑“经验池预警分析”，也可以直接“输出风险报告”。",
    ].join("\n");
  }

  function isCurrentResultJob(jobId: string) {
    return activeResultJobIdRef.current === jobId;
  }

  function setResultForCurrentJob(jobId: string, payload: ProcessResult) {
    if (!isCurrentResultJob(jobId)) return false;
    setResult(payload);
    return true;
  }

  function markReportPreviewUpdated(jobId: string, message: string) {
    if (!isCurrentResultJob(jobId)) return;
    setReportPreviewUpdateMessage(message);
    setReportPreviewRevision((current) => current + 1);
  }

  function refreshCurrentReportPreview() {
    if (!hasCurrentReport) return;
    setReportPreviewUpdateMessage("正在重新读取当前任务的最新 Word 报告…");
    setReportPreviewRevision((current) => current + 1);
  }

  function openDownload(url: string, label: string) {
    window.open(url, "_blank", "noopener,noreferrer");
    appendZhisuanMessage(`${label}已经准备好，我已触发下载。文件仍然来自系统原始输出，不经过大模型改写。`, "command");
  }

  function detectZhisuanCommand(message: string): ZhisuanCommand | null {
    const compact = message.replace(/\s+/g, "").toLowerCase();
    const asksAboutCommand =
      compact.includes("怎么") ||
      compact.includes("如何") ||
      compact.includes("为什么") ||
      compact.includes("是什么") ||
      compact.includes("什么意思") ||
      compact.includes("依据") ||
      compact.includes("来源");
    if (asksAboutCommand) return null;
    if (compact === "批量匹配" || compact.includes("执行批量匹配") || compact.includes("开始批量匹配")) return "batch-match";
    if (compact.includes("预警分析") || compact.includes("运行经验池") || compact === "经验池预警") return "experience-warning";
    if (compact.includes("输出风险报告") || compact.includes("生成ai审查摘要") || compact.includes("生成审查摘要")) return "risk-report";
    if (compact.includes("输出excel") || compact.includes("下载excel") || compact.includes("下载xlsx") || compact.includes("输出表格")) return "download-excel";
    if (compact.includes("输出word") || compact.includes("下载word") || compact.includes("下载docx") || compact.includes("输出报告")) return "download-word";
    return null;
  }

  function parseForceKnowledgePrompt(message: string) {
    const cleanMessage = message.trim();
    for (const prefix of FORCE_KNOWLEDGE_PREFIXES) {
      if (cleanMessage.startsWith(prefix)) {
        return {
          forced: true,
          question: cleanMessage.slice(prefix.length).replace(/^[\s:：,，.。;；]+/, "").trim(),
        };
      }
    }
    return { forced: false, question: cleanMessage };
  }

  function isKnowledgeQuestion(message: string) {
    if (parseForceKnowledgePrompt(message).forced) return true;
    const compact = message.replace(/\s+/g, "").toLowerCase();
    return [
      "哪里来的",
      "哪来的",
      "依据",
      "标准",
      "为什么",
      "什么意思",
      "解释",
      "来源",
      "出处",
      "0.22",
      "22%",
      "0.6",
      "1.3",
      "1.5",
      "技术工作费",
      "实物工作费",
      "实物工作系数",
      "实物工作费系数",
      "实物系数",
      "附加调整系数",
      "经验提示",
      "第二层",
      "待复核",
      "预警",
      "不能连乘",
      "标黄",
      "标红",
      "风险报告怎么",
      "审查摘要怎么",
      "问问智算",
      "强制知识库",
      "行级ai",
      "行级复核",
    ].some((term) => compact.includes(term.toLowerCase()));
  }

  function knowledgeRowContext(context: RowAiContext | null) {
    if (!context) return null;
    return {
      sheet_name: context.sheetName,
      row_number: context.rowNumber,
      values: context.values,
    };
  }

  function formatKnowledgeAnswer(payload: KnowledgeAskResponse, options: { forcedKnowledge?: boolean } = {}) {
    const forcedKnowledge = options.forcedKnowledge || Boolean(payload.forced_knowledge);
    const knowledgeModeLine = forcedKnowledge
      ? "已调用知识库：本次回答先检索本地规则、知识库和当前行上下文。"
      : "";
    if (!payload.evidence_found || payload.sources.length === 0) {
      return [knowledgeModeLine, payload.answer].filter(Boolean).join("\n\n");
    }
    const sourceLines = payload.sources.slice(0, 5).map((source, index) => {
      const title = source.title_path ? ` / ${source.title_path}` : "";
      return `${index + 1}. ${source.source_file}${title}`;
    });
    const hasSourceSection = payload.answer.includes("依据来源");
    const hasBoundaryTip = payload.answer.includes("不改变程序填价结果") || payload.answer.includes("不改变填价结果");
    return [
      knowledgeModeLine,
      payload.answer.trim(),
      hasSourceSection ? "" : `依据来源：\n${sourceLines.join("\n")}`,
      hasBoundaryTip ? "" : "提示：本回答只解释依据，不改变程序填价结果。",
    ]
      .filter(Boolean)
      .join("\n\n");
  }

  async function handleZhisuanCommand(command: ZhisuanCommand) {
    if (command === "batch-match") {
      if (!result) {
        appendZhisuanMessage("现在还没有待匹配的预览结果。请先上传 Excel 并点击“开始转换”，生成表格预览后我再执行批量匹配。", "command");
        return;
      }
      if (result.summary.matching_status !== "pending") {
        appendZhisuanMessage("本次已经完成批量匹配，不需要重复执行。你可以继续运行经验池预警或输出风险报告。", "command");
        return;
      }
      setActiveDaweibaModule("preview");
      await runBatchMatch();
      return;
    }
    if (command === "experience-warning") {
      if (!result) {
        appendZhisuanMessage("我还没有可分析的转换结果。先上传并转换 Excel，我再帮你跑经验池预警。", "command");
        return;
      }
      appendZhisuanMessage("收到，我开始跑经验池预警。先找同类记录，再看平均值偏离率，高风险和低风险我会分开报。", "command");
      await runExperienceWarnings(true);
      return;
    }
    if (command === "risk-report") {
      if (!result) {
        appendZhisuanMessage("风险报告需要先有转换结果。你先完成填价转换，我再给你生成审查摘要。", "command");
        return;
      }
      appendZhisuanMessage("收到，我开始组织风险报告。报告会照常写回 Word，同时我也会把摘要放在这里。", "command");
      await generateRiskReport(true);
      return;
    }
    if (command === "download-excel") {
      if (!result) {
        appendZhisuanMessage("Excel 输出还没生成。先完成转换，我再帮你触发下载。", "command");
        return;
      }
      appendZhisuanMessage("收到，正在导出 Excel 表格。这个动作等同于点击左侧“下载 Excel”。", "command");
      openDownload(excelDownloadHref, "Excel 表格");
      return;
    }
    if (command === "download-word") {
      if (!reportDownloadHref) {
        appendZhisuanMessage("Word 报告还没生成。请先完成批量匹配，我再帮你触发下载。", "command");
        return;
      }
      appendZhisuanMessage("收到，正在导出 Word 报告。这个动作等同于点击左侧“下载 Word”。", "command");
      openDownload(reportDownloadHref, "Word 报告");
    }
  }

  async function runZhisuanQuickCommand(command: ZhisuanCommand, prompt: string) {
    appendUserCommand(prompt);
    await handleZhisuanCommand(command);
  }

  async function runZhisuanSuggestion(prompt: string) {
    appendUserCommand(prompt);
    setChatInput("");
    if (prompt.includes("生成") || prompt.includes("摘要")) {
      await handleZhisuanCommand("risk-report");
      return;
    }
    if (prompt.includes("预警")) {
      const details = result?.summary.warning_details ?? [];
      if (!result) {
        appendZhisuanMessage("我还没有转换结果，暂时看不到预警集中情况。先完成转换，再跑经验池预警分析。", "command");
        return;
      }
      if (!result.summary.warning_summary?.executed) {
        appendZhisuanMessage("本次还没有运行经验池预警。你可以点“经验池预警分析”，我会把高风险和低风险前 5 条收拢给你。", "command");
        return;
      }
      appendZhisuanMessage(describeTopWarnings(details), "command");
      return;
    }
    if (prompt.includes("优先复核")) {
      if (!result) {
        appendZhisuanMessage("我还没有转换结果。先上传并转换 Excel，完成后我会按待复核、预警等级和未命中原因提示优先级。", "command");
        return;
      }
      const warningRows = (result.summary.warning_details ?? [])
        .slice(0, 5)
        .map((warning) => `${warning.sheet_name} 第${warning.excel_row}行：${warning.metric} ${warning.message}`);
      appendZhisuanMessage(
        [
          `我建议优先看三类：高风险预警行、待复核 ${result.summary.review_rows} 行、以及报告里标黄或说明为“第二层经验提示层”的行。`,
          warningRows.length ? `当前预警靠前的行：\n${warningRows.join("\n")}` : "当前还没有可列出的预警明细。若需要更像审查清单，先运行经验池预警分析。",
        ].join("\n\n"),
        "command",
      );
      return;
    }
    if (prompt.includes("待复核")) {
      if (rowAiContext) {
        await askKnowledgeQuestion(prompt, knowledgeRowContext(rowAiContext), "行级知识库复核");
        return;
      }
      await askKnowledgeQuestion(prompt, null, "知识库问答");
      return;
    }
    if (isKnowledgeQuestion(prompt)) {
      await askKnowledgeQuestion(prompt, knowledgeRowContext(rowAiContext), "知识库问答");
      return;
    }
    appendZhisuanMessage("这个问题我可以回答，但如果要调用在线大模型，请直接在输入框里发送。我会把失败降级为“智算辅助暂不可用”，不影响主流程。", "command");
  }

  async function runZhisuanQuickItem(item: ZhisuanQuickItem) {
    if (item.source === "custom") {
      setChatInput(item.prompt);
      setIsChatOpen(true);
      setIsAiDockCollapsed(false);
      window.setTimeout(() => chatInputRef.current?.focus(), 0);
      return;
    }
    if (item.kind === "command" && item.command) {
      await runZhisuanQuickCommand(item.command, item.prompt);
      return;
    }
    const forcedKnowledge = parseForceKnowledgePrompt(item.prompt);
    if (forcedKnowledge.forced) {
      appendUserCommand(item.prompt);
      setChatInput("");
      if (!forcedKnowledge.question) {
        appendZhisuanMessage("请输入知识库问题，例如：@知识库：第二层经验提示是什么意思？", "command");
        return;
      }
      await askKnowledgeQuestion(forcedKnowledge.question, knowledgeRowContext(rowAiContext), "强制知识库问答", { forcedKnowledge: true });
      return;
    }
    const detectedCommand = detectZhisuanCommand(item.prompt);
    if (detectedCommand) {
      appendUserCommand(item.prompt);
      await handleZhisuanCommand(detectedCommand);
      return;
    }
    if (ZHISUAN_BUILTIN_QUICK_ITEMS.some((builtin) => builtin.id === item.id)) {
      await runZhisuanSuggestion(item.prompt);
      return;
    }
    appendUserCommand(item.prompt);
    setChatInput("");
    await askZhisuanFreeform(item.prompt);
  }

  function toggleZhisuanQuickItem(id: string, checked: boolean) {
    setZhisuanQuickSettings((current) => {
      const enabledIds = checked
        ? Array.from(new Set([...current.enabledIds, id]))
        : current.enabledIds.filter((itemId) => itemId !== id);
      return { ...current, enabledIds };
    });
  }

  function saveCustomZhisuanQuickCommands() {
    const customPrompts = parsePreferenceText(customQuickCommandDraft)
      .filter((value) => !ZHISUAN_QUICK_PROMPT_BLOCKLIST.has(value))
      .slice(0, 12);
    setCustomQuickCommandDraft(preferenceText(customPrompts));
    setZhisuanQuickSettings((current) => ({ ...current, customPrompts }));
  }

  function saveZhisuanChatHeightSetting() {
    const nextHeight = clampZhisuanChatHeight(zhisuanChatHeightDraft);
    setZhisuanChatHeight(nextHeight);
    setZhisuanChatHeightDraft(String(nextHeight));
  }

  function saveZhisuanDockWidthSetting() {
    const nextWidth = clampZhisuanDockWidth(zhisuanDockWidthDraft);
    setZhisuanDockWidth(nextWidth);
    setZhisuanDockWidthDraft(String(nextWidth));
  }

  function saveZhisuanWelcomeMessage() {
    const nextMessage = zhisuanWelcomeDraft.replace(/\r/g, "").trim() || zhisuanWindowDefaults.welcomeMessage;
    setZhisuanWelcomeDraft(nextMessage);
    setZhisuanWelcomeMessage(nextMessage);
  }

  function resetZhisuanWelcomeMessage() {
    const nextMessage = zhisuanWindowDefaults.welcomeMessage;
    setZhisuanWelcomeDraft(nextMessage);
    setZhisuanWelcomeMessage(nextMessage);
  }

  function updateZhisuanQuickAutoHide(autoHide: boolean) {
    setZhisuanQuickSettings((current) => ({ ...current, autoHide }));
  }

  function updateZhisuanDockVisibility(key: ZhisuanDockVisibilityKey, visible: boolean) {
    setZhisuanDockVisibility((current) => ({ ...current, [key]: visible }));
    if (key === "debugInfo" && !visible) {
      setIsLlmDebugOpen(false);
    }
  }

  function resetZhisuanQuickSettings() {
    const nextSettings = zhisuanWindowDefaults.quickSettings;
    setZhisuanQuickSettings(nextSettings);
    setCustomQuickCommandDraft(preferenceText(nextSettings.customPrompts));
  }

  function allowsEmptyElement(field: MappingField) {
    return (ELEMENT_FIELDS as readonly string[]).includes(field);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0] ?? null);
  }

  function applyZhisuanWindowSettings(raw?: ZhisuanWindowSettingsPayload) {
    const defaults = normalizeZhisuanWindowSettings(raw);
    setZhisuanWindowDefaults(defaults);
    setZhisuanChatHeight(defaults.chatHeight);
    setZhisuanChatHeightDraft(String(defaults.chatHeight));
    setZhisuanDockWidth(defaults.dockWidth);
    setZhisuanDockWidthDraft(String(defaults.dockWidth));
    setUseZhisuanDockViewportHeight(defaults.useViewportHeight);
    setZhisuanQuickSettings(defaults.quickSettings);
    setCustomQuickCommandDraft(preferenceText(defaults.quickSettings.customPrompts));
    setZhisuanDockVisibility(defaults.dockVisibility);
    setZhisuanWelcomeMessage(defaults.welcomeMessage);
    setZhisuanWelcomeDraft(defaults.welcomeMessage);
    setZhisuanDockStyle(defaults.dockStyle);
    if (!defaults.dockVisibility.debugInfo) setIsLlmDebugOpen(false);
  }

  function restoreZhisuanWindowProjectDefaults() {
    applyZhisuanWindowSettings(zhisuanWindowDefaults);
  }

  function applyProjectDefaultSettings(payload: ProjectDefaultSettingsPayload) {
    applyZhisuanWindowSettings(payload.zhisuanWindow);
    const previewDefaults = normalizePreviewColumnPreferences(payload.previewColumns);
    setPreviewColumnPreferences(previewDefaults);
    setPreviewDefaultLabelsDraft(preferenceText(previewDefaults.defaultLabels));

    const inputMapping = payload.inputMapping ?? {};
    const inputDefaults = normalizeInputFieldPreferences(inputMapping.fieldPreferences);
    setHeaderRow(Math.max(1, Math.floor(Number(inputMapping.headerRow ?? 4) || 4)));
    setOutputMatchReport(inputMapping.outputMatchReport ?? true);
    setOnlyMatchRowsWithValue(inputMapping.onlyMatchRowsWithValue ?? true);
    setMatchValueFilterField(normalizeWarningFilterFieldValue(inputMapping.matchValueFilterField));
    setMergeVerticalCells(inputMapping.mergeVerticalCells ?? true);
    setMergeHorizontalCells(inputMapping.mergeHorizontalCells ?? true);
    setInputFieldDefaults(inputDefaults);
    setInputFieldDraft(inputDefaults);
    setInputFieldPreferencesPath(payload.file_path ?? "");

    const workloadDefaults = payload.workloadCapture ?? {};
    const sourceDefaults = workloadDefaults.source ?? {};
    const targetDefaults = workloadDefaults.target ?? {};
    const sourcePreferences = normalizeWorkloadFieldPreferences(sourceDefaults.fieldPreferences);
    const targetPreferences = normalizeWorkloadTargetFieldPreferences(targetDefaults.fieldPreferences);
    setSelectedWorkloadFields(normalizeWorkloadSelectedFields(workloadDefaults.selectedFields));
    setWorkloadWriteMode(normalizeWorkloadWriteModeValue(workloadDefaults.writeMode));
    setOnlyCaptureWorkloadRowsWithValue(workloadDefaults.onlyCaptureRowsWithValue ?? true);
    setWorkloadValueFilterField(normalizeWorkloadSourceFieldValue(workloadDefaults.valueFilterField));
    setWorkloadFieldDefaults(sourcePreferences);
    setWorkloadFieldDraft(sourcePreferences);
    setWorkloadAdjacentFallbackEnabled(sourceDefaults.adjacentFallbackEnabled ?? true);
    setWorkloadElementSequenceEnabled(sourceDefaults.elementSequenceEnabled ?? true);
    setWorkloadFieldPreferencesPath(payload.file_path ?? "");
    setWorkloadTargetFieldDefaults(targetPreferences);
    setWorkloadTargetFieldDraft(targetPreferences);
    setWorkloadTargetAdjacentFallbackEnabled(targetDefaults.adjacentFallbackEnabled ?? true);
    setWorkloadTargetElementSequenceEnabled(targetDefaults.elementSequenceEnabled ?? false);
    setWorkloadTargetFieldPreferencesPath(payload.file_path ?? "");
  }

  async function loadProjectDefaultSettings() {
    try {
      const response = await fetch(`${API_BASE}/api/project-default-settings`);
      if (!response.ok) return null;
      const payload = (await response.json()) as ProjectDefaultSettingsPayload;
      applyProjectDefaultSettings(payload);
      return payload;
    } catch {
      // The built-in defaults remain usable if the backend is still starting.
      return null;
    } finally {
      setIsZhisuanWelcomeLoaded(true);
    }
  }

  function applyFeishuWebhookStatus(payload: FeishuWebhookStatus) {
    const notifications = {
      ...DEFAULT_FEISHU_NOTIFICATION_SWITCHES,
      ...(payload.notifications ?? {}),
    };
    const normalized = { ...EMPTY_FEISHU_WEBHOOK_STATUS, ...payload, notifications };
    setFeishuWebhookStatus(normalized);
    setFeishuEnabledDraft(normalized.enabled);
    setFeishuNotificationDraft(notifications);
    setFeishuAppUrlDraft(normalized.app_url ?? "");
  }

  async function loadFeishuWebhookData() {
    setIsLoadingFeishuWebhook(true);
    try {
      const [statusResponse, historyResponse, appBotResponse] = await Promise.all([
        fetch(`${API_BASE}/api/collaboration/feishu-webhook/status`),
        fetch(`${API_BASE}/api/collaboration/feishu-webhook/history?limit=30`),
        fetch(`${API_BASE}/api/collaboration/feishu-app-bot/status`),
      ]);
      if (!statusResponse.ok) throw new Error(`读取连接状态失败：${statusResponse.status}`);
      const statusPayload = (await statusResponse.json()) as FeishuWebhookStatus;
      const historyPayload = historyResponse.ok
        ? await historyResponse.json() as { items?: FeishuDeliveryRecord[] }
        : { items: [] };
      applyFeishuWebhookStatus(statusPayload);
      setFeishuWebhookHistory(Array.isArray(historyPayload.items) ? historyPayload.items : []);
      if (appBotResponse.ok) setFeishuAppBotStatus(await appBotResponse.json() as FeishuAppBotStatus);
    } catch (err) {
      setFeishuWebhookFeedback(err instanceof Error ? err.message : "读取飞书 Webhook 状态失败");
    } finally {
      setIsLoadingFeishuWebhook(false);
    }
  }

  async function loadFeishuBotConsole(silent = false) {
    if (!silent) setIsLoadingFeishuBotConsole(true);
    try {
      const [statusResponse, consoleResponse] = await Promise.all([
        fetch(`${API_BASE}/api/collaboration/feishu-app-bot/status`),
        fetch(`${API_BASE}/api/collaboration/feishu-app-bot/logs?limit=160`),
      ]);
      if (statusResponse.ok) setFeishuAppBotStatus(await statusResponse.json() as FeishuAppBotStatus);
      if (!consoleResponse.ok) throw new Error(`读取机器人日志失败：${consoleResponse.status}`);
      const payload = await consoleResponse.json() as { items?: FeishuBotConsoleEvent[] };
      setFeishuBotConsoleEvents(Array.isArray(payload.items) ? payload.items : []);
    } catch (err) {
      if (!silent) setFeishuWebhookFeedback(err instanceof Error ? err.message : "读取机器人运行日志失败");
    } finally {
      if (!silent) setIsLoadingFeishuBotConsole(false);
    }
  }

  function openFeishuBotConsole() {
    setIsFeishuBotConsoleOpen(true);
    void loadFeishuBotConsole();
  }

  async function saveFeishuWebhookSettings() {
    setIsSavingFeishuWebhook(true);
    setFeishuWebhookFeedback("");
    const payload: Record<string, unknown> = {
      enabled: feishuEnabledDraft,
      app_url: feishuAppUrlDraft.trim(),
      notifications: feishuNotificationDraft,
    };
    if (feishuWebhookDraft.trim()) payload.webhook_url = feishuWebhookDraft.trim();
    if (feishuSecretDraft.trim()) payload.secret = feishuSecretDraft.trim();
    try {
      const response = await fetch(`${API_BASE}/api/collaboration/feishu-webhook/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        throw new Error(errorPayload?.detail ?? `保存失败：${response.status}`);
      }
      applyFeishuWebhookStatus(await response.json() as FeishuWebhookStatus);
      setFeishuWebhookDraft("");
      setFeishuSecretDraft("");
      setFeishuWebhookFeedback("设置已保存。地址和签名密钥不会回显到前端。");
    } catch (err) {
      setFeishuWebhookFeedback(err instanceof Error ? err.message : "保存飞书 Webhook 设置失败");
    } finally {
      setIsSavingFeishuWebhook(false);
    }
  }

  async function toggleFeishuWebhook(enabled: boolean) {
    setFeishuEnabledDraft(enabled);
    setIsSavingFeishuWebhook(true);
    setFeishuWebhookFeedback("");
    try {
      const response = await fetch(`${API_BASE}/api/collaboration/feishu-webhook/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (!response.ok) throw new Error(`切换失败：${response.status}`);
      applyFeishuWebhookStatus(await response.json() as FeishuWebhookStatus);
      setFeishuWebhookFeedback(enabled ? "第一层 Webhook 通知已启用。" : "第一层 Webhook 通知已关闭。");
    } catch (err) {
      setFeishuEnabledDraft(!enabled);
      setFeishuWebhookFeedback(err instanceof Error ? err.message : "切换第一层 Webhook 失败");
    } finally {
      setIsSavingFeishuWebhook(false);
    }
  }

  async function selectFeishuWebhookProfile(profileId: string) {
    if (!profileId || profileId === feishuWebhookStatus.active_profile) return;
    setIsSavingFeishuWebhook(true);
    setFeishuWebhookFeedback("正在切换第一层 Webhook 配置。");
    try {
      const response = await fetch(`${API_BASE}/api/collaboration/feishu-webhook/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: feishuEnabledDraft, profile_id: profileId }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `切换失败：${response.status}`);
      }
      const latestStatus = await response.json() as FeishuWebhookStatus;
      applyFeishuWebhookStatus(latestStatus);
      const selected = latestStatus.profiles.find((profile) => profile.profile_id === latestStatus.active_profile);
      setFeishuWebhookFeedback(`已切换为${selected?.label ?? "当前 Webhook"}${latestStatus.enabled ? "，通知已启用。" : "。"}`);
    } catch (err) {
      setFeishuWebhookFeedback(err instanceof Error ? err.message : "切换第一层 Webhook 配置失败");
      await loadFeishuWebhookData();
    } finally {
      setIsSavingFeishuWebhook(false);
    }
  }

  async function toggleFeishuAppBot(enabled: boolean) {
    setIsTogglingFeishuAppBot(true);
    setFeishuWebhookFeedback("");
    try {
      const response = await fetch(`${API_BASE}/api/collaboration/feishu-app-bot/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `切换失败：${response.status}`);
      }
      const initialStatus = await response.json() as FeishuAppBotStatus;
      setFeishuAppBotStatus(initialStatus);
      setFeishuWebhookFeedback(enabled ? "第二层机器人已启用，正在建立长连接。" : "第二层机器人已关闭，本机不再接收飞书文件。运行中的任务不会被转交给其他实例。");
      let latestStatus = initialStatus;
      for (let attempt = 0; attempt < 10 && latestStatus.running !== enabled; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const statusResponse = await fetch(`${API_BASE}/api/collaboration/feishu-app-bot/status`);
        if (!statusResponse.ok) break;
        latestStatus = await statusResponse.json() as FeishuAppBotStatus;
        setFeishuAppBotStatus(latestStatus);
      }
      if (enabled && !latestStatus.running) {
        setFeishuWebhookFeedback("第二层机器人已启用，但10秒内未建立长连接，请查看机器人运行日志或重新启动造价智算。");
      } else if (enabled) {
        setFeishuWebhookFeedback("第二层机器人已启用并开始接收飞书任务。");
      } else {
        setFeishuWebhookFeedback("第二层机器人已关闭，本机长连接已经退出。");
      }
    } catch (err) {
      setFeishuWebhookFeedback(err instanceof Error ? err.message : "切换第二层机器人失败");
    } finally {
      setIsTogglingFeishuAppBot(false);
    }
  }

  async function selectFeishuAppBotProfile(profileId: string) {
    if (!profileId || profileId === feishuAppBotStatus?.active_profile) return;
    setIsTogglingFeishuAppBot(true);
    setFeishuWebhookFeedback("正在切换第二层机器人配置，当前长连接会先安全退出。");
    try {
      const enabled = Boolean(feishuAppBotStatus?.enabled);
      const response = await fetch(`${API_BASE}/api/collaboration/feishu-app-bot/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled, profile_id: profileId }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `切换失败：${response.status}`);
      }
      let latestStatus = await response.json() as FeishuAppBotStatus;
      setFeishuAppBotStatus(latestStatus);
      for (let attempt = 0; enabled && attempt < 10 && latestStatus.running !== enabled; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const statusResponse = await fetch(`${API_BASE}/api/collaboration/feishu-app-bot/status`);
        if (!statusResponse.ok) break;
        latestStatus = await statusResponse.json() as FeishuAppBotStatus;
        setFeishuAppBotStatus(latestStatus);
      }
      const selected = latestStatus.profiles.find((profile) => profile.profile_id === latestStatus.active_profile);
      setFeishuWebhookFeedback(enabled && !latestStatus.running
        ? "机器人配置已切换，但长连接尚未恢复，请查看运行状态。"
        : `已切换为${selected?.label ?? "当前机器人"}${enabled ? "，长连接已运行。" : "。"}`);
    } catch (err) {
      setFeishuWebhookFeedback(err instanceof Error ? err.message : "切换第二层机器人配置失败");
      await loadFeishuWebhookData();
    } finally {
      setIsTogglingFeishuAppBot(false);
    }
  }

  async function clearFeishuWebhookSettings() {
    if (!window.confirm("确定清空当前选中的 Webhook 配置吗？其他 Webhook 配置不会被删除。")) return;
    setIsSavingFeishuWebhook(true);
    setFeishuWebhookFeedback("");
    try {
      const response = await fetch(`${API_BASE}/api/collaboration/feishu-webhook/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clear_credentials: true }),
      });
      if (!response.ok) throw new Error(`清空失败：${response.status}`);
      applyFeishuWebhookStatus(await response.json() as FeishuWebhookStatus);
      setFeishuWebhookDraft("");
      setFeishuSecretDraft("");
      setFeishuWebhookFeedback("当前 Webhook 配置已清除；如仍有其他配置，系统已自动切换到下一项。");
    } catch (err) {
      setFeishuWebhookFeedback(err instanceof Error ? err.message : "清空飞书 Webhook 设置失败");
    } finally {
      setIsSavingFeishuWebhook(false);
    }
  }

  async function testFeishuWebhookConnection() {
    setIsTestingFeishuWebhook(true);
    setFeishuWebhookFeedback("");
    try {
      const response = await fetch(`${API_BASE}/api/collaboration/feishu-webhook/test`, { method: "POST" });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        throw new Error(errorPayload?.detail ?? `测试发送失败：${response.status}`);
      }
      setFeishuWebhookFeedback("测试消息发送成功，请到配置的飞书群中核对。");
    } catch (err) {
      setFeishuWebhookFeedback(err instanceof Error ? err.message : "飞书 Webhook 测试发送失败");
    } finally {
      setIsTestingFeishuWebhook(false);
      await loadFeishuWebhookData();
    }
  }

  async function sendCollaborationNotification(notificationType: FeishuNotificationType, context: Record<string, unknown>) {
    try {
      await fetch(`${API_BASE}/api/collaboration/feishu-webhook/notify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notification_type: notificationType, context }),
      });
    } catch {
      // Webhook notifications are best-effort and never change the professional workflow result.
    }
  }

  async function restoreProjectDefaultSettings() {
    setError("");
    const payload = await loadProjectDefaultSettings();
    const inputPreferences = normalizeInputFieldPreferences(payload?.inputMapping?.fieldPreferences);
    const sourcePreferences = normalizeWorkloadFieldPreferences(payload?.workloadCapture?.source?.fieldPreferences);
    const targetPreferences = normalizeWorkloadTargetFieldPreferences(payload?.workloadCapture?.target?.fieldPreferences);
    if (file) {
      const config = activeSheetConfig();
      void inspectFile(file, config?.header_row ?? 4, config?.sheet_name, inputPreferences);
    }
    if (workloadFile) {
      setWorkloadFieldDraft(sourcePreferences);
      setWorkloadTargetFieldDraft(targetPreferences);
      void inspectWorkloadFile(
        workloadFile,
        "source",
        undefined,
        undefined,
        sourcePreferences,
        payload?.workloadCapture?.source?.adjacentFallbackEnabled ?? true,
        payload?.workloadCapture?.source?.elementSequenceEnabled ?? true,
      );
    }
    if (result) {
      void inspectCurrentWorkloadTarget(
        result.job_id,
        undefined,
        undefined,
        targetPreferences,
        payload?.workloadCapture?.target?.adjacentFallbackEnabled ?? true,
        payload?.workloadCapture?.target?.elementSequenceEnabled ?? false,
      );
    }
  }

  async function loadInputFieldPreferences(openAfterLoad = false) {
    setIsLoadingInputFieldSettings(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/input/field-preferences`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取输入字段设置失败：${response.status}`);
      }
      const payload = (await response.json()) as InputFieldPreferencesPayload;
      const defaults = normalizeInputFieldPreferences(payload.defaults);
      const preferences = normalizeInputFieldPreferences({ ...payload.defaults, ...payload.preferences });
      setInputFieldDefaults(defaults);
      setInputFieldDraft(preferences);
      setInputFieldPreferencesPath(payload.file_path ?? "");
      if (openAfterLoad) {
        setIsInputFieldSettingsOpen(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取输入字段设置失败");
    } finally {
      setIsLoadingInputFieldSettings(false);
    }
  }

  function openInputFieldSettings() {
    void loadInputFieldPreferences(true);
  }

  function updateInputFieldDraft(field: MappingField, value: string) {
    setInputFieldDraft((current) => ({ ...current, [field]: parsePreferenceText(value) }));
  }

  function resetInputFieldDraft() {
    setInputFieldDraft(inputFieldDefaults);
  }

  async function saveInputFieldPreferences() {
    setIsSavingInputFieldSettings(true);
    setError("");
    try {
      setIsInputFieldSettingsOpen(false);
      if (file) {
        const config = activeSheetConfig();
        void inspectFile(file, config?.header_row ?? headerRow, config?.sheet_name, inputFieldDraft);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "应用输入字段设置失败");
    } finally {
      setIsSavingInputFieldSettings(false);
    }
  }

  function openPreviewSettings() {
    const currentSheetKey = previewSheetKey(activePreview);
    setActivePreviewSettingsSheetName(currentSheetKey);
    setPreviewDefaultLabelsDraft(preferenceText(previewColumnPreferences.defaultLabels));
    setIsPreviewSettingsOpen(true);
  }

  function updatePreviewSheetColumns(label: string, checked: boolean) {
    const sheetKey = previewSheetKey(activePreviewSettingsSheet);
    if (!sheetKey) return;
    const currentPreferenceLabels = previewColumnPreferences.sheetOverrides[sheetKey] ?? previewColumnPreferences.defaultLabels;
    const current = resolvePreviewPreferenceLabels(
      previewSettingColumns,
      currentPreferenceLabels,
      activePreviewSettingsSheet,
      result?.summary.price_column,
    );
    const next = checked ? [...current, label] : current.filter((item) => item !== label);
    const deduped = Array.from(new Set(next));
    setPreviewColumnPreferences((previous) => ({
      ...previous,
      sheetOverrides: deduped.length > 0
        ? { ...previous.sheetOverrides, [sheetKey]: deduped }
        : Object.fromEntries(
            Object.entries(previous.sheetOverrides).filter(([key]) => key !== sheetKey),
          ),
    }));
  }

  function resetPreviewSheetColumns() {
    const sheetKey = previewSheetKey(activePreviewSettingsSheet);
    if (!sheetKey) return;
    setPreviewColumnPreferences((previous) => ({
      ...previous,
      sheetOverrides: Object.fromEntries(
        Object.entries(previous.sheetOverrides).filter(([key]) => key !== sheetKey),
      ),
    }));
  }

  function updatePreviewSheetHeaderRow(sheet: TablePreview, value: number) {
    const sheetKey = previewSheetKey(sheet);
    if (!sheetKey) return;
    const rowNumber = Math.max(1, Math.floor(value || 1));
    setPreviewColumnPreferences((previous) =>
      normalizePreviewColumnPreferences({
        ...previous,
        headerRows: {
          ...previous.headerRows,
          [sheetKey]: rowNumber,
        },
      }),
    );
  }

  function previewHeaderRowValue(sheet: TablePreview) {
    const sheetKey = previewSheetKey(sheet);
    return previewColumnPreferences.headerRows[sheetKey] ?? sheet.header_row ?? 1;
  }

  function updatePreviewMaxDisplayChars(value: number) {
    const maxDisplayChars = Math.max(4, Math.min(40, Math.floor(value || DEFAULT_PREVIEW_CELL_MAX_DISPLAY_CHARS)));
    setPreviewColumnPreferences((previous) =>
      normalizePreviewColumnPreferences({
        ...previous,
        maxDisplayChars,
      }),
    );
  }

  function previewColumnSavedWidth(sheet: TablePreview, column: PreviewColumn) {
    const sheetKey = previewSheetKey(sheet);
    const savedWidths = previewColumnPreferences.columnWidths[sheetKey] ?? {};
    for (const key of previewColumnWidthKeys(column)) {
      const width = savedWidths[key];
      if (width) return width;
    }
    return null;
  }

  function previewColumnWidthStyle(sheet: TablePreview, column: PreviewColumn) {
    const width = previewColumnSavedWidth(sheet, column);
    if (!width) return undefined;
    return { "--preview-column-width": `${width}px` } as CSSProperties;
  }

  function resizePreviewColumn(sheet: TablePreview, column: PreviewColumn, width: number) {
    const sheetKey = previewSheetKey(sheet);
    const clampedWidth = clampPreviewColumnWidth(width);
    if (!sheetKey || clampedWidth === null) return;
    setPreviewColumnPreferences((previous) => {
      const nextSheetWidths = { ...(previous.columnWidths[sheetKey] ?? {}) };
      for (const key of previewColumnWidthKeys(column)) {
        nextSheetWidths[key] = clampedWidth;
      }
      return normalizePreviewColumnPreferences({
        ...previous,
        columnWidths: {
          ...previous.columnWidths,
          [sheetKey]: nextSheetWidths,
        },
      });
    });
  }

  function startPreviewColumnResize(
    event: ReactPointerEvent<HTMLSpanElement>,
    sheet: TablePreview,
    column: PreviewColumn,
  ) {
    const headerCell = event.currentTarget.parentElement;
    const currentWidth = headerCell?.getBoundingClientRect().width ?? previewColumnSavedWidth(sheet, column) ?? 112;
    const startX = event.clientX;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;

    event.preventDefault();
    event.stopPropagation();
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const handlePointerMove = (pointerEvent: PointerEvent) => {
      pointerEvent.preventDefault();
      resizePreviewColumn(sheet, column, currentWidth + pointerEvent.clientX - startX);
    };
    const handlePointerUp = (pointerEvent: PointerEvent) => {
      pointerEvent.preventDefault();
      resizePreviewColumn(sheet, column, currentWidth + pointerEvent.clientX - startX);
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
  }

  function buildPreviewHeaderRows(preferences: PreviewColumnPreferences, sheets: TablePreview[] = previewSheets) {
    return Object.fromEntries(
      sheets
        .map((sheet) => {
          const sheetKey = previewSheetKey(sheet);
          const rowNumber = preferences.headerRows[sheetKey] ?? sheet.header_row ?? 1;
          return [sheetKey, Math.max(1, Math.floor(Number(rowNumber) || 1))] as const;
        })
        .filter(([sheetKey]) => Boolean(sheetKey)),
    );
  }

  function hasPreviewHeaderRowOverrides(sheets: TablePreview[], preferences: PreviewColumnPreferences) {
    return sheets.some((sheet) => Object.prototype.hasOwnProperty.call(preferences.headerRows, previewSheetKey(sheet)));
  }

  async function refreshPreviewWithPreferences(baseResult: ProcessResult, preferences: PreviewColumnPreferences) {
    const sheets = previewSheetsFromTablePreview(baseResult.summary.table_preview);
    const response = await fetch(`${API_BASE}/api/preview/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: baseResult.job_id,
        header_rows: buildPreviewHeaderRows(preferences, sheets),
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(payload?.detail ?? `刷新预览失败：${response.status}`);
    }
    return (await response.json()) as ProcessResult;
  }

  async function refreshActivePreviewSettingsSheet() {
    if (!result) return;
    const requestJobId = result.job_id;
    const currentSheetKey = previewSheetKey(activePreviewSettingsSheet);
    setIsRefreshingPreviewSettings(true);
    setError("");
    try {
      const payload = await refreshPreviewWithPreferences(result, previewColumnPreferences);
      if (!setResultForCurrentJob(requestJobId, payload)) return;
      setActivePreviewSettingsSheetName(currentSheetKey);
    } catch (err) {
      if (!isCurrentResultJob(requestJobId)) return;
      setError(err instanceof Error ? err.message : "刷新预览列名失败");
    } finally {
      setIsRefreshingPreviewSettings(false);
    }
  }

  function previewEditKey(sheetName: string, rowNumber: number, columnNumber: number) {
    return `${sheetName}::${rowNumber}::${columnNumber}`;
  }

  function startPreviewCellEdit(column: PreviewColumn, row: Array<string | number | null>, sourceIndex: number) {
    if (!result || !isEditablePreviewColumn(column)) return;
    if (committingPreviewEditRef.current || savingPreviewCellKey) return;
    const sheetName = previewSheetLabel(activePreview, 0);
    const rowNumber = previewExcelRowNumber(activePreview, sourceIndex, sheetConfigs);
    const columnNumber = column.index + 1;
    const key = previewEditKey(sheetName, rowNumber, columnNumber);
    if (savingPreviewCellKey === key) return;
    setPreviewManualEditMessage("");
    setEditingPreviewCell({
      sheetName,
      sourceIndex,
      rowNumber,
      columnIndex: column.index,
      columnNumber,
      originalValue: previewCellText(row[column.index]),
      draftValue: previewCellText(row[column.index]),
    });
  }

  function updateEditingPreviewCell(value: string) {
    setEditingPreviewCell((current) => current ? { ...current, draftValue: value } : current);
  }

  async function commitPreviewCellEdit(edit: PreviewCellEditState | null, value: string) {
    if (!edit || !result || committingPreviewEditRef.current) return;
    const requestJobId = result.job_id;
    if (value === edit.originalValue) {
      setEditingPreviewCell((current) => (
        current
        && current.sourceIndex === edit.sourceIndex
        && current.columnIndex === edit.columnIndex
        && current.rowNumber === edit.rowNumber
          ? null
          : current
      ));
      return;
    }
    const key = previewEditKey(edit.sheetName, edit.rowNumber, edit.columnNumber);
    committingPreviewEditRef.current = true;
    setSavingPreviewCellKey(key);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/preview/cell`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: requestJobId,
          sheet_name: edit.sheetName,
          row_number: edit.rowNumber,
          column_number: edit.columnNumber,
          value,
          header_rows: buildPreviewHeaderRows(previewColumnPreferences),
          recalculate: false,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `保存人工修改失败：${response.status}`);
      }
      const payload = (await response.json()) as PreviewCellUpdateResult;
      if (!setResultForCurrentJob(requestJobId, payload)) return;
      setActivePreviewSheetName(edit.sheetName);
      setPreviewManualEditMessage(`已保存人工修改：${payload.manual_edit.column_letter}${payload.manual_edit.row_number}；如影响汇总，请点“重算公式”。`);
      setEditingPreviewCell((current) => (
        current
        && current.sourceIndex === edit.sourceIndex
        && current.columnIndex === edit.columnIndex
        && current.rowNumber === edit.rowNumber
          ? null
          : current
      ));
    } catch (err) {
      if (!isCurrentResultJob(requestJobId)) return;
      setError(err instanceof Error ? err.message : "保存人工修改失败");
    } finally {
      setSavingPreviewCellKey("");
      committingPreviewEditRef.current = false;
    }
  }

  function handlePreviewEditKeyDown(event: KeyboardEvent<HTMLInputElement>, edit: PreviewCellEditState | null) {
    if (event.key === "Enter") {
      event.preventDefault();
      void commitPreviewCellEdit(edit, event.currentTarget.value);
    }
    if (event.key === "Escape") {
      event.preventDefault();
      cancelPreviewEditRef.current = true;
      setEditingPreviewCell(null);
    }
  }

  function handlePreviewEditBlur(edit: PreviewCellEditState | null, value: string) {
    if (cancelPreviewEditRef.current) {
      cancelPreviewEditRef.current = false;
      return;
    }
    void commitPreviewCellEdit(edit, value);
  }

  async function recalculatePreviewWorkbook() {
    if (!result || isRecalculatingPreview) return;
    const requestJobId = result.job_id;
    setIsRecalculatingPreview(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/preview/recalculate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: requestJobId,
          header_rows: buildPreviewHeaderRows(previewColumnPreferences),
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `重算公式失败：${response.status}`);
      }
      const payload = (await response.json()) as ProcessResult & { formula_recalculated?: boolean };
      if (!setResultForCurrentJob(requestJobId, payload)) return;
      setPreviewManualEditMessage(
        payload.formula_recalculated === false
          ? "已刷新预览和报告；本机未完成 Excel 公式缓存刷新，已尽量使用程序侧公式结果。"
          : "已重算公式并刷新 Word 报告。",
      );
      markReportPreviewUpdated(requestJobId, "公式和 Word 报告已重算，正在刷新真实预览…");
    } catch (err) {
      if (!isCurrentResultJob(requestJobId)) return;
      setError(err instanceof Error ? err.message : "重算公式失败");
    } finally {
      setIsRecalculatingPreview(false);
    }
  }

  async function savePreviewColumnPreferences() {
    const nextPreferences = normalizePreviewColumnPreferences({
      defaultLabels: parsePreferenceText(previewDefaultLabelsDraft),
      sheetOverrides: previewColumnPreferences.sheetOverrides,
      headerRows: previewColumnPreferences.headerRows,
      maxDisplayChars: previewColumnPreferences.maxDisplayChars,
      columnWidths: previewColumnPreferences.columnWidths,
    });
    setPreviewColumnPreferences(nextPreferences);
    setIsRefreshingPreviewSettings(true);
    setError("");
    try {
      if (!result) {
        setIsPreviewSettingsOpen(false);
        return;
      }
      const requestJobId = result.job_id;
      const payload = await refreshPreviewWithPreferences(result, nextPreferences);
      if (!setResultForCurrentJob(requestJobId, payload)) return;
      setActivePreviewSheetName((current) => current || payload.summary.table_preview.sheet_name || "");
      setIsPreviewSettingsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "应用或刷新预览设置失败");
    } finally {
      setIsRefreshingPreviewSettings(false);
    }
  }

  async function restorePreviewProjectDefaults() {
    setIsRefreshingPreviewSettings(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/preview-column-preferences`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取项目默认预览设置失败：${response.status}`);
      }
      const payload = (await response.json()) as PreviewColumnPreferencesPayload;
      const defaults = normalizePreviewColumnPreferences(payload.preferences ?? payload.defaults);
      setPreviewColumnPreferences(defaults);
      setPreviewDefaultLabelsDraft(preferenceText(defaults.defaultLabels));
      if (result) {
        const requestJobId = result.job_id;
        const nextResult = await refreshPreviewWithPreferences(result, defaults);
        if (!setResultForCurrentJob(requestJobId, nextResult)) return;
        setActivePreviewSheetName((current) => current || nextResult.summary.table_preview.sheet_name || "");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "恢复项目默认预览设置失败");
    } finally {
      setIsRefreshingPreviewSettings(false);
    }
  }

  function handleExperienceFileChange(event: ChangeEvent<HTMLInputElement>) {
    selectExperienceFile(event.target.files?.[0] ?? null);
  }

  function selectExperienceFile(nextFile: File | null) {
    setExperienceImportSummary(null);
    setExperienceSheetConfigs([]);
    setActiveExperienceSheetName("");
    setIsExperienceMappingOpen(false);
    if (!nextFile) {
      setExperienceFile(null);
      return;
    }
    if (!nextFile.name.toLowerCase().endsWith(".xlsx")) {
      setExperienceFile(null);
      setError("经验池模块请上传 .xlsx 格式的控制价文件");
      return;
    }
    setError("");
    setExperienceFile(nextFile);
    appendZhisuanMessage(`收到经验池来源文件：${nextFile.name}。我先帮你读取 sheet 和字段，后面只用于预警比选，不会改正式知识库。`);
    void inspectExperienceFile(nextFile);
  }

  function toggleExperienceField(field: string, checked: boolean) {
    setSelectedExperienceFields((current) => {
      const next = checked ? [...current, field] : current.filter((item) => item !== field);
      return next.length > 0 ? next : current;
    });
  }

  async function loadExperienceFieldPreferences(openAfterLoad = false) {
    setIsLoadingExperienceFieldSettings(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/experience-pool/field-preferences`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取经验池字段设置失败：${response.status}`);
      }
      const payload = (await response.json()) as ExperienceFieldPreferencesPayload;
      const defaults = normalizeExperienceFieldPreferences(payload.defaults);
      const preferences = normalizeExperienceFieldPreferences({ ...payload.defaults, ...payload.preferences });
      setExperienceFieldDefaults(defaults);
      setExperienceFieldDraft(preferences);
      setExperienceFieldPreferencesPath(payload.file_path ?? "");
      if (openAfterLoad) {
        setIsExperienceFieldSettingsOpen(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取经验池字段设置失败");
    } finally {
      setIsLoadingExperienceFieldSettings(false);
    }
  }

  function openExperienceFieldSettings() {
    void loadExperienceFieldPreferences(true);
  }

  async function loadExperienceWarningSettings(openAfterLoad = false) {
    setIsLoadingExperienceWarningSettings(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/experience-warnings/settings`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取预警设置失败：${response.status}`);
      }
      const payload = (await response.json()) as ExperienceWarningSettingsPayload;
      const nextSettings = payload.settings ?? payload.defaults ?? DEFAULT_EXPERIENCE_WARNING_SETTINGS;
      setExperienceWarningSettings(nextSettings);
      setExperienceWarningSettingsDraft(nextSettings);
      setExperienceWarningFilterFields(payload.filter_fields?.length ? payload.filter_fields : [...WARNING_FILTER_FIELDS]);
      setExperienceWarningSettingsPath(payload.file_path ?? "");
      if (openAfterLoad) {
        setIsExperienceWarningSettingsOpen(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取预警设置失败");
    } finally {
      setIsLoadingExperienceWarningSettings(false);
    }
  }

  function openExperienceWarningSettings() {
    void loadExperienceWarningSettings(true);
  }

  function updateExperienceWarningSetting(field: "low_risk_warning_ratio" | "high_risk_warning_ratio", value: string) {
    const numericValue = Number(value);
    setExperienceWarningSettingsDraft((current) => ({
      ...current,
      [field]: Number.isFinite(numericValue) ? numericValue : 0,
    }));
  }

  function updateExperienceWarningToggle(value: boolean) {
    setExperienceWarningSettingsDraft((current) => ({
      ...current,
      only_check_rows_with_value: value,
    }));
  }

  function updateExperienceWarningFilterField(value: string) {
    setExperienceWarningSettingsDraft((current) => ({
      ...current,
      value_filter_field: value as WarningFilterField,
    }));
  }

  function resetExperienceWarningSettingsDraft() {
    setExperienceWarningSettingsDraft(experienceWarningSettings);
  }

  async function saveExperienceWarningSettings() {
    const low = Number(experienceWarningSettingsDraft.low_risk_warning_ratio);
    const high = Number(experienceWarningSettingsDraft.high_risk_warning_ratio);
    if (!Number.isFinite(low) || !Number.isFinite(high)) {
      setError("预警比率必须是数字");
      return;
    }
    if (low < 0 || high < 0) {
      setError("低风险预警比率和高风险预警比率都必须大于等于 0");
      return;
    }
    if (high < low) {
      setError("高风险预警比率必须大于等于低风险预警比率");
      return;
    }
    if (experienceWarningSettingsDraft.only_check_rows_with_value && !experienceWarningSettingsDraft.value_filter_field) {
      setError("请选择指定列字段");
      return;
    }
    setIsSavingExperienceWarningSettings(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/experience-warnings/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: experienceWarningSettingsDraft }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `保存预警设置失败：${response.status}`);
      }
      const payload = (await response.json()) as ExperienceWarningSettingsPayload;
      const savedSettings = payload.settings ?? payload.defaults ?? DEFAULT_EXPERIENCE_WARNING_SETTINGS;
      setExperienceWarningSettings(savedSettings);
      setExperienceWarningSettingsDraft(savedSettings);
      setExperienceWarningFilterFields(payload.filter_fields?.length ? payload.filter_fields : [...WARNING_FILTER_FIELDS]);
      setExperienceWarningSettingsPath(payload.file_path ?? "");
      setIsExperienceWarningSettingsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存预警设置失败");
    } finally {
      setIsSavingExperienceWarningSettings(false);
    }
  }

  function updateExperienceFieldDraft(field: ExperienceMappingField, value: string) {
    setExperienceFieldDraft((current) => ({ ...current, [field]: parsePreferenceText(value) }));
  }

  function resetExperienceFieldDraft() {
    setExperienceFieldDraft(experienceFieldDefaults);
  }

  async function saveExperienceFieldPreferences() {
    setIsSavingExperienceFieldSettings(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/experience-pool/field-preferences`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences: experienceFieldDraft }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `保存经验池字段设置失败：${response.status}`);
      }
      const payload = (await response.json()) as ExperienceFieldPreferencesPayload;
      setExperienceFieldDraft(normalizeExperienceFieldPreferences({ ...payload.defaults, ...payload.preferences }));
      setExperienceFieldPreferencesPath(payload.file_path ?? "");
      setIsExperienceFieldSettingsOpen(false);
      if (experienceFile) {
        void inspectExperienceFile(experienceFile);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存经验池字段设置失败");
    } finally {
      setIsSavingExperienceFieldSettings(false);
    }
  }

  async function importExperienceFile() {
    if (!experienceFile) {
      setError("请先选择要导入经验池的控制价 Excel");
      return;
    }
    const enabledConfigs = experienceSheetConfigs.filter((config) => config.enabled);
    const missingFields = enabledConfigs.flatMap((config) => {
      const required = [...REQUIRED_EXPERIENCE_FIELDS, ...selectedExperienceFields] as string[];
      if (onlyImportExperienceRowsWithValue && !required.includes(experienceValueFilterField)) {
        required.push(experienceValueFilterField);
      }
      return required
        .filter((field) => !config.column_mapping[field as ExperienceMappingField])
        .map((field) => `${config.sheet_name}：${field}`);
    });
    if (enabledConfigs.length === 0) {
      setError("请至少选择一个 sheet 导入经验池");
      return;
    }
    if (missingFields.length > 0) {
      setError(`请先完成经验池列选择：${missingFields.join("、")}`);
      setIsExperienceMappingOpen(true);
      return;
    }
    setIsImportingExperience(true);
    setExperienceImportSummary(null);
    setError("");
    const body = new FormData();
    body.append("file", experienceFile);
    body.append("selected_fields", JSON.stringify(selectedExperienceFields));
    body.append("only_import_rows_with_value", String(onlyImportExperienceRowsWithValue));
    body.append("value_filter_field", experienceValueFilterField);
    body.append(
      "sheet_configs",
      JSON.stringify(
        experienceSheetConfigs.map((config) => ({
          sheet_name: config.sheet_name,
          enabled: config.enabled,
          header_row: config.header_row,
          column_mapping: config.column_mapping,
        })),
      ),
    );
    try {
      const response = await fetch(`${API_BASE}/api/experience-pool/import`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `经验池导入失败：${response.status}`);
      }
      const payload = (await response.json()) as { summary: ExperienceImportSummary };
      setExperienceImportSummary(payload.summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "经验池导入失败");
    } finally {
      setIsImportingExperience(false);
    }
  }

  async function inspectExperienceFile(nextFile: File, selectedHeaderRow?: number, selectedSheetName?: string) {
    setIsInspectingExperience(true);
    const body = new FormData();
    body.append("file", nextFile);
    if (selectedHeaderRow) {
      body.append("header_row", String(selectedHeaderRow));
    }
    if (selectedSheetName) {
      body.append("sheet_name", selectedSheetName);
    }
    try {
      const response = await fetch(`${API_BASE}/api/experience-pool/inspect`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取经验池表头失败：${response.status}`);
      }
      const payload = (await response.json()) as ExperienceInspectResult;
      const configs = (payload.sheets ?? []).map((sheet) => ({
        sheet_name: sheet.sheet_name,
        enabled: sheet.enabled,
        header_row: sheet.header_row,
        columns: sheet.columns,
        column_mapping: { ...EMPTY_EXPERIENCE_MAPPING, ...sheet.suggested_mapping },
      }));
      if (selectedSheetName) {
        const nextConfig = configs[0];
        if (nextConfig) {
          setExperienceSheetConfigs((current) =>
            current.map((config) => (config.sheet_name === selectedSheetName ? nextConfig : config)),
          );
        }
        return;
      }
      setExperienceSheetConfigs(configs);
      setActiveExperienceSheetName(configs.find((config) => config.enabled)?.sheet_name ?? configs[0]?.sheet_name ?? "");
      setIsExperienceMappingOpen(configs.length > 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取经验池表头失败");
    } finally {
      setIsInspectingExperience(false);
    }
  }

  async function loadWorkloadFieldPreferences(openAfterLoad = false) {
    setIsLoadingWorkloadFieldSettings(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/workload-capture/field-preferences`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取工作量字段设置失败：${response.status}`);
      }
      const payload = (await response.json()) as WorkloadFieldPreferencesPayload;
      const defaults = normalizeWorkloadFieldPreferences(payload.defaults);
      const preferences = normalizeWorkloadFieldPreferences({ ...payload.defaults, ...payload.preferences });
      setWorkloadFieldDefaults(defaults);
      setWorkloadFieldDraft(preferences);
      setWorkloadAdjacentFallbackEnabled(payload.adjacent_fallback_enabled ?? true);
      setWorkloadElementSequenceEnabled(payload.element_sequence_enabled ?? true);
      setWorkloadFieldPreferencesPath(payload.file_path ?? "");
      if (openAfterLoad) {
        setIsWorkloadFieldSettingsOpen(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取工作量字段设置失败");
    } finally {
      setIsLoadingWorkloadFieldSettings(false);
    }
  }

  async function openWorkloadFieldSettings() {
    await Promise.all([
      loadWorkloadFieldPreferences(false),
      loadWorkloadTargetFieldPreferences(false),
    ]);
    setIsWorkloadFieldSettingsOpen(true);
  }

  function updateWorkloadFieldDraft(field: WorkloadSourceField, value: string) {
    setWorkloadFieldDraft((current) => ({ ...current, [field]: parsePreferenceText(value) }));
  }

  function resetWorkloadFieldDraft() {
    setWorkloadFieldDraft(workloadFieldDefaults);
  }

  async function saveWorkloadFieldPreferences() {
    setIsSavingWorkloadFieldSettings(true);
    setIsSavingWorkloadTargetFieldSettings(true);
    setError("");
    try {
      setIsWorkloadFieldSettingsOpen(false);
      if (workloadFile) {
        void inspectWorkloadFile(workloadFile, "source");
      }
      if (result) {
        void inspectCurrentWorkloadTarget(result.job_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "应用工作量字段设置失败");
    } finally {
      setIsSavingWorkloadFieldSettings(false);
      setIsSavingWorkloadTargetFieldSettings(false);
    }
  }

  async function loadWorkloadTargetFieldPreferences(openAfterLoad = false) {
    setIsLoadingWorkloadTargetFieldSettings(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/workload-capture/target-field-preferences`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取控制价计算表字段设置失败：${response.status}`);
      }
      const payload = (await response.json()) as WorkloadFieldPreferencesPayload;
      const defaults = normalizeWorkloadTargetFieldPreferences(payload.defaults as Partial<Record<WorkloadTargetField, string[]>>);
      const preferences = normalizeWorkloadTargetFieldPreferences({ ...payload.defaults, ...payload.preferences } as Partial<Record<WorkloadTargetField, string[]>>);
      setWorkloadTargetFieldDefaults(defaults);
      setWorkloadTargetFieldDraft(preferences);
      setWorkloadTargetAdjacentFallbackEnabled(payload.adjacent_fallback_enabled ?? true);
      setWorkloadTargetElementSequenceEnabled(payload.element_sequence_enabled ?? false);
      setWorkloadTargetFieldPreferencesPath(payload.file_path ?? "");
      if (openAfterLoad) {
        setIsWorkloadTargetFieldSettingsOpen(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取控制价计算表字段设置失败");
    } finally {
      setIsLoadingWorkloadTargetFieldSettings(false);
    }
  }

  function openWorkloadTargetFieldSettings() {
    void loadWorkloadTargetFieldPreferences(true);
  }

  function updateWorkloadTargetFieldDraft(field: WorkloadTargetField, value: string) {
    setWorkloadTargetFieldDraft((current) => ({ ...current, [field]: parsePreferenceText(value) }));
  }

  function resetWorkloadTargetFieldDraft() {
    setWorkloadTargetFieldDraft(workloadTargetFieldDefaults);
  }

  async function saveWorkloadTargetFieldPreferences() {
    setIsSavingWorkloadTargetFieldSettings(true);
    setError("");
    try {
      setIsWorkloadTargetFieldSettingsOpen(false);
      if (result) {
        void inspectCurrentWorkloadTarget(result.job_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "应用控制价计算表字段设置失败");
    } finally {
      setIsSavingWorkloadTargetFieldSettings(false);
    }
  }

  function handleWorkloadFileChange(event: ChangeEvent<HTMLInputElement>) {
    selectWorkloadFile("source", event.target.files?.[0] ?? null);
  }

  function handleWorkloadTargetFileChange(event: ChangeEvent<HTMLInputElement>) {
    selectWorkloadFile("target", event.target.files?.[0] ?? null);
  }

  function selectWorkloadFile(role: WorkloadRole, nextFile: File | null) {
    setWorkloadCaptureResult(null);
    setWorkloadPreviewCountdown(null);
    setIsWorkloadMappingOpen(false);
    if (role === "source") {
      setWorkloadSourceConfigs([]);
      setActiveWorkloadSourceSheetName("");
    } else {
      setWorkloadTargetConfigs([]);
      setActiveWorkloadTargetSheetName("");
    }
    if (!nextFile) {
      role === "source" ? setWorkloadFile(null) : setWorkloadTargetFile(null);
      return;
    }
    if (!nextFile.name.toLowerCase().endsWith(".xlsx")) {
      setError("工作量抓取模块请上传 .xlsx 文件");
      role === "source" ? setWorkloadFile(null) : setWorkloadTargetFile(null);
      return;
    }
    setError("");
    role === "source" ? setWorkloadFile(nextFile) : setWorkloadTargetFile(nextFile);
    appendZhisuanMessage(
      role === "source"
        ? `收到工作量表：${nextFile.name}。我会帮你盯着要素、单位和数量字段。`
        : `收到控制价计算表：${nextFile.name}。后面抓取工作量时，我只做信息搬运和提示，不改变价格匹配逻辑。`,
    );
    void inspectWorkloadFile(nextFile, role);
    if (role === "source" && result) {
      void inspectCurrentWorkloadTarget(result.job_id);
    }
  }

  function toggleWorkloadField(field: string, checked: boolean) {
    setSelectedWorkloadFields((current) => {
      const next = checked ? [...current, field] : current.filter((item) => item !== field);
      return next.length > 0 ? next : current;
    });
  }

  async function inspectWorkloadFile(
    nextFile: File,
    role: WorkloadRole,
    selectedHeaderRow?: number,
    selectedSheetName?: string,
    fieldPreferencesOverride?: WorkloadFieldPreferences | WorkloadTargetFieldPreferences,
    adjacentFallbackOverride?: boolean,
    elementSequenceOverride?: boolean,
  ) {
    setIsInspectingWorkload(true);
    const body = new FormData();
    body.append("file", nextFile);
    body.append("role", role);
    if (selectedHeaderRow) {
      body.append("header_row", String(selectedHeaderRow));
    }
    if (selectedSheetName) {
      body.append("sheet_name", selectedSheetName);
    }
    body.append("field_preferences", JSON.stringify(fieldPreferencesOverride ?? (role === "source" ? workloadFieldDraft : workloadTargetFieldDraft)));
    body.append(
      "adjacent_fallback_enabled",
      String(adjacentFallbackOverride ?? (role === "source" ? workloadAdjacentFallbackEnabled : workloadTargetAdjacentFallbackEnabled)),
    );
    body.append(
      "element_sequence_enabled",
      String(elementSequenceOverride ?? (role === "source" ? workloadElementSequenceEnabled : workloadTargetElementSequenceEnabled)),
    );
    try {
      const response = await fetch(`${API_BASE}/api/workload-capture/inspect`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取工作量抓取表头失败：${response.status}`);
      }
      const payload = (await response.json()) as WorkloadInspectResult;
      if (role === "source") {
        const configs = (payload.sheets ?? []).map((sheet) => ({
          sheet_name: sheet.sheet_name,
          enabled: sheet.enabled,
          header_row: sheet.header_row,
          columns: sheet.columns,
          column_mapping: { ...EMPTY_WORKLOAD_SOURCE_MAPPING, ...sheet.suggested_mapping },
        }));
        if (selectedSheetName) {
          const nextConfig = configs[0];
          if (nextConfig) {
            setWorkloadSourceConfigs((current) =>
              current.map((config) => (config.sheet_name === selectedSheetName ? nextConfig : config)),
            );
          }
          return;
        }
        setWorkloadSourceConfigs(configs);
        setActiveWorkloadSourceSheetName(configs.find((config) => config.enabled)?.sheet_name ?? configs[0]?.sheet_name ?? "");
      } else {
        const configs = (payload.sheets ?? []).map((sheet) => ({
          sheet_name: sheet.sheet_name,
          enabled: sheet.enabled,
          header_row: sheet.header_row,
          columns: sheet.columns,
          column_mapping: { ...EMPTY_WORKLOAD_TARGET_MAPPING, ...sheet.suggested_mapping },
        }));
        if (selectedSheetName) {
          const nextConfig = configs[0];
          if (nextConfig) {
            setWorkloadTargetConfigs((current) =>
              current.map((config) => (config.sheet_name === selectedSheetName ? nextConfig : config)),
            );
          }
          return;
        }
        setWorkloadTargetConfigs(configs);
        setActiveWorkloadTargetSheetName(configs.find((config) => config.enabled)?.sheet_name ?? configs[0]?.sheet_name ?? "");
      }
      setIsWorkloadMappingOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取工作量抓取表头失败");
    } finally {
      setIsInspectingWorkload(false);
    }
  }

  async function inspectCurrentWorkloadTarget(
    jobId: string,
    selectedHeaderRow?: number,
    selectedSheetName?: string,
    fieldPreferencesOverride?: WorkloadTargetFieldPreferences,
    adjacentFallbackOverride?: boolean,
    elementSequenceOverride?: boolean,
  ) {
    setIsInspectingWorkload(true);
    const body = new FormData();
    body.append("job_id", jobId);
    if (selectedHeaderRow) {
      body.append("header_row", String(selectedHeaderRow));
    }
    if (selectedSheetName) {
      body.append("sheet_name", selectedSheetName);
    }
    body.append("field_preferences", JSON.stringify(fieldPreferencesOverride ?? workloadTargetFieldDraft));
    body.append("adjacent_fallback_enabled", String(adjacentFallbackOverride ?? workloadTargetAdjacentFallbackEnabled));
    body.append("element_sequence_enabled", String(elementSequenceOverride ?? workloadTargetElementSequenceEnabled));
    try {
      const response = await fetch(`${API_BASE}/api/workload-capture/inspect-current-target`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取当前预览控制价表失败：${response.status}`);
      }
      const payload = (await response.json()) as WorkloadInspectResult;
      const configs = (payload.sheets ?? []).map((sheet) => ({
        sheet_name: sheet.sheet_name,
        enabled: sheet.enabled,
        header_row: sheet.header_row,
        columns: sheet.columns,
        column_mapping: { ...EMPTY_WORKLOAD_TARGET_MAPPING, ...sheet.suggested_mapping },
      }));
      if (selectedSheetName) {
        const nextConfig = configs[0];
        if (nextConfig) {
          setWorkloadTargetConfigs((current) =>
            current.map((config) => (config.sheet_name === selectedSheetName ? nextConfig : config)),
          );
        }
        return configs;
      }
      setWorkloadTargetConfigs(configs);
      setActiveWorkloadTargetSheetName(configs.find((config) => config.enabled)?.sheet_name ?? configs[0]?.sheet_name ?? "");
      if (configs.length > 0) {
        setIsWorkloadMappingOpen(true);
      }
      return configs;
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取当前预览控制价表失败");
      return [];
    } finally {
      setIsInspectingWorkload(false);
    }
  }

  async function runWorkloadCapture() {
    if (!workloadFile || !result) {
      setError("请先完成控制价计算表转换并选择工作量表格");
      return;
    }
    const requestJobId = result.job_id;
    let targetConfigsForRun = workloadTargetConfigs;
    if (targetConfigsForRun.length === 0) {
      targetConfigsForRun = await inspectCurrentWorkloadTarget(requestJobId) ?? [];
      if (!isCurrentResultJob(requestJobId)) return;
    }
    const sourceEnabled = workloadSourceConfigs.filter((config) => config.enabled);
    const targetEnabled = targetConfigsForRun.filter((config) => config.enabled);
    const selectedFieldsForRun = effectiveWorkloadSelectedFields(sourceEnabled, targetEnabled);
    if (sourceEnabled.length === 0 || targetEnabled.length === 0) {
      setError("请至少选择一个工作量 sheet，并确认当前预览控制价表已识别到可写入 sheet");
      setIsWorkloadMappingOpen(true);
      return;
    }
    if (selectedFieldsForRun.length === 0) {
      setError("请至少选择一个实际要抓取并写入的字段");
      setIsWorkloadMappingOpen(true);
      return;
    }
    const missingSource = sourceEnabled.flatMap((config) => {
      const required: string[] = [...REQUIRED_WORKLOAD_KEY_FIELDS];
      if (selectedFieldsForRun.includes("数量(信息抓取)") && !required.includes("数量")) {
        required.push("数量");
      }
      if (onlyCaptureWorkloadRowsWithValue && !required.includes(workloadValueFilterField)) {
        required.push(workloadValueFilterField);
      }
      return required
        .filter((field) => !config.column_mapping[field as WorkloadSourceField])
        .map((field) => `${config.sheet_name}：${workloadFieldLabel(field)}`);
    });
    const missingTarget = targetEnabled.flatMap((config) =>
      REQUIRED_WORKLOAD_KEY_FIELDS
        .filter((field) => !config.column_mapping[field as WorkloadTargetField])
        .map((field) => `${config.sheet_name}：${workloadFieldLabel(field)}`),
    );
    if (missingSource.length > 0 || missingTarget.length > 0) {
      setError(`请先完成工作量抓取列选择：${[...missingSource, ...missingTarget].join("、")}`);
      setIsWorkloadMappingOpen(true);
      return;
    }

    setIsRunningWorkloadCapture(true);
    setWorkloadProgressPercent(6);
    setWorkloadProgressText("正在读取工作量表和当前预览控制价表...");
    setWorkloadCaptureResult(null);
    setWorkloadPreviewCountdown(null);
    setError("");
    setIsAiDockCollapsed(false);
    appendZhisuanMessage(
      `开始工作量抓取：先读取工作量表和当前预览控制价表，再按要素1-5、单位和术语归并规则匹配，最后按${workloadWriteMode === "conservative" ? "保守模式" : "覆盖模式"}写入${selectedFieldsForRun.map(workloadFieldLabel).join("、")}。`,
      "system",
    );
    const body = new FormData();
    body.append("workload_file", workloadFile);
    body.append("job_id", requestJobId);
    body.append("selected_fields", JSON.stringify(selectedFieldsForRun));
    body.append("only_capture_rows_with_value", String(onlyCaptureWorkloadRowsWithValue));
    body.append("value_filter_field", workloadValueFilterField);
    body.append("write_mode", workloadWriteMode);
    body.append(
      "source_sheet_configs",
      JSON.stringify(
        workloadSourceConfigs.map((config) => ({
          sheet_name: config.sheet_name,
          enabled: config.enabled,
          header_row: config.header_row,
          column_mapping: config.column_mapping,
        })),
      ),
    );
    body.append(
      "target_sheet_configs",
      JSON.stringify(
        targetConfigsForRun.map((config) => ({
          sheet_name: config.sheet_name,
          enabled: config.enabled,
          header_row: config.header_row,
          column_mapping: config.column_mapping,
        })),
      ),
    );
    try {
      const response = await fetch(`${API_BASE}/api/workload-capture/apply-to-current`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `工作量抓取失败：${response.status}`);
      }
      const payload = (await response.json()) as WorkloadApplyToCurrentResult;
      if (!setResultForCurrentJob(requestJobId, payload)) return;
      setWorkloadProgressPercent(100);
      setWorkloadProgressText("抓取完成，已刷新表格预览。");
      setActivePreviewSheetName(payload.summary.table_preview?.sheet_name ?? "");
      setWorkloadCaptureResult({
        job_id: payload.job_id,
        summary: payload.workload_summary,
        downloads: payload.workload_downloads,
      });
      setPreviewManualEditMessage(
        `工作量抓取已写入当前预览：填写 ${payload.workload_summary.filled_rows} 行，覆盖 ${payload.workload_summary.overwritten_rows ?? 0} 行，保守跳过 ${payload.workload_summary.skipped_existing_rows ?? 0} 行。`,
      );
      appendZhisuanMessage(
        `工作量抓取完成：写入 ${payload.workload_summary.filled_rows} 行，覆盖 ${payload.workload_summary.overwritten_rows ?? 0} 行，保守跳过 ${payload.workload_summary.skipped_existing_rows ?? 0} 行，预警 ${payload.workload_summary.warning_rows} 行。5 秒后我会自动跳到表格预览；你点击任意位置可以取消自动跳转。`,
        "command",
      );
      markReportPreviewUpdated(requestJobId, "工作量抓取已写入并更新 Word 报告，正在刷新真实预览…");
      setWorkloadPreviewCountdown(5);
    } catch (err) {
      if (!isCurrentResultJob(requestJobId)) return;
      appendZhisuanMessage(
        `工作量抓取失败：${err instanceof Error ? err.message : "未知错误"}。我没有继续自动跳转，请检查列映射或源表数据后重试。`,
        "system",
      );
      setError(err instanceof Error ? err.message : "工作量抓取失败");
    } finally {
      setIsRunningWorkloadCapture(false);
    }
  }

  async function selectFile(nextFile: File | null) {
    processRequestSequenceRef.current += 1;
    activeResultJobIdRef.current = null;
    setIsProcessing(false);
    setIsDemoLoading(false);
    setError("");
    setResult(null);
    setActivePreviewSheetName("");
    setWorkloadPreviewCountdown(null);
    setEditingPreviewCell(null);
    setSavingPreviewCellKey("");
    setPreviewManualEditMessage("");
    setRiskReport("");
    setRiskSummary(null);
    setIsDemoMode(false);
    setFillAssistDialog(null);
    setRowAiContext(null);
    setRowAiAnswer("");
    setShowAllWarnings(false);
    setWarningProgress(EMPTY_WARNING_PROGRESS);
    appendZhisuanMessage("开始转换。我会按读取输入、结构化匹配、公式重算、生成报告与预览这几步盯着。");
    setColumns([]);
    setSheetConfigs([]);
    setActiveSheetName("");
    setHeaderRow(1);
    setColumnMapping(EMPTY_MAPPING);
    setIsMappingOpen(false);
    setMergeVerticalCells(true);
    setMergeHorizontalCells(true);
    if (!nextFile) {
      setFile(null);
      return;
    }
    if (!nextFile.name.toLowerCase().endsWith(".xlsx")) {
      setFile(null);
      setError("请上传 .xlsx 格式的 Excel 文件");
      return;
    }
    setFile(nextFile);
    appendZhisuanMessage(`收到 ${nextFile.name}，准备复核表头和列映射。你可以先看左侧字段识别，我会在右边跟着提示下一步。`);
    await inspectFile(nextFile);
  }

  async function inspectFile(
    nextFile: File,
    selectedHeaderRow?: number,
    selectedSheetName?: string,
    fieldPreferencesOverride?: InputFieldPreferences,
  ) {
    setIsInspecting(true);
    const body = new FormData();
    body.append("file", nextFile);
    if (selectedHeaderRow) {
      body.append("header_row", String(selectedHeaderRow));
    }
    if (selectedSheetName) {
      body.append("sheet_name", selectedSheetName);
    }
    body.append("field_preferences", JSON.stringify(fieldPreferencesOverride ?? inputFieldDraft));
    try {
      const response = await fetch(`${API_BASE}/api/inspect`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取表头失败：${response.status}`);
      }
      const payload = (await response.json()) as InspectResult;
      if (selectedSheetName) {
        setSheetConfigs((configs) =>
          configs.map((config) =>
            config.sheet_name === selectedSheetName
              ? {
                  ...config,
                  header_row: payload.header_row,
                  columns: payload.columns,
                  column_mapping: { ...EMPTY_MAPPING, ...payload.suggested_mapping },
                }
              : config,
          ),
        );
        return;
      }
      setColumns(payload.columns);
      setHeaderRow(payload.header_row);
      setColumnMapping({ ...EMPTY_MAPPING, ...payload.suggested_mapping });
      const configs = (payload.sheets ?? []).map((sheet) => ({
        sheet_name: sheet.sheet_name,
        enabled: sheet.enabled,
        header_row: sheet.header_row,
        columns: sheet.columns,
        column_mapping: { ...EMPTY_MAPPING, ...sheet.suggested_mapping },
      }));
      setSheetConfigs(configs);
      setActiveSheetName(configs[0]?.sheet_name ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取表头失败");
    } finally {
      setIsInspecting(false);
    }
  }

  function handleDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setIsDragging(true);
  }

  function handleDragLeave(event: DragEvent<HTMLLabelElement>) {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    setIsDragging(false);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(false);
    selectFile(event.dataTransfer.files?.[0] ?? null);
  }

  function handleExperienceDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setIsExperienceDragging(true);
  }

  function handleExperienceDragLeave(event: DragEvent<HTMLDivElement>) {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    setIsExperienceDragging(false);
  }

  function handleExperienceDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsExperienceDragging(false);
    selectExperienceFile(event.dataTransfer.files?.[0] ?? null);
  }

  function handleWorkloadDragOver(event: DragEvent<HTMLDivElement>, role: WorkloadRole) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setWorkloadDraggingRole(role);
  }

  function handleWorkloadDragLeave(event: DragEvent<HTMLDivElement>, role: WorkloadRole) {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    setWorkloadDraggingRole((current) => (current === role ? null : current));
  }

  function handleWorkloadDrop(event: DragEvent<HTMLDivElement>, role: WorkloadRole) {
    event.preventDefault();
    setWorkloadDraggingRole(null);
    selectWorkloadFile(role, event.dataTransfer.files?.[0] ?? null);
  }

  async function processFile() {
    if (!file) {
      setError("请选择 .xlsx 文件");
      return;
    }
    const configsToValidate = sheetConfigs.length > 0 ? sheetConfigs.filter((config) => config.enabled) : [];
    const missingFields = sheetConfigs.length > 0
      ? configsToValidate.flatMap((config) =>
          REQUIRED_MAPPING_FIELDS
            .filter((field) => !config.column_mapping[field])
            .map((field) => `${config.sheet_name}：${field}`),
        )
      : REQUIRED_MAPPING_FIELDS.filter((field) => !columnMapping[field]);
    if (missingFields.length > 0) {
      setError(`请先选择列映射：${missingFields.join("、")}`);
      return;
    }

    const requestId = ++processRequestSequenceRef.current;
    activeResultJobIdRef.current = null;
    setIsProcessing(true);
    setProgressPercent(1);
    setError("");
    setResult(null);
    setActivePreviewSheetName("");
    setEditingPreviewCell(null);
    setSavingPreviewCellKey("");
    setPreviewManualEditMessage("");
    setRiskSummary(null);
    setFillAssistDialog(null);
    setRowAiContext(null);
    setRowAiAnswer("");
    setShowAllWarnings(false);
    setWarningProgress(EMPTY_WARNING_PROGRESS);

    const body = new FormData();
    body.append("file", file);
    if (sheetConfigs.length > 0) {
      body.append(
        "sheet_configs",
        JSON.stringify(
          sheetConfigs.map((config) => ({
            sheet_name: config.sheet_name,
            enabled: config.enabled,
            header_row: config.header_row,
            column_mapping: config.column_mapping,
            output_match_report: outputMatchReport,
            merge_vertical_cells: mergeVerticalCells,
            merge_horizontal_cells: mergeHorizontalCells,
            only_match_rows_with_value: onlyMatchRowsWithValue,
            match_value_filter_field: matchValueFilterField,
          })),
        ),
      );
    } else {
      body.append("column_mapping", JSON.stringify(columnMapping));
      body.append("header_row", String(headerRow));
    }
    body.append("output_match_report", String(outputMatchReport));
    body.append("merge_vertical_cells", String(mergeVerticalCells));
    body.append("merge_horizontal_cells", String(mergeHorizontalCells));
    body.append("only_match_rows_with_value", String(onlyMatchRowsWithValue));
    body.append("match_value_filter_field", matchValueFilterField);
    body.append("defer_matching", "true");
    void sendCollaborationNotification("task_started", {
      task_name: file.name,
      stage: "读取输入并生成待匹配预览",
    });

    try {
      appendZhisuanMessage("我先读取表格、列映射和候选 sheet，生成待匹配预览；价格和两个系数先不批量写入。", "system");
      const response = await fetch(`${API_BASE}/api/process`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `处理失败：${response.status}`);
      }
      const payload = (await response.json()) as ProcessResult;
      let finalPayload = payload;
      const payloadPreviewSheets = previewSheetsFromTablePreview(payload.summary.table_preview);
      if (hasPreviewHeaderRowOverrides(payloadPreviewSheets, previewColumnPreferences)) {
        try {
          finalPayload = await refreshPreviewWithPreferences(payload, previewColumnPreferences);
        } catch (refreshError) {
          setError(refreshError instanceof Error ? refreshError.message : "自动刷新预览失败，请在预览设置中点一次保存");
        }
      }
      if (requestId !== processRequestSequenceRef.current) return;
      activeResultJobIdRef.current = finalPayload.job_id;
      setResult(finalPayload);
      setProgressPercent(100);
      appendZhisuanMessage(summarizeResultForZhisuan(finalPayload));
      void sendCollaborationNotification("progress", {
        task_name: file.name,
        job_id: finalPayload.job_id,
        stage: "待匹配预览已生成",
      });
    } catch (err) {
      if (requestId !== processRequestSequenceRef.current) return;
      const messageText = err instanceof Error ? err.message : "处理失败";
      setError(messageText);
      setProgressPercent(0);
      appendZhisuanMessage(`转换失败：${messageText}。主流程已经停下，我没有改动任何输出文件。`);
      void sendCollaborationNotification("task_failed", {
        task_name: file.name,
        error: messageText,
      });
    } finally {
      if (requestId === processRequestSequenceRef.current) {
        setIsProcessing(false);
      }
    }
  }

  async function runBatchMatch() {
    if (!result || result.summary.matching_status !== "pending" || isBatchMatching) return;
    const requestJobId = result.job_id;
    setIsBatchMatching(true);
    setError("");
    setPreviewManualEditMessage("");
    appendZhisuanMessage("开始批量匹配。我会按结构化计价库、标准规则和第二层经验提示依次填写基价 / 单价、实物工作费调整系数和技术工作费调整系数。", "system");
    void sendCollaborationNotification("task_started", {
      task_name: file?.name ?? "当前造价任务",
      job_id: requestJobId,
      stage: "批量匹配",
    });
    try {
      const response = await fetch(`${API_BASE}/api/process/batch-match`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: requestJobId,
          header_rows: buildPreviewHeaderRows(previewColumnPreferences),
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `批量匹配失败：${response.status}`);
      }
      const payload = (await response.json()) as ProcessResult;
      if (!setResultForCurrentJob(requestJobId, payload)) return;
      setActivePreviewSheetName((current) => current || previewSheetLabel(previewSheetsFromTablePreview(payload.summary.table_preview)[0] ?? activePreview, 0));
      markReportPreviewUpdated(requestJobId, "批量匹配已完成并生成 Word 报告，正在加载真实预览…");
      appendZhisuanMessage(summarizeResultForZhisuan(payload), "command");
      void sendCollaborationNotification("task_completed", {
        task_name: file?.name ?? "当前造价任务",
        job_id: payload.job_id,
        summary: {
          total_data_rows: payload.summary.total_data_rows,
          matched_rows: payload.summary.matched_rows,
          review_rows: payload.summary.review_rows,
          warning_rows: payload.summary.warning_summary?.warning_rows ?? 0,
        },
      });
    } catch (err) {
      if (!isCurrentResultJob(requestJobId)) return;
      const messageText = err instanceof Error ? err.message : "批量匹配失败";
      setError(messageText);
      appendZhisuanMessage(`批量匹配失败：${messageText}。我没有继续生成新的匹配结果，请检查列映射或输入表后重试。`, "system");
      void sendCollaborationNotification("task_failed", {
        task_name: file?.name ?? "当前造价任务",
        job_id: requestJobId,
        error: messageText,
      });
    } finally {
      setIsBatchMatching(false);
    }
  }

  async function loadDemoSample() {
    const requestId = ++processRequestSequenceRef.current;
    setIsDemoLoading(true);
    setError("");
    setRiskReport("");
    setRiskSummary(null);
    setFillAssistDialog(null);
    setWarningProgress(EMPTY_WARNING_PROGRESS);
    appendZhisuanMessage("正在加载演示样例，并按正式转换链路生成结果。", "system");
    try {
      const response = await fetch(`${API_BASE}/api/demo/load-sample`, { method: "POST" });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `加载演示样例失败：${response.status}`);
      }
      const payload = (await response.json()) as ProcessResult & { demo_mode?: boolean; sample_file?: string };
      let finalPayload: ProcessResult = payload;
      const payloadPreviewSheets = previewSheetsFromTablePreview(payload.summary.table_preview);
      if (hasPreviewHeaderRowOverrides(payloadPreviewSheets, previewColumnPreferences)) {
        finalPayload = await refreshPreviewWithPreferences(payload, previewColumnPreferences);
      }
      if (requestId !== processRequestSequenceRef.current) return;
      activeResultJobIdRef.current = finalPayload.job_id;
      setResult(finalPayload);
      setIsDemoMode(true);
      setActiveDaweibaModule("preview");
      appendZhisuanMessage(`演示样例已加载：${payload.sample_file ?? "预置样例"}。可以继续运行经验池预警、查看风险清单、下载 Excel/Word。`, "command");
    } catch (err) {
      if (requestId !== processRequestSequenceRef.current) return;
      const messageText = err instanceof Error ? err.message : "加载演示样例失败";
      setError(messageText);
      appendZhisuanMessage(`演示样例加载失败：${messageText}`, "system");
    } finally {
      if (requestId === processRequestSequenceRef.current) {
        setIsDemoLoading(false);
      }
    }
  }

  async function loadRiskSummary() {
    if (!result) {
      setError("请先完成转换");
      return;
    }
    if (result.summary.matching_status === "pending") {
      setError("请先点击预览窗口的“批量匹配”");
      appendZhisuanMessage("当前只是待匹配预览，还没有正式填写价格和两个系数。请先点“批量匹配”，完成后我再生成风险清单。", "command");
      return;
    }
    setIsRiskSummaryLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/risk/summary?job_id=${encodeURIComponent(result.job_id)}`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取风险清单失败：${response.status}`);
      }
      const payload = (await response.json()) as RiskSummaryPayload;
      setRiskSummary(payload);
      appendZhisuanMessage(`结构化风险清单已生成：共 ${payload.summary.total} 项。`, "command");
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取风险清单失败");
    } finally {
      setIsRiskSummaryLoading(false);
    }
  }

  async function loadExperienceGovernance() {
    setIsExperienceGovernanceLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/quality/experience-pool`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `生成经验池治理报告失败：${response.status}`);
      }
      const payload = (await response.json()) as GovernanceReport;
      setExperienceGovernance(payload);
      appendZhisuanMessage(`经验池治理报告已生成：发现 ${payload.summary.issue_count} 项问题线索。`, "command");
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成经验池治理报告失败");
    } finally {
      setIsExperienceGovernanceLoading(false);
    }
  }

  async function openFillAssist(row: Array<string | number | null>, sourceIndex: number, sheetOverride?: TablePreview) {
    if (!result || !activePreview) return;
    const sourceSheet = sheetOverride ?? activePreview;
    const sourceColumns = sheetOverride
      ? buildPreviewColumns(sourceSheet, result.summary.price_column, previewColumnPreferences)
      : previewColumns;
    const targetColumn = findFillAssistTargetColumn(sourceColumns, result.summary.price_column);
    if (!targetColumn) {
      setError("当前预览未找到基价 / 单价列，无法打开辅助填价");
      return;
    }
    const sheetIndex = Math.max(0, previewSheets.findIndex((sheet) => sheet.sheet_name === sourceSheet.sheet_name));
    const sheetName = previewSheetLabel(sourceSheet, sheetIndex);
    const rowNumber = previewExcelRowNumber(sourceSheet, sourceIndex, sheetConfigs);
    setFillAssistDialog({
      context: {
        sheet_name: sheetName,
        excel_row: rowNumber,
        target_header: targetColumn.label,
        target_column: targetColumn.index + 1,
        current_value: row[targetColumn.index] ?? "",
        row: {},
        diagnostics: {},
      },
      candidates: [],
      trace: [],
      selectedCandidateId: "",
      note: "",
      isLoading: true,
      isConfirming: false,
      error: "",
    });
    try {
      const response = await fetch(`${API_BASE}/api/fill-assist/candidates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: result.job_id,
          sheet_name: sheetName,
          row_number: rowNumber,
          target_header: targetColumn.label,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `读取辅助填价候选失败：${response.status}`);
      }
      const payload = (await response.json()) as FillAssistPayload;
      setFillAssistDialog({
        ...payload,
        trace: payload.trace ?? [],
        selectedCandidateId: payload.candidates[0]?.id ?? "",
        note: "",
        isLoading: false,
        isConfirming: false,
        error: "",
      });
    } catch (err) {
      setFillAssistDialog((current) => current ? {
        ...current,
        isLoading: false,
        error: err instanceof Error ? err.message : "读取辅助填价候选失败",
      } : current);
    }
  }

  async function confirmFillAssist() {
    if (!result || !fillAssistDialog) return;
    const requestJobId = result.job_id;
    const candidate = fillAssistDialog.candidates.find((item) => item.id === fillAssistDialog.selectedCandidateId);
    if (!candidate) {
      setFillAssistDialog((current) => current ? { ...current, error: "请选择一个候选" } : current);
      return;
    }
    setFillAssistDialog((current) => current ? { ...current, isConfirming: true, error: "" } : current);
    try {
      const response = await fetch(`${API_BASE}/api/fill-assist/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: requestJobId,
          sheet_name: fillAssistDialog.context.sheet_name,
          row_number: fillAssistDialog.context.excel_row,
          column_number: fillAssistDialog.context.target_column,
          candidate,
          note: fillAssistDialog.note,
          header_rows: buildPreviewHeaderRows(previewColumnPreferences),
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `辅助填价确认失败：${response.status}`);
      }
      const payload = (await response.json()) as PreviewCellUpdateResult;
      if (!setResultForCurrentJob(requestJobId, payload)) return;
      setPreviewManualEditMessage(`已通过辅助填价写入：${payload.manual_edit.column_letter}${payload.manual_edit.row_number}；如影响汇总，请点“重算公式”。`);
      setFillAssistDialog(null);
      appendZhisuanMessage(`已采用辅助填价候选：${candidate.source_label}，写入 ${candidate.value}。`, "command");
    } catch (err) {
      if (!isCurrentResultJob(requestJobId)) return;
      setFillAssistDialog((current) => current ? {
        ...current,
        isConfirming: false,
        error: err instanceof Error ? err.message : "辅助填价确认失败",
      } : current);
    }
  }

  async function runExperienceWarnings(fromZhisuan = false) {
    if (!result) {
      setError("请先完成 Excel 转换");
      if (fromZhisuan) {
        appendZhisuanMessage("我还没有可分析的转换结果。先完成 Excel 转换，我再接着跑经验池预警。", "command");
      }
      return;
    }
    if (result.summary.matching_status === "pending") {
      setError("请先点击预览窗口的“批量匹配”");
      appendZhisuanMessage("经验池预警需要基于已填写的价格和系数运行。当前还在待匹配预览阶段，请先点击“批量匹配”。", fromZhisuan ? "command" : "system");
      return;
    }
    const requestJobId = result.job_id;
    setIsRunningWarnings(true);
    setWarningProgress({ ...EMPTY_WARNING_PROGRESS, status: "running" });
    setError("");
    const body = new FormData();
    body.append("job_id", requestJobId);
    body.append("preview_header_rows", JSON.stringify(buildPreviewHeaderRows(previewColumnPreferences)));
    const pollProgress = async () => {
      const response = await fetch(`${API_BASE}/api/experience-warnings/progress/${requestJobId}`);
      if (!response.ok) {
        return;
      }
      const payload = (await response.json()) as WarningProgress;
      if (!isCurrentResultJob(requestJobId)) return;
      setWarningProgress({
        ...EMPTY_WARNING_PROGRESS,
        ...payload,
      });
    };
    let warningProgressTimer: number | null = null;
    try {
      await pollProgress();
      warningProgressTimer = window.setInterval(() => {
        void pollProgress();
      }, 400);
      const response = await fetch(`${API_BASE}/api/experience-warnings/run`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `经验池预警分析失败：${response.status}`);
      }
      const payload = (await response.json()) as ProcessResult;
      if (!setResultForCurrentJob(requestJobId, payload)) return;
      setShowAllWarnings(false);
      setActivePreviewSheetName((current) => current || payload.summary.table_preview.sheet_name || "");
      const finalSummary = payload.summary.warning_summary;
      setWarningProgress({
        status: "completed",
        processed_rows: finalSummary?.candidate_rows ?? 0,
        total_rows: finalSummary?.candidate_rows ?? 0,
        matched_rows: finalSummary?.checked_rows ?? 0,
        warning_rows: finalSummary?.warning_rows ?? 0,
      });
      appendZhisuanMessage(
        [
          `经验池预警分析完成：候选 ${finalSummary?.candidate_rows ?? 0} 行，已核查 ${finalSummary?.checked_rows ?? 0} 行，预警 ${finalSummary?.warning_rows ?? 0} 行。`,
          describeTopWarnings(payload.summary.warning_details ?? []),
        ].join("\n\n"),
        fromZhisuan ? "command" : "system",
      );
      markReportPreviewUpdated(requestJobId, "经验池预警结果已写入 Word 报告，正在刷新真实预览…");
    } catch (err) {
      if (!isCurrentResultJob(requestJobId)) return;
      const messageText = err instanceof Error ? err.message : "经验池预警分析失败";
      setWarningProgress((current) => ({
        ...current,
        status: "failed",
        error: messageText,
      }));
      setError(messageText);
      appendZhisuanMessage(`智算辅助暂不可用：${messageText}。主流程和已有转换结果不受影响。`, fromZhisuan ? "command" : "system");
    } finally {
      if (warningProgressTimer !== null) {
        window.clearInterval(warningProgressTimer);
      }
      setIsRunningWarnings(false);
    }
  }

  async function generateRiskReport(fromZhisuan = false) {
    if (!result) {
      setError("请先完成 Excel 转换");
      if (fromZhisuan) {
        appendZhisuanMessage("风险报告需要先有转换结果。先完成填价转换，我再帮你输出。", "command");
      }
      return;
    }
    if (result.summary.matching_status === "pending") {
      setError("请先点击预览窗口的“批量匹配”");
      appendZhisuanMessage("风险报告需要正式匹配结果。当前只是待匹配预览，请先点“批量匹配”，完成填价后我再输出报告。", fromZhisuan ? "command" : "system");
      return;
    }
    const requestJobId = result.job_id;
    setIsGeneratingRisk(true);
    setError("");
    const body = new FormData();
    body.append("job_id", requestJobId);
    body.append("provider", llmSettings.provider);
    body.append("model", llmSettings.model);
    body.append("base_url", llmSettings.baseUrl);
    const thinking = appendZhisuanMessage("正在汇总本次匹配结果和费用信息...", "thinking", { typing: false });
    const thinkingTimer = window.setTimeout(() => {
      replaceZhisuanMessage(thinking, "正在检索本地知识库依据，补充报告说明...", "thinking", { typing: false });
    }, 1800);
    const longWaitTimer = window.setTimeout(() => {
      replaceZhisuanMessage(thinking, "大模型正在生成风险报告，可能还需要几秒。左侧结果不受影响。", "thinking", { typing: false });
    }, 5200);
    try {
      const response = await fetch(`${API_BASE}/api/risk-report`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `风险报告生成失败：${response.status}`);
      }
      const payload = (await response.json()) as { risk_report: string; debug?: LlmDebugInfo };
      if (!isCurrentResultJob(requestJobId)) return;
      setRiskReport(payload.risk_report);
      markReportPreviewUpdated(requestJobId, "风险报告已写入 Word，正在刷新真实预览…");
      recordLlmDebug("风险报告", payload.debug);
      replaceZhisuanMessage(thinking, `风险报告已生成，也会照常写入 Word 报告。\n\n${payload.risk_report}`, "model");
      appendZhisuanMessage(
        `风险内容已经整合进 Word 报告。点击下方按钮可以跳转到“Word 报告”页查看，也可以直接下载。\n${ZHISUAN_WORD_REPORT_ACTION}`,
        "command",
        { typing: false },
      );
    } catch (err) {
      if (!isCurrentResultJob(requestJobId)) return;
      const messageText = err instanceof Error ? err.message : "风险报告生成失败";
      setError(messageText);
      replaceZhisuanMessage(thinking, `智算辅助暂不可用：${messageText}。转换、Excel 下载和 Word 基础报告仍照常可用。`, fromZhisuan ? "command" : "model");
    } finally {
      window.clearTimeout(thinkingTimer);
      window.clearTimeout(longWaitTimer);
      setIsGeneratingRisk(false);
    }
  }

  async function askZhisuanFreeform(message: string) {
    setIsChatting(true);
    setError("");
    const body = new FormData();
    body.append("message", message);
    body.append("provider", llmSettings.provider);
    body.append("model", llmSettings.model);
    body.append("base_url", llmSettings.baseUrl);
    const thinking = appendZhisuanMessage("正在发送问题给大模型...", "thinking", { typing: false });
    const longWaitTimer = window.setTimeout(() => {
      replaceZhisuanMessage(thinking, "大模型正在组织回答，可能还需要几秒。主流程可以继续操作。", "thinking", { typing: false });
    }, 4200);

    try {
      const response = await fetch(`${API_BASE}/api/llm-chat`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `大模型问答失败：${response.status}`);
      }
      const payload = (await response.json()) as { answer: string; debug?: LlmDebugInfo };
      replaceZhisuanMessage(thinking, payload.answer, "model");
      recordLlmDebug("问答测试", payload.debug);
    } catch (err) {
      const messageText = err instanceof Error ? err.message : "大模型问答失败";
      setError(messageText);
      replaceZhisuanMessage(thinking, `智算辅助暂不可用：${messageText}`, "model");
    } finally {
      window.clearTimeout(longWaitTimer);
      setIsChatting(false);
    }
  }

  async function askKnowledgeQuestion(
    question: string,
    rowContext: ReturnType<typeof knowledgeRowContext> = null,
    sourceLabel = "知识库问答",
    options: { forcedKnowledge?: boolean; rowDetailContext?: RowAiContext } = {},
  ) {
    setIsChatting(true);
    setError("");
    const thinking = appendZhisuanMessage(
      options.forcedKnowledge ? "已进入知识库模式，正在检索本地规则和知识库..." : "正在检索本地规则和知识库...",
      "thinking",
      { typing: false },
    );
    const evidenceTimer = window.setTimeout(() => {
      replaceZhisuanMessage(
        thinking,
        options.forcedKnowledge ? "已调用知识库，正在整理依据来源和当前行上下文..." : "正在整理依据来源和当前行上下文...",
        "thinking",
        { typing: false },
      );
    }, 1500);
    const modelTimer = window.setTimeout(() => {
      replaceZhisuanMessage(thinking, "已找到相关依据，正在让智算组织回答...", "thinking", { typing: false });
    }, 3600);
    try {
      const response = await fetch(`${API_BASE}/api/knowledge/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          context_type: rowContext ? "row" : "general",
          row_context: rowContext,
          provider: llmSettings.provider,
          model: llmSettings.model,
          base_url: llmSettings.baseUrl,
          limit: 8,
          force_knowledge: Boolean(options.forcedKnowledge),
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `知识库问答失败：${response.status}`);
      }
      const payload = (await response.json()) as KnowledgeAskResponse;
      const answer = formatKnowledgeAnswer(payload, { forcedKnowledge: options.forcedKnowledge });
      replaceZhisuanMessage(thinking, answer, payload.evidence_found ? "model" : "command", {
        rowDetailContext: options.rowDetailContext,
      });
      recordLlmDebug(sourceLabel, payload.debug ?? undefined);
      return answer;
    } catch (err) {
      const messageText = err instanceof Error ? err.message : "知识库问答失败";
      setError(messageText);
      replaceZhisuanMessage(thinking, `智算辅助暂不可用：${messageText}`, "model", {
        rowDetailContext: options.rowDetailContext,
      });
      return `智算辅助暂不可用：${messageText}`;
    } finally {
      window.clearTimeout(evidenceTimer);
      window.clearTimeout(modelTimer);
      setIsChatting(false);
    }
  }

  async function sendChatMessage() {
    const message = chatInput.trim();
    if (!message) {
      setError("请输入要发送给大模型的问题");
      return;
    }

    setError("");
    setChatInput("");
    appendUserCommand(message);

    const forcedKnowledge = parseForceKnowledgePrompt(message);
    if (forcedKnowledge.forced) {
      if (!forcedKnowledge.question) {
        setError("请输入查库问题");
        appendZhisuanMessage("请输入知识库问题，例如：@知识库：第二层经验提示是什么意思？", "command");
        return;
      }
      await askKnowledgeQuestion(forcedKnowledge.question, knowledgeRowContext(rowAiContext), "强制知识库问答", { forcedKnowledge: true });
      return;
    }

    const command = detectZhisuanCommand(message);
    if (command) {
      await handleZhisuanCommand(command);
      return;
    }

    if (isKnowledgeQuestion(message)) {
      await askKnowledgeQuestion(message, knowledgeRowContext(rowAiContext));
      return;
    }

    await askZhisuanFreeform(message);
  }

  async function askRowAi(context: RowAiContext | null = rowAiContext, question = rowAiQuestion) {
    if (!context) return;
    const cleanQuestion = question.trim();
    if (!cleanQuestion) {
      setError("请输入要询问这行的问题");
      return;
    }
    setIsRowAiLoading(true);
    setError("");
    setRowAiQuestion(cleanQuestion);
    setRowAiAnswer("");

    try {
      const answer = await askKnowledgeQuestion(cleanQuestion, knowledgeRowContext(context), "行级知识库复核", {
        rowDetailContext: context,
      });
      setRowAiAnswer(answer);
      setRowAiDetailPrompt(context);
    } catch (err) {
      const messageText = err instanceof Error ? err.message : "行级 AI 分析失败";
      setError(messageText);
      setRowAiAnswer(`智算辅助暂不可用：${messageText}`);
      appendZhisuanMessage(`智算辅助暂不可用：${messageText}`, "model");
    } finally {
      setIsRowAiLoading(false);
    }
  }

  function openRowAi(row: Array<string | number | null>, rowIndex: number) {
    const values: Record<string, string> = Object.fromEntries(
      previewColumns
        .filter((column) => column.index >= 0)
        .map((column) => [column.label, previewHeaderText(row[column.index])]),
    );
    const hasValueForAlias = (aliases: readonly string[]) => {
      const normalizedAliases = aliases.map((alias) => compactHeader(alias));
      return Object.keys(values).some((label) => {
        const normalizedLabel = compactHeader(label);
        return normalizedAliases.some((alias) => normalizedLabel.includes(alias));
      });
    };
    const findHeaderIndex = (aliases: readonly string[]) => {
      const normalizedAliases = aliases.map((alias) => compactHeader(alias));
      return activePreview.headers.findIndex((header) => {
        const normalizedHeader = compactHeader(header);
        return normalizedAliases.some((alias) => normalizedHeader.includes(alias));
      });
    };
    ROW_AI_CONTEXT_FIELD_GROUPS.forEach((field) => {
      if (hasValueForAlias(field.aliases)) return;
      const index = findHeaderIndex(field.aliases);
      if (index < 0) return;
      const text = previewHeaderText(row[index]);
      if (text) {
        values[field.label] = text;
      }
    });
    const context = {
      sheetName: previewSheetLabel(activePreview, 0),
      rowNumber: previewExcelRowNumber(activePreview, rowIndex, sheetConfigs),
      values,
      previewRow: row,
      sourceIndex: rowIndex,
    };
    const question = "解释这行要素含义，并判断当前基价和两个系数是否合理。";
    setRowAiContext(context);
    setRowAiAnswer("");
    setRowAiQuestion(question);
    setChatInput(question);
    setIsChatOpen(true);
    setIsAiDockCollapsed(false);
    window.setTimeout(() => chatInputRef.current?.focus(), 0);
  }

  function openRowAiDetail(context: RowAiContext | null = rowAiDetailPrompt) {
    if (!context) return;
    const matchedSheet = previewSheets.find(
      (sheet) => normalizePreviewSheetName(sheet.sheet_name) === normalizePreviewSheetName(context.sheetName),
    );
    setActiveDaweibaModule("preview");
    if (matchedSheet) {
      setActivePreviewSheetName(matchedSheet.sheet_name || context.sheetName);
    }
    setRowAiDetailPrompt(null);
    void openFillAssist(context.previewRow, context.sourceIndex, matchedSheet);
  }

  function jumpToWarningPreview(warning: WarningDetail) {
    const matchedSheet = previewSheets.find(
      (sheet) => normalizePreviewSheetName(sheet.sheet_name) === normalizePreviewSheetName(warning.sheet_name),
    );
    const sheetName = matchedSheet?.sheet_name ?? warning.sheet_name;
    const target = {
      sheetName,
      excelRow: warning.excel_row,
      metric: warning.metric,
    };
    setActiveDaweibaModule("preview");
    setActivePreviewSheetName(sheetName);
    setPendingPreviewJump(target);
    setFocusedPreviewJump(target);
  }

  useEffect(() => {
    return () => {
      if (previewFocusTimeoutRef.current !== null) {
        window.clearTimeout(previewFocusTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!pendingPreviewJump) return;
    if (normalizePreviewSheetName(activePreview.sheet_name) !== normalizePreviewSheetName(pendingPreviewJump.sheetName)) {
      return;
    }
    const targetExcelRow = pendingPreviewJump.excelRow;
    const matchedRow = visiblePreviewRows.find(
      ({ sourceIndex }) => previewExcelRowNumber(activePreview, sourceIndex, sheetConfigs) === targetExcelRow,
    );
    if (!matchedRow) {
      setPendingPreviewJump(null);
      setError(`已切换到 ${pendingPreviewJump.sheetName}，但第 ${targetExcelRow} 行不在当前填价结果预览范围内。`);
      if (previewFocusTimeoutRef.current !== null) {
        window.clearTimeout(previewFocusTimeoutRef.current);
      }
      previewFocusTimeoutRef.current = window.setTimeout(() => setFocusedPreviewJump(null), 2200);
      return;
    }
    const scrollContainer = previewScrollRef.current;
    const rowElement = Array.from(
      scrollContainer?.querySelectorAll<HTMLTableRowElement>("tbody tr[data-preview-row]") ?? [],
    ).find(
      (element) => (
        element.dataset.previewSheet === normalizePreviewSheetName(pendingPreviewJump.sheetName)
        && Number(element.dataset.previewRow) === targetExcelRow
      ),
    );
    if (rowElement) {
      rowElement.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
      const cellElement = Array.from(rowElement.querySelectorAll<HTMLTableCellElement>("td[data-preview-column]")).find(
        (element) => Number(element.dataset.previewColumn) === focusedPreviewColumnIndex,
      );
      cellElement?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    }
    setPendingPreviewJump(null);
    if (previewFocusTimeoutRef.current !== null) {
      window.clearTimeout(previewFocusTimeoutRef.current);
    }
    previewFocusTimeoutRef.current = window.setTimeout(() => setFocusedPreviewJump(null), 2200);
  }, [activePreview, focusedPreviewColumnIndex, pendingPreviewJump, sheetConfigs, visiblePreviewRows]);

  function recordLlmDebug(source: string, debug?: LlmDebugInfo) {
    if (!debug) return;
    setLlmDebugHistory((current) => [
      { ...debug, source, createdAt: new Date().toLocaleString() },
      ...current,
    ].slice(0, 10));
  }

  function applyLlmPreset(presetId: string) {
    const preset = LLM_PRESETS.find((item) => item.id === presetId);
    if (!preset) return;
    setLlmSettings({
      provider: preset.provider,
      model: preset.model,
      baseUrl: preset.baseUrl,
    });
  }

  function updateActiveMapping(field: MappingField, value: string) {
    if (sheetConfigs.length > 0) {
      setSheetConfigs((configs) =>
        configs.map((config) =>
          config.sheet_name === activeSheetName
            ? {
                ...config,
                column_mapping: {
                  ...config.column_mapping,
                  [field]: value,
                },
              }
            : config,
        ),
      );
      return;
    }
    setColumnMapping((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function updateActiveHeaderRow(value: number) {
    if (sheetConfigs.length > 0) {
      setSheetConfigs((configs) =>
        configs.map((config) =>
          config.sheet_name === activeSheetName ? { ...config, header_row: value } : config,
        ),
      );
      return;
    }
    setHeaderRow(value);
  }

  function toggleActiveSheet(enabled: boolean) {
    setSheetConfigs((configs) =>
      configs.map((config) =>
        config.sheet_name === activeSheetName ? { ...config, enabled } : config,
      ),
    );
  }

  function updateActiveExperienceMapping(field: ExperienceMappingField, value: string) {
    setExperienceSheetConfigs((configs) =>
      configs.map((config) =>
        config.sheet_name === activeExperienceSheetName
          ? {
              ...config,
              column_mapping: {
                ...config.column_mapping,
                [field]: value,
              },
            }
          : config,
      ),
    );
  }

  function updateActiveExperienceHeaderRow(value: number) {
    setExperienceSheetConfigs((configs) =>
      configs.map((config) =>
        config.sheet_name === activeExperienceSheetName ? { ...config, header_row: value } : config,
      ),
    );
  }

  function toggleActiveExperienceSheet(enabled: boolean) {
    setExperienceSheetConfigs((configs) =>
      configs.map((config) =>
        config.sheet_name === activeExperienceSheetName ? { ...config, enabled } : config,
      ),
    );
  }

  function updateActiveWorkloadMapping(role: WorkloadRole, field: string, value: string) {
    if (role === "source") {
      setWorkloadSourceConfigs((configs) =>
        configs.map((config) =>
          config.sheet_name === activeWorkloadSourceSheetName
            ? {
                ...config,
                column_mapping: {
                  ...config.column_mapping,
                  [field]: value,
                },
              }
            : config,
        ),
      );
      return;
    }
    setWorkloadTargetConfigs((configs) =>
      configs.map((config) =>
        config.sheet_name === activeWorkloadTargetSheetName
          ? {
              ...config,
              column_mapping: {
                ...config.column_mapping,
                [field]: value,
              },
            }
          : config,
      ),
    );
  }

  function updateActiveWorkloadHeaderRow(role: WorkloadRole, value: number) {
    if (role === "source") {
      setWorkloadSourceConfigs((configs) =>
        configs.map((config) =>
          config.sheet_name === activeWorkloadSourceSheetName ? { ...config, header_row: value } : config,
        ),
      );
      return;
    }
    setWorkloadTargetConfigs((configs) =>
      configs.map((config) =>
        config.sheet_name === activeWorkloadTargetSheetName ? { ...config, header_row: value } : config,
      ),
    );
  }

  function toggleActiveWorkloadSheet(role: WorkloadRole, enabled: boolean) {
    if (role === "source") {
      setWorkloadSourceConfigs((configs) =>
        configs.map((config) =>
          config.sheet_name === activeWorkloadSourceSheetName ? { ...config, enabled } : config,
        ),
      );
      return;
    }
    setWorkloadTargetConfigs((configs) =>
      configs.map((config) =>
        config.sheet_name === activeWorkloadTargetSheetName ? { ...config, enabled } : config,
      ),
    );
  }

  function fieldLabel(field: MappingField) {
    return field === "输出-价格列" ? "输出-价格列" : field;
  }

  function isMappingMissing(field: MappingField) {
    const shouldWarn =
      field === "单位" ||
      field === "输出-价格列" ||
      (ELEMENT_FIELDS as readonly string[]).includes(field);
    return shouldWarn && !activeMapping()[field];
  }

  function isExperienceMappingMissing(field: ExperienceMappingField) {
    const required = [...REQUIRED_EXPERIENCE_FIELDS, ...selectedExperienceFields] as string[];
    return required.includes(field) && !activeExperienceMapping()[field];
  }

  function effectiveWorkloadSelectedFields(
    sourceConfigs: WorkloadSheetMappingConfig<WorkloadSourceMapping>[] = workloadSourceConfigs,
    targetConfigs: WorkloadSheetMappingConfig<WorkloadTargetMapping>[] = workloadTargetConfigs,
  ) {
    return selectedWorkloadFields.filter((field) => {
      if (field === "数量(信息抓取)") return true;
      if (!(WORKLOAD_OPTIONAL_TARGET_FIELDS as readonly string[]).includes(field)) return true;
      const sourceField = WORKLOAD_TARGET_TO_SOURCE_FIELD[field];
      const hasSourceMapping = sourceConfigs.some(
        (config) => config.enabled && Boolean(config.column_mapping[sourceField as WorkloadSourceField]),
      );
      const hasTargetMapping = targetConfigs.some(
        (config) => config.enabled && Boolean(config.column_mapping[field as WorkloadTargetField]),
      );
      return hasSourceMapping && hasTargetMapping;
    });
  }

  function isWorkloadMappingMissing(role: WorkloadRole, field: string) {
    if (role === "source") {
      const sourceMapping = activeWorkloadSourceMapping();
      if (Object.values(WORKLOAD_TARGET_TO_SOURCE_FIELD).includes(field)) {
        if (field === "数量") {
          return selectedWorkloadFields.includes("数量(信息抓取)") && !sourceMapping[field as WorkloadSourceField];
        }
        return false;
      }
      const required: string[] = [
        ...REQUIRED_WORKLOAD_KEY_FIELDS,
      ];
      return required.includes(field) && !sourceMapping[field as WorkloadSourceField];
    }
    return (REQUIRED_WORKLOAD_KEY_FIELDS as readonly string[]).includes(field) && !activeWorkloadTargetMapping()[field as WorkloadTargetField];
  }

  function previewText(value: string | number | null | undefined) {
    if (value === null || value === undefined) return "";
    const text = String(value);
    return text.length > 10 ? text.slice(0, 10) : text;
  }

  function previewCellText(value: string | number | null | undefined) {
    if (value === null || value === undefined) return "";
    if (typeof value === "number" && Number.isFinite(value)) {
      const rounded = Math.round(value * 100) / 100;
      if (Number.isInteger(rounded)) return String(rounded);
      return rounded.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
    }
    return String(value);
  }

  function warningCellValues(columns: PreviewColumn[], row: Array<string | number | null>) {
    const parameterColumn = columns.find((column) => column.label === "预警参数" || column.label === "预警信息");
    const detailColumn = columns.find((column) => column.label === "预警细节");
    return {
      parameter: parameterColumn ? previewCellText(row[parameterColumn.index]) : "",
      detail: detailColumn ? previewCellText(row[detailColumn.index]) : "",
    };
  }

  function warningCellState(columns: PreviewColumn[], row: Array<string | number | null>) {
    const { parameter, detail } = warningCellValues(columns, row);
    if (!parameter && !detail) return "empty";
    if (parameter.trim() === "无预警") return "ok";
    if (detail.includes("高风险预警") || detail.startsWith("高风险")) return "high";
    return "low";
  }

  function previewDisplayText(column: PreviewColumn, value: string | number | null | undefined) {
    void column;
    return previewCellText(value);
  }

  function previewHeaderText(value: string | number | null | undefined) {
    return String(value ?? "").trim();
  }

  function compactPreviewHeader(value: string | number | null | undefined) {
    return previewHeaderText(value).replace(/\s+/g, "");
  }

  function previewSheetLabel(sheet: TablePreview, sheetIndex: number) {
    const name = String(sheet.sheet_name ?? "").trim();
    return name || `Sheet ${sheetIndex + 1}`;
  }

  function isMatchedNumberCell(column: PreviewColumn, row: Array<string | number | null>) {
    if (column.kind !== "number" || column.index < 0) return false;
    const text = previewHeaderText(row[column.index]);
    return Boolean(text) && text !== "待复核" && text !== "空单价";
  }

  function previewCellClass(column: PreviewColumn, row: Array<string | number | null>, columns: PreviewColumn[]) {
    if (column.kind === "warning") {
      const state = warningCellState(columns, row);
      if (state === "high") return "preview-warning-high-cell";
      if (state === "low") return "preview-warning-low-cell";
      if (state === "ok") return "preview-warning-ok-cell";
    }
    if (isMatchedNumberCell(column, row)) return "preview-number-ok";
    return undefined;
  }

  function previewCellTitle(column: PreviewColumn, row: Array<string | number | null>, columns: PreviewColumn[]) {
    if (column.kind !== "warning") return previewCellText(row[column.index]);
    const { parameter, detail } = warningCellValues(columns, row);
    if (parameter && detail) return `预警参数：${parameter}\n预警细节：${detail}`;
    return parameter || detail;
  }

  function isEditablePreviewColumn(column: PreviewColumn) {
    if (column.index < 0) return false;
    if (column.kind === "warning" || column.kind === "status" || column.kind === "note") return false;
    const compact = compactPreviewHeader(column.label);
    return !["匹配状态", "候选数量", "匹配说明", "预警参数", "预警细节"].some(
      (label) => compact === compactPreviewHeader(label),
    );
  }

  function isEditingPreviewCell(sourceIndex: number, column: PreviewColumn) {
    return Boolean(
      editingPreviewCell
      && editingPreviewCell.sourceIndex === sourceIndex
      && editingPreviewCell.columnIndex === column.index
      && normalizePreviewSheetName(editingPreviewCell.sheetName) === normalizePreviewSheetName(activePreview.sheet_name),
    );
  }

  function renderPreviewCellContent(column: PreviewColumn, row: Array<string | number | null>, columns: PreviewColumn[]) {
    const text = previewDisplayText(column, row[column.index]);
    if (column.kind !== "warning" || !text) return text;
    const state = warningCellState(columns, row);
    if (state === "high" || state === "low") {
      return (
        <span className={`preview-warning-inline ${state === "high" ? "is-high" : "is-low"}`}>
          <AlertTriangle size={14} />
          <span>{text}</span>
        </span>
      );
    }
    if (state === "ok") {
      return (
        <span className="preview-warning-inline is-ok">
          <CheckCircle2 size={14} />
          <span>{text}</span>
        </span>
      );
    }
    return text;
  }

  function renderZhisuanInlineText(text: string) {
    const pattern = /(实际偏离率[：:\s]*[-+]?\d+(?:\.\d+)?%|第\s*\d+\s*行|(?:预警\s*)?\d+\s*行|高风险|低风险|无预警|待复核|建议复核|依据来源|智算解释|经验池预警分析|输出风险报告|输出excel表格|输出word报告|生成\s*AI\s*审查摘要)/g;
    const nodes: ReactNode[] = [];
    let lastIndex = 0;
    for (const match of text.matchAll(pattern)) {
      const matchedText = match[0];
      const index = match.index ?? 0;
      if (index > lastIndex) {
        nodes.push(text.slice(lastIndex, index));
      }
      nodes.push(
        <span className="zhisuan-text-highlight" key={`${matchedText}-${index}`}>
          {matchedText}
        </span>,
      );
      lastIndex = index + matchedText.length;
    }
    if (lastIndex < text.length) {
      nodes.push(text.slice(lastIndex));
    }
    return nodes.length > 0 ? nodes : text;
  }

  function renderZhisuanRichInlineText(text: string) {
    const segments = text.split(/(\*\*[^*]+\*\*)/g);
    return segments.map((segment, index) => {
      if (segment.startsWith("**") && segment.endsWith("**") && segment.length > 4) {
        return (
          <strong key={`strong-${index}`}>
            {renderZhisuanInlineText(segment.slice(2, -2))}
          </strong>
        );
      }
      return <span key={`text-${index}`}>{renderZhisuanInlineText(segment)}</span>;
    });
  }

  function zhisuanLineTone(text: string) {
    if (/高风险|严重|异常|超过|偏离率/.test(text)) return "is-high";
    return "";
  }

  function findWarningDetailFromZhisuanLine(text: string, severity?: "high" | "low") {
    const normalizedText = normalizePreviewSheetName(text);
    return warningDetails.find((warning) => {
      if (severity && warning.severity !== severity) return false;
      const rowText = `第${warning.excel_row}行`;
      return (
        normalizedText.includes(normalizePreviewSheetName(warning.sheet_name))
        && normalizedText.includes(normalizePreviewSheetName(rowText))
        && normalizedText.includes(normalizePreviewSheetName(warning.metric))
      );
    });
  }

  function renderZhisuanWarningJump(warning: WarningDetail, label = "跳到表格") {
    return (
      <button
        className="zhisuan-warning-jump"
        key={`warning-jump-${warning.sheet_name}-${warning.excel_row}-${warning.metric}`}
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          jumpToWarningPreview(warning);
        }}
      >
        <FileSpreadsheet size={13} />
        {label}
      </button>
    );
  }

  function openPreviewFromZhisuanGuide() {
    setActiveDaweibaModule("preview");
    if (!result) return;
    const resultKey = result.summary.output_excel || result.job_id || "preview";
    if (previewGuideResultKeyRef.current === resultKey) return;
    previewGuideResultKeyRef.current = resultKey;
    const rowsText = visiblePreviewRows.length > 0 ? `当前窗口先展示 ${visiblePreviewRows.length} 行预览数据` : "当前窗口会展示转换后的表格预览";
    appendZhisuanMessage(
      [
        "这里是表格预览页。",
        `${rowsText}，可以切换 Sheet、查看匹配状态、调整列宽、人工修改普通单元格，也可以在 AI 列打开辅助填价或行级复核。`,
        result.summary.matching_status === "pending"
          ? "当前还没有正式批量填写价格和两个系数。点击下方“批量匹配”后，我会按知识库、标准规则和第二层经验提示开始填价。"
          : "当前已经完成批量匹配，可以继续运行经验池预警、查看风险清单或输出报告。",
        ZHISUAN_BATCH_MATCH_ACTION,
      ].join("\n"),
      "command",
    );
  }

  function renderZhisuanBatchMatchAction() {
    const isPending = result?.summary.matching_status === "pending";
    return (
      <div className="zhisuan-action-row" key="batch-match-actions">
        <button
          className="zhisuan-action-button"
          type="button"
          disabled={!isPending || isBatchMatching}
          onClick={(event) => {
            event.stopPropagation();
            void handleZhisuanCommand("batch-match");
          }}
        >
          {isBatchMatching ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />}
          {isPending ? "批量匹配" : "已完成匹配"}
        </button>
      </div>
    );
  }

  function renderZhisuanPreviewAction() {
    return (
      <div className="zhisuan-action-row" key="preview-actions">
        <button
          className="zhisuan-action-button"
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            openPreviewFromZhisuanGuide();
          }}
        >
          <FileSpreadsheet size={14} />
          跳转到表格预览
        </button>
      </div>
    );
  }

  function renderZhisuanWordReportActions() {
    return (
      <div className="zhisuan-action-row" key="word-report-actions">
        <button
          className="zhisuan-action-button"
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            setActiveDaweibaModule("report");
          }}
        >
          <FileText size={14} />
          去 Word 报告
        </button>
        <button
          className="zhisuan-action-button secondary"
          type="button"
          disabled={!reportDownloadHref}
          onClick={(event) => {
            event.stopPropagation();
            if (reportDownloadHref) {
              openDownload(reportDownloadHref, "Word 报告");
            }
          }}
        >
          <Download size={14} />
          下载 Word
        </button>
      </div>
    );
  }

  function renderZhisuanMessageText(text: string) {
    const lines = text.replace(/\r/g, "").split("\n");
    const nodes: ReactNode[] = [];
    let paragraph: string[] = [];
    let bullets: string[] = [];

    const flushParagraph = () => {
      if (!paragraph.length) return;
      const content = paragraph.join("\n").trim();
      if (content) {
        nodes.push(
          <p className={`zhisuan-message-paragraph ${zhisuanLineTone(content)}`} key={`p-${nodes.length}`}>
            {renderZhisuanRichInlineText(content)}
          </p>,
        );
      }
      paragraph = [];
    };
    const flushBullets = () => {
      if (!bullets.length) return;
      nodes.push(
        <ul className="zhisuan-message-list" key={`ul-${nodes.length}`}>
          {bullets.map((item, index) => (
            <li className={zhisuanLineTone(item)} key={`${item}-${index}`}>
              {renderZhisuanRichInlineText(item)}
            </li>
          ))}
        </ul>,
      );
      bullets = [];
    };

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) {
        flushParagraph();
        flushBullets();
        continue;
      }
      if (line === ZHISUAN_WORD_REPORT_ACTION) {
        flushParagraph();
        flushBullets();
        nodes.push(renderZhisuanWordReportActions());
        continue;
      }
      if (line === ZHISUAN_PREVIEW_ACTION) {
        flushParagraph();
        flushBullets();
        nodes.push(renderZhisuanPreviewAction());
        continue;
      }
      if (line === ZHISUAN_BATCH_MATCH_ACTION) {
        flushParagraph();
        flushBullets();
        nodes.push(renderZhisuanBatchMatchAction());
        continue;
      }
      const bulletMatch = line.match(/^(?:[-*•]|\d+[.、]|[一二三四五六七八九十]+[.、])\s*(.+)$/);
      if (bulletMatch) {
        flushParagraph();
        bullets.push(bulletMatch[1].trim());
        continue;
      }
      const headingMatch = line.match(/^#{1,4}\s*(.+)$/) || line.match(/^([一二三四五六七八九十]+[、.].{2,32})$/);
      const colonHeading = /^[^：:]{2,18}[：:]$/.test(line);
      if (headingMatch || colonHeading) {
        flushParagraph();
        flushBullets();
        const headingText = (headingMatch?.[1] ?? line).replace(/[：:]$/, "");
        nodes.push(
          <div className="zhisuan-message-heading" key={`h-${nodes.length}`}>
            {renderZhisuanRichInlineText(headingText)}
          </div>,
        );
        continue;
      }
      const severity = /高风险/.test(line) ? "high" : /低风险/.test(line) ? "low" : undefined;
      const warning = findWarningDetailFromZhisuanLine(line, severity);
      if (warning) {
        flushParagraph();
        flushBullets();
        nodes.push(
          <p className={`zhisuan-message-paragraph zhisuan-warning-line ${zhisuanLineTone(line)}`} key={`warning-${nodes.length}`}>
            <span>{renderZhisuanRichInlineText(line)}</span>
            {renderZhisuanWarningJump(warning)}
          </p>,
        );
        continue;
      }
      paragraph.push(line);
    }
    flushParagraph();
    flushBullets();

    return nodes.length > 0 ? nodes : renderZhisuanRichInlineText(text);
  }

  function renderWorkloadMappingPanel(role: WorkloadRole) {
    const configs = role === "source" ? workloadSourceConfigs : workloadTargetConfigs;
    const activeConfig = role === "source" ? activeWorkloadSourceConfig() : activeWorkloadTargetConfig();
    const fields = role === "source" ? WORKLOAD_SOURCE_FIELDS : WORKLOAD_TARGET_FIELDS;
    const activeMapping = role === "source" ? activeWorkloadSourceMapping() : activeWorkloadTargetMapping();
    const mappedCount = role === "source" ? mappedWorkloadSourceFieldCount : mappedWorkloadTargetFieldCount;
    const title = role === "source" ? "工作量表格列选择" : "当前预览控制价表列选择";
    const currentFile = role === "source" ? workloadFile : workloadTargetFile;
    const hasTargetWorkbook = role === "target" ? Boolean(result) : Boolean(currentFile);
    const activeName = role === "source" ? activeWorkloadSourceSheetName : activeWorkloadTargetSheetName;
    const setActiveName = role === "source" ? setActiveWorkloadSourceSheetName : setActiveWorkloadTargetSheetName;

    if (!hasTargetWorkbook) return null;
    return (
      <div
        className="mapping-subpanel"
        data-ui-key={role === "source" ? "workload-source-mapping-panel" : "workload-target-mapping-panel"}
        style={uiStyle(role === "source" ? "workload-source-mapping-panel" : "workload-target-mapping-panel")}
      >
        <div className="mapping-subhead">
          <strong>{title}</strong>
          <span>
            {isInspectingWorkload
              ? "正在读取表头"
              : configs.length > 0
                ? `当前 ${activeConfig?.sheet_name ?? ""}，已映射 ${mappedCount}/${fields.length} 项`
                : role === "source" ? "选择文件后自动读取 sheet 和表头" : "生成表格预览后自动读取 sheet 和表头"}
          </span>
        </div>
        {configs.length > 0 && (
          <div className="sheet-tabs" data-ui-key="sheet-tabs" style={uiStyle("sheet-tabs")} role="tablist" aria-label={title}>
            {configs.map((config) => (
              <button
                className={config.sheet_name === activeName ? "is-active" : ""}
                key={`${role}-${config.sheet_name}`}
                type="button"
                onClick={() => setActiveName(config.sheet_name)}
              >
                <span className={config.enabled ? "sheet-tab-status is-enabled" : "sheet-tab-status is-skipped"}>
                  {config.enabled ? "录入" : "跳过"}
                </span>
                <span className="sheet-tab-divider"> · </span>
                <span>{config.sheet_name}</span>
              </button>
            ))}
          </div>
        )}
        {activeConfig && (
          <>
            <label className="mapping-check-field" data-ui-key="check-field" style={uiStyle("check-field")}>
              <input
                checked={activeConfig.enabled}
                type="checkbox"
                onChange={(event) => toggleActiveWorkloadSheet(role, event.target.checked)}
              />
              <span>{role === "source" ? "从该 sheet 抓取工作量" : "向该 sheet 写入抓取结果"}</span>
            </label>
            <label className="mapping-row-field" data-ui-key="mapping-row-field" style={uiStyle("mapping-row-field")}>
              <span>映射行</span>
              <span className="mapping-row-control">
                <input
                  min={1}
                  max={999}
                  type="number"
                  value={activeConfig.header_row}
                  disabled={isInspectingWorkload}
                  onChange={(event) => updateActiveWorkloadHeaderRow(role, Math.max(1, Number(event.target.value) || 1))}
                />
                <button
                  type="button"
                  disabled={isInspectingWorkload}
                  onClick={() => {
                    if (role === "source" && currentFile) {
                      void inspectWorkloadFile(currentFile, role, activeConfig.header_row, activeConfig.sheet_name);
                      return;
                    }
                    if (role === "target" && result) {
                      void inspectCurrentWorkloadTarget(result.job_id, activeConfig.header_row, activeConfig.sheet_name);
                    }
                  }}
                >
                  读取该行
                </button>
              </span>
            </label>
            <div className="mapping-grid experience-mapping-grid">
              {fields.map((field) => {
                const missing = isWorkloadMappingMissing(role, field);
                return (
                  <label className={`mapping-field ${missing ? "is-missing" : ""}`} data-ui-key="mapping-field" style={uiStyle("mapping-field")} key={`${role}-${field}`}>
                    <span>
                      {workloadFieldLabel(field)}
                      {missing && <small>必选</small>}
                    </span>
                    <select
                      value={activeMapping[field as keyof typeof activeMapping] ?? ""}
                      disabled={isInspectingWorkload || activeWorkloadColumns(role).length === 0}
                      onChange={(event) => updateActiveWorkloadMapping(role, field, event.target.value)}
                    >
                      <option value="">
                        {role === "target" && field === "数量(信息抓取)"
                          ? "自动新增列"
                          : "不使用"}
                      </option>
                      {activeWorkloadColumns(role).map((column) => (
                        <option key={`${role}-${field}-${column.letter}`} value={column.letter}>
                          {column.label}
                        </option>
                      ))}
                    </select>
                  </label>
                );
              })}
            </div>
          </>
        )}
      </div>
    );
  }

  function enterAppFromWelcome() {
    if (hideWelcomeNextTime) {
      window.localStorage.setItem(WELCOME_SCREEN_HIDDEN_STORAGE_KEY, "1");
      window.localStorage.setItem(WELCOME_SCREEN_VERSION_STORAGE_KEY, WELCOME_SCREEN_VERSION);
    }
    setIsWelcomeScreenVisible(false);
  }

  function showWelcomeScreen() {
    window.localStorage.removeItem(WELCOME_SCREEN_HIDDEN_STORAGE_KEY);
    window.localStorage.removeItem(WELCOME_SCREEN_VERSION_STORAGE_KEY);
    setHideWelcomeNextTime(false);
    setIsWelcomeScreenVisible(true);
  }

  function openDaweibaKnowledge() {
    setActiveDaweibaModule("knowledge");
    setIsAiDockCollapsed(false);
    setIsChatOpen(true);
    setChatInput((current) => current || "@知识库：");
    window.requestAnimationFrame(() => chatInputRef.current?.focus());
  }

  const daweibaInputRows = result ? result.summary.total_data_rows : "--";
  const daweibaPreviewRows = result ? visiblePreviewRows.length : "--";
  const daweibaReviewCount = result ? result.summary.review_rows : "--";
  const daweibaWarningCount = warningSummary?.executed ? warningSummary.warning_rows : "未运行";
  const daweibaTotalRows = Math.max(1, result?.summary.total_data_rows ?? 0);
  const daweibaReviewRows = result?.summary.review_rows ?? 0;
  const daweibaWarningRows = warningSummary?.executed ? Number(warningSummary.warning_rows ?? 0) : 0;
  const daweibaMatchedRows = result?.summary.matched_rows ?? 0;
  const daweibaStableRows = Math.max(0, daweibaMatchedRows - daweibaReviewRows - daweibaWarningRows);
  const daweibaStablePercent = result
    ? Math.min(100, Math.round((daweibaStableRows / daweibaTotalRows) * 1000) / 10)
    : Math.min(100, Math.round(displayCompletion));
  const daweibaReviewEndPercent = result
    ? Math.min(100, daweibaStablePercent + Math.round((daweibaReviewRows / daweibaTotalRows) * 1000) / 10)
    : daweibaStablePercent;
  const daweibaWarningEndPercent = result
    ? Math.min(100, daweibaReviewEndPercent + Math.round((daweibaWarningRows / daweibaTotalRows) * 1000) / 10)
    : daweibaReviewEndPercent;
  const daweibaChartTotal = result ? Math.max(1, result.summary.total_data_rows) : 1;
  const daweibaChartMatchedRows = result ? Math.max(0, daweibaStableRows) : 0;
  const daweibaChartReviewRows = result ? daweibaReviewRows : 0;
  const daweibaChartWarningRows = result ? daweibaWarningRows : 0;
  const daweibaChartUsedRows = daweibaChartMatchedRows + daweibaChartReviewRows + daweibaChartWarningRows;
  const daweibaChartRestRows = result ? Math.max(0, daweibaChartTotal - daweibaChartUsedRows) : 1;
  let daweibaChartOffset = 0;
  const daweibaStatusSegments = [
    { id: "matched", label: "匹配", value: daweibaChartMatchedRows, color: "rgb(117, 188, 146)" },
    { id: "review", label: "复核", value: daweibaChartReviewRows, color: "#d9972f" },
    { id: "warning", label: "预警", value: daweibaChartWarningRows, color: "#d84b4b" },
    { id: "rest", label: "未展示", value: daweibaChartRestRows, color: "#e6e6e3" },
  ]
    .filter((segment) => segment.value > 0)
    .map((segment) => {
      const percent = (segment.value / daweibaChartTotal) * 100;
      const offset = daweibaChartOffset;
      daweibaChartOffset += percent;
      return { ...segment, percent, offset };
    });
  const daweibaStatusCallouts = [
    {
      id: "matched",
      className: "is-left-top",
      label: "匹配",
      value: daweibaChartMatchedRows,
      color: "rgb(117, 188, 146)",
    },
    {
      id: "review",
      className: "is-right",
      label: "复核",
      value: daweibaChartReviewRows,
      color: "#d9972f",
    },
    {
      id: "warning",
      className: "is-left-bottom",
      label: "预警",
      value: daweibaChartWarningRows,
      color: "#d84b4b",
    },
  ].map((item) => ({
    ...item,
    percent: result ? Math.round((item.value / daweibaChartTotal) * 100) : 0,
  }));
  const daweibaStatusRows = [
    { label: "输入行", value: daweibaInputRows },
    { label: "可视化", value: daweibaPreviewRows },
    { label: "待复核", value: daweibaReviewCount },
    { label: "预警", value: daweibaWarningCount },
  ];
  const uploadRowSummary = result ? `${result.summary.total_data_rows} 行` : "待转换";
  const experienceInfoRows = result
    ? result.summary.matched_rows + result.summary.physical_experience_rows + result.summary.technical_experience_rows
    : 0;
  const experienceInfoDetail = result
    ? `价格 ${result.summary.matched_rows} · 实物 ${result.summary.physical_experience_rows} · 技术 ${result.summary.technical_experience_rows}`
    : "转换后显示经验信息数";
  const workbenchStatusCards = [
    {
      label: "预警概览",
      value: warningSummary?.executed ? `${warningSummary.warning_rows} 条` : "未运行",
      detail: warningSummary?.executed
        ? `高风险 ${warningSummary.high_rows} · 低风险 ${warningSummary.low_rows ?? warningSummary.medium_rows ?? 0}`
        : "运行经验池预警后显示",
    },
    {
      label: "风险报告",
      value: riskReport ? "已生成" : warningSummary?.executed ? "可生成" : "待预警",
      detail: riskReport ? "已整合进 Word 报告" : "预警分析完成后生成",
    },
    {
      label: "经验池",
      value: experienceImportSummary
        ? `${experienceImportSummary.imported_rows} 条经验`
        : result
          ? `${experienceInfoRows} 条经验`
          : "待转换",
      detail: experienceImportSummary
        ? `跳过 ${experienceImportSummary.skipped_rows} 行`
        : experienceInfoDetail,
    },
    {
      label: "知识库",
      value: `${KNOWLEDGE_QA_ENTRY_COUNT} 条知识`,
      detail: `${KNOWLEDGE_QA_SOURCE_COUNT} 个来源 · 结构化计价库 ${PRICE_KNOWLEDGE_ROW_COUNT} 条`,
    },
  ];
  const daweibaModules = [
    {
      id: "fill",
      name: "填价工作台",
      detail: file ? "已选择 Excel" : "上传与列映射",
      icon: <Upload size={16} />,
    },
    {
      id: "preview",
      name: "结果预览",
      detail: result ? `${visiblePreviewRows.length} 行可视化` : "转换后查看",
      icon: <FileSpreadsheet size={16} />,
    },
    {
      id: "experience",
      name: "经验池预警",
      detail: warningSummary?.executed ? `${warningSummary.warning_rows} 条预警` : "手动运行",
      icon: <AlertTriangle size={16} />,
    },
    {
      id: "workload",
      name: "工作量抓取",
      detail: workloadCaptureResult ? "已有抓取结果" : "独立预处理",
      icon: <Columns3 size={16} />,
    },
    {
      id: "report",
      name: "Word 报告",
      detail: hasCurrentReport ? "可预览与下载" : isBatchMatchPending ? "等待批量匹配" : "等待转换",
      icon: <FileText size={16} />,
    },
    {
      id: "knowledge",
      name: "知识库问答",
      detail: FORCE_KNOWLEDGE_PREFIXES.join(" / "),
      icon: <Database size={16} />,
    },
    {
      id: "collaboration",
      name: "智能协同",
      detail: feishuAppBotStatus?.configured && feishuAppBotStatus.enabled ? "第二层 · 已启用" : feishuWebhookStatus.enabled ? "Webhook 已启用" : "待配置",
      icon: <Send size={16} />,
    },
    {
      id: "digital-project-assistant",
      name: "数字化项目助手",
      detail: "独立服务 · iframe",
      icon: <MonitorUp size={16} />,
    },
  ] satisfies Array<{
    id: DaweibaModuleId;
    name: string;
    detail: string;
    icon: ReactNode;
  }>;
  const activeDaweibaModuleMeta =
    daweibaModules.find((item) => item.id === activeDaweibaModule) ?? daweibaModules[0];
  const latestFeishuDelivery = feishuWebhookHistory[0] ?? feishuWebhookStatus.last_delivery ?? null;
  const feishuConnectionLabel = isTestingFeishuWebhook
    ? "发送中"
    : !feishuWebhookStatus.configured
      ? "未配置"
      : feishuWebhookStatus.enabled
        ? "已启用"
        : "已配置未启用";

  return (
    <main
      className={`shell layout-daweiba ${useZhisuanDockViewportHeight ? "is-zhisuan-viewport-height" : ""} ${uiPreferences.enabled ? "ui-tune-enabled" : ""} ${isUiPickMode ? "ui-pick-mode" : ""}`}
      onClickCapture={handleUiPick}
    >
      <nav className="global-nav" aria-label="全局导航">
        <span>{APP_NAME}</span>
        <span className="nav-status">工程造价辅助 · 本地结构化匹配 · {API_BASE_LABEL} · {APP_VERSION}</span>
        <button className="nav-text-button" type="button" onClick={showWelcomeScreen}>
          欢迎页
        </button>
        <button
          className="nav-settings-button"
          type="button"
          aria-label="页面设置"
          onClick={() => setIsPageSettingsOpen(true)}
        >
          <Settings size={16} />
        </button>
      </nav>

      {isWelcomeScreenVisible && (
        <section className={`welcome-screen is-${WELCOME_SCREEN_VARIANT}`} aria-label="欢迎页">
          <div className="welcome-shell">
            <div className="welcome-copy">
              <p className="welcome-kicker">
                <ShieldCheck size={15} />
                本地运行 · 规则可追溯 · 人工兜底
              </p>
              <h1>{APP_NAME}</h1>
              <p className="welcome-role">{APP_SUBTITLE}</p>
              <p className="welcome-lead">
                本地规则匹配价格与系数，联动经验池预警、工作量抓取和 Word 报告。
              </p>
              <div className="welcome-actions">
                <button className="welcome-primary" type="button" onClick={enterAppFromWelcome}>
                  <Sparkles size={20} />
                  进入系统
                </button>
                <label className="welcome-check">
                  <input
                    checked={hideWelcomeNextTime}
                    type="checkbox"
                    onChange={(event) => setHideWelcomeNextTime(event.target.checked)}
                  />
                  <span>下次直接进入主界面</span>
                </label>
              </div>
            </div>
            {WELCOME_SCREEN_VARIANT === "dark" ? (
              <div className="welcome-board welcome-board-dark" aria-hidden="true">
                <div className="welcome-board-head">
                  <span></span>
                  <span></span>
                  <span></span>
                  <strong>{APP_VERSION}</strong>
                </div>
                <div className="welcome-flow">
                  {[
                    ["01", "上传标准 Excel", "识别 sheet、表头与列映射"],
                    ["02", "结构化匹配", "本地知识库与规则表硬校验"],
                    ["03", "输出成果", "Excel、Word、预览与预警"],
                  ].map(([step, title, detail]) => (
                    <div className="welcome-flow-item" key={step}>
                      <b>{step}</b>
                      <span>
                        <strong>{title}</strong>
                        <small>{detail}</small>
                      </span>
                    </div>
                  ))}
                </div>
                <div className="welcome-metrics">
                  <span><strong>3</strong> 个关键数字本地裁决</span>
                  <span><strong>0</strong> API Key 也可跑核心流程</span>
                </div>
              </div>
            ) : (
              <div className="welcome-product-frame" aria-hidden="true">
                <div className="welcome-frame-toolbar">
                  <span className="welcome-frame-brand">造价智算工作台</span>
                  <span>本地服务 {API_BASE_LABEL}</span>
                </div>
                <div className="welcome-frame-body">
                  <div className="welcome-frame-rail">
                    <span className="welcome-frame-logo">智</span>
                    <FileSpreadsheet size={18} />
                    <Columns3 size={18} />
                    <Database size={18} />
                    <MessageSquareText size={18} />
                  </div>
                  <div className="welcome-frame-menu">
                    <strong>填价工作台</strong>
                    {["标准 Excel 转换", "表格预览", "经验池预警", "问问智算"].map((item, index) => (
                      <span className={index === 0 ? "is-active" : ""} key={item}>
                        {item}
                      </span>
                    ))}
                  </div>
                  <div className="welcome-frame-main">
                    <div className="welcome-frame-main-head">
                      <span>
                        <b>价格与系数匹配</b>
                        <small>基价 / 实物系数 / 技术系数</small>
                      </span>
                      <button type="button">批量匹配</button>
                    </div>
                    <div className="welcome-upload-preview">
                      <BookOpen size={20} />
                      <span>
                        <strong>规则引擎先裁决，AI 只解释</strong>
                        <small>结构化计价库、规则表和经验池预警分层处理</small>
                      </span>
                    </div>
                    <div className="welcome-mini-grid">
                      {[
                        ["待匹配行", "100"],
                        ["规则命中", "86"],
                        ["待复核", "14"],
                      ].map(([label, value]) => (
                        <span key={label}>
                          <small>{label}</small>
                          <strong>{value}</strong>
                        </span>
                      ))}
                    </div>
                    <div className="welcome-table-preview">
                      {["要素1", "单位", "基价", "匹配状态"].map((head) => (
                        <b key={head}>{head}</b>
                      ))}
                      {[
                        ["地形测量", "km", "1240", "已命中"],
                        ["管线测量", "km", "待复核", "需人工确认"],
                        ["技术工作费", "项", "0.85", "标准规则"],
                      ].flatMap((row, rowIndex) =>
                        row.map((cell, cellIndex) => (
                          <span className={rowIndex === 1 && cellIndex >= 2 ? "is-warning" : ""} key={`${rowIndex}-${cellIndex}`}>
                            {cell}
                          </span>
                        )),
                      )}
                    </div>
                  </div>
                  <div className="welcome-frame-ai">
                    <div>
                      <CheckCircle2 size={18} />
                      <strong>复核提示</strong>
                    </div>
                    <p>发现 14 行需要人工确认，已整理候选依据和经验池对比。</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      <div
        className={[
          "daweiba-layout-shell",
          isLeftColumnCollapsed ? "is-left-collapsed" : "",
          isAiDockCollapsed ? "is-ai-collapsed" : "",
        ].filter(Boolean).join(" ")}
        style={{ "--zhisuan-dock-width": `${zhisuanDockWidth}px` } as CSSProperties}
      >
        <aside className={`daweiba-nav ${isLeftColumnCollapsed ? "is-collapsed" : ""}`} aria-label="大尾巴主题模块导航">
            <div className="daweiba-icon-rail" aria-label="全局快捷入口">
              <button className="daweiba-mark" type="button" title={APP_NAME} onClick={() => setActiveDaweibaModule("fill")}>智</button>
              <button
                className={`daweiba-icon-link ${activeDaweibaModule === "fill" ? "is-active" : ""}`}
                type="button"
                title="填价工作台"
                onClick={() => setActiveDaweibaModule("fill")}
              >
                <FileSpreadsheet size={18} />
              </button>
              <button
                className={`daweiba-icon-link ${activeDaweibaModule === "preview" ? "is-active" : ""}`}
                type="button"
                title="表格预览"
                onClick={() => setActiveDaweibaModule("preview")}
              >
                <Columns3 size={18} />
              </button>
              <button
                className={`daweiba-icon-link ${activeDaweibaModule === "knowledge" ? "is-active" : ""}`}
                type="button"
                title="知识库问答"
                onClick={openDaweibaKnowledge}
              >
                <Bot size={18} />
              </button>
              <button
                className={`daweiba-icon-link ${activeDaweibaModule === "collaboration" ? "is-active" : ""}`}
                type="button"
                title="智能协同"
                onClick={() => setActiveDaweibaModule("collaboration")}
              >
                <Send size={18} />
              </button>
              <button className="daweiba-icon-link" type="button" title="页面设置" onClick={() => setIsPageSettingsOpen(true)}>
                <Settings size={18} />
              </button>
            </div>
            {!isLeftColumnCollapsed && (
              <div className="daweiba-module-rail">
                <div className="daweiba-nav-head">
                  <div>
                    <span>当前模块</span>
                    <strong>{activeDaweibaModuleMeta.name}</strong>
                  </div>
                  <button
                    className="daweiba-nav-toggle"
                    type="button"
                    aria-label="收起左侧模块导航"
                    onClick={() => setIsLeftColumnCollapsed(true)}
                  >
                    <PanelLeftClose size={17} />
                  </button>
                </div>
                <nav className="daweiba-module-list" aria-label="造价智算模块">
                  {daweibaModules.map((item) => (
                    <button
                      className={`daweiba-module-item ${activeDaweibaModule === item.id ? "is-active" : ""}`}
                      type="button"
                      key={item.id}
                      onClick={() => {
                        if (item.id === "knowledge") {
                          openDaweibaKnowledge();
                          return;
                        }
                        setActiveDaweibaModule(item.id);
                      }}
                    >
                      <span className="daweiba-module-icon">{item.icon}</span>
                      <span className="daweiba-module-copy">
                        <strong>{item.name}</strong>
                        <small>{item.detail}</small>
                      </span>
                    </button>
                  ))}
                </nav>
                <div className="daweiba-status-panel" aria-label="匹配状态仪表盘">
                  <div className="daweiba-status-chart">
                    <svg className="daweiba-status-svg" viewBox="0 0 210 150" role="img" aria-label="匹配状态环形图">
                      <g className="daweiba-status-donut" transform="translate(105 75) rotate(-90)">
                        <circle className="daweiba-status-track" cx="0" cy="0" r="44" pathLength="100" />
                        {daweibaStatusSegments.map((segment) => (
                          <circle
                            className="daweiba-status-segment"
                            cx="0"
                            cy="0"
                            r="44"
                            pathLength="100"
                            key={segment.id}
                            stroke={segment.color}
                            strokeDasharray={`${segment.percent} ${100 - segment.percent}`}
                            strokeDashoffset={-segment.offset}
                          />
                        ))}
                      </g>
                      <g className="daweiba-status-lines" aria-hidden="true">
                        <path d="M76 45 L52 25" />
                        <path d="M149 75 L181 75" />
                        <path d="M77 106 L52 126" />
                      </g>
                    </svg>
                    <div className="daweiba-status-center">
                      <strong>{result ? result.summary.total_data_rows : 0}</strong>
                      <span>Total</span>
                    </div>
                    <div className="daweiba-status-callouts" aria-label="状态分布标注">
                      {daweibaStatusCallouts.map((callout) => (
                        <span className={callout.className} key={callout.id} style={{ "--callout-color": callout.color } as CSSProperties}>
                          {callout.value} ({callout.percent}%)
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="daweiba-status-legend">
                    <span><i className="is-ok" />匹配</span>
                    <span><i className="is-review" />复核</span>
                    <span><i className="is-warning" />预警</span>
                  </div>
                  <div className="daweiba-status-rows">
                    {daweibaStatusRows.map((row) => (
                      <span key={row.label}>
                        <strong>{row.value}</strong>
                        {row.label}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}
            {isLeftColumnCollapsed && (
              <button
                className="daweiba-rail-expand"
                type="button"
                aria-label="展开左侧模块导航"
                onClick={() => setIsLeftColumnCollapsed(false)}
              >
                <PanelLeftOpen size={18} />
                <span>展开</span>
                <b>{result ? `${Math.round(daweibaStablePercent)}%` : "--"}</b>
              </button>
            )}
          </aside>
        <div className="daweiba-main-content">

      <section
        className={`daweiba-workspace-frame daweiba-workspace is-daweiba-module-${activeDaweibaModule}`}
        id="soft-workspace-start"
      >
        <div className="daweiba-fill-grid">
          <section className="input-panel" id="daweiba-input" data-ui-key="input-panel" style={uiStyle("input-panel")}>
            <div className="section-heading" data-ui-key="section-heading" style={uiStyle("section-heading")}>
              <span><Upload size={18} /></span>
              <div>
                <p>输入</p>
                <h2>上传标准 Excel</h2>
              </div>
            </div>

            <label
              className={`drop-zone ${isDragging ? "is-dragging" : ""} ${file ? "has-file" : ""}`}
              data-ui-key="drop-zone"
              style={uiStyle("drop-zone")}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <input accept=".xlsx" ref={fileInputRef} type="file" onChange={handleFileChange} />
              {file ? (
                <div className="uploaded-file-card" aria-label="已上传 Excel 基本信息">
                  <span className="uploaded-file-icon">
                    <FileSpreadsheet size={24} />
                  </span>
                  <div className="uploaded-file-content">
                    <strong>{file.name}</strong>
                    <ul className="uploaded-file-meta" aria-label="Excel 文件信息">
                      <li><span>大小</span><b>{fileSize}</b></li>
                      <li><span>行数</span><b>{uploadRowSummary}</b></li>
                    </ul>
                    <small>点击可更换文件</small>
                  </div>
                </div>
              ) : (
                <>
                  <span className="drop-icon">
                    <Upload size={30} />
                  </span>
                  <span className="drop-title" data-ui-text-key="upload.title.empty">{uiText("upload.title.empty", "拖拽 Excel 到这里")}</span>
                  <span className="drop-subtitle" data-ui-text-key="upload.subtitle.empty">
                    {uiText("upload.subtitle.empty", "或点击选择 .xlsx 文件")}
                  </span>
                </>
              )}
            </label>

            <div className="action-row">
              <button className="primary-button" data-ui-key="primary-button" data-ui-text-key={isProcessing ? "button.process.running" : "button.process.ready"} style={uiStyle("primary-button")} disabled={isProcessing || isInspecting || !file} onClick={processFile}>
                {isProcessing ? <Loader2 className="spin" size={20} /> : <Sparkles size={20} />}
                {isProcessing ? uiText("button.process.running", "正在转换") : uiText("button.process.ready", "开始转换")}
              </button>
              <button className="ghost-button" data-ui-key="secondary-button" data-ui-text-key="button.pick-file" style={uiStyle("secondary-button")} type="button" onClick={() => fileInputRef.current?.click()}>
                <FileSpreadsheet size={18} />
                {uiText("button.pick-file", "选文件")}
              </button>
              <button className="ghost-button" data-ui-key="secondary-button" style={uiStyle("secondary-button")} type="button" disabled={isDemoLoading || isProcessing} onClick={loadDemoSample}>
                {isDemoLoading ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />}
                加载演示样例
              </button>
            </div>
            {isDemoMode && (
              <div className="demo-guide-strip" role="status">
                <span>演示模式</span>
                <button type="button" onClick={() => setActiveDaweibaModule("preview")}>① 看结果</button>
                <button type="button" onClick={() => setActiveDaweibaModule("experience")}>② 跑预警</button>
                <button type="button" onClick={loadRiskSummary}>③ 风险清单</button>
                <button type="button" onClick={() => setActiveDaweibaModule("report")}>④ 输出报告</button>
              </div>
            )}

            {error && (
              <div className="notice error">
                <AlertTriangle size={18} />
                {error}
              </div>
            )}

            {file && (
              <div className={`mapping-panel ${isMappingOpen ? "is-open" : ""}`} data-ui-key="mapping-panel" style={uiStyle("mapping-panel")}>
                <button
                  className="mapping-toggle"
                  type="button"
                  aria-expanded={isMappingOpen}
                  onClick={() => setIsMappingOpen((current) => !current)}
                >
                  <span className="mapping-title">
                    <Columns3 size={18} />
                    <span>
                      <strong data-ui-text-key="mapping.title">{uiText("mapping.title", "列映射设置")}</strong>
                      <small>
                        {isInspecting
                          ? "正在读取第一行表头"
                          : sheetConfigs.length > 0
                            ? `已识别 ${sheetConfigs.length} 个候选 sheet，当前 ${activeSheetConfig()?.sheet_name ?? ""}`
                            : `第 ${headerRow} 行作为映射行，已自动预选 ${mappedFieldCount}/${MAPPING_FIELDS.length} 项`}
                      </small>
                    </span>
                  </span>
                  <ChevronDown className="mapping-chevron" size={18} />
                </button>
                {isMappingOpen && (
                  <div className="mapping-body">
                    <div className="panel-action-row">
                      <button className="experience-settings-button" data-ui-key="settings-button" style={uiStyle("settings-button")} type="button" onClick={openInputFieldSettings}>
                        {(isLoadingInputFieldSettings || isSavingInputFieldSettings) ? <Loader2 className="spin" size={17} /> : <Settings size={17} />}
                        设置
                      </button>
                    </div>
                    {sheetConfigs.length > 0 && (
                      <div className="sheet-tabs" data-ui-key="sheet-tabs" style={uiStyle("sheet-tabs")} role="tablist" aria-label="候选 sheet">
                        {sheetConfigs.map((config) => (
                          <button
                            className={config.sheet_name === activeSheetName ? "is-active" : ""}
                            key={config.sheet_name}
                            type="button"
                            onClick={() => setActiveSheetName(config.sheet_name)}
                          >
                            {config.sheet_name}
                          </button>
                        ))}
                      </div>
                    )}
                    {sheetConfigs.length > 0 && activeSheetConfig() && (
                      <label className="mapping-check-field" data-ui-key="check-field" style={uiStyle("check-field")}>
                        <input
                          checked={activeSheetConfig()?.enabled ?? true}
                          type="checkbox"
                          onChange={(event) => toggleActiveSheet(event.target.checked)}
                        />
                        <span>逐行匹配该sheet</span>
                      </label>
                    )}
                    <label className="mapping-row-field" data-ui-key="mapping-row-field" style={uiStyle("mapping-row-field")}>
                      <span>映射行</span>
                      <span className="mapping-row-control">
                        <input
                          min={1}
                          max={999}
                          type="number"
                          value={activeSheetConfig()?.header_row ?? headerRow}
                          disabled={isInspecting}
                          onChange={(event) => updateActiveHeaderRow(Math.max(1, Number(event.target.value) || 1))}
                        />
                        <button
                          type="button"
                          disabled={isInspecting || !file}
                          onClick={() => {
                            if (!file) return;
                            const config = activeSheetConfig();
                            inspectFile(file, config?.header_row ?? headerRow, config?.sheet_name);
                          }}
                        >
                          读取该行
                        </button>
                      </span>
                    </label>
                    <label className="mapping-check-field" data-ui-key="check-field" style={uiStyle("check-field")}>
                      <input
                        checked={outputMatchReport}
                        type="checkbox"
                        onChange={(event) => setOutputMatchReport(event.target.checked)}
                      />
                      <span>输出逐行匹配报告</span>
                    </label>
                    <label className="mapping-check-field" data-ui-key="check-field" style={uiStyle("check-field")}>
                      <input
                        checked={onlyMatchRowsWithValue}
                        type="checkbox"
                        onChange={(event) => setOnlyMatchRowsWithValue(event.target.checked)}
                      />
                      <span>不匹配指定列无值的行</span>
                    </label>
                    <label className="mapping-row-field" data-ui-key="mapping-row-field" style={uiStyle("mapping-row-field")}>
                      <span>指定列</span>
                      <span className="mapping-row-control">
                        <select
                          value={matchValueFilterField}
                          disabled={!onlyMatchRowsWithValue}
                          onChange={(event) => setMatchValueFilterField(event.target.value as WarningFilterField)}
                        >
                          {WARNING_FILTER_FIELDS.map((field) => (
                            <option value={field} key={field}>{field}</option>
                          ))}
                        </select>
                      </span>
                    </label>
                    <p className="settings-hint">开启后，指定列为空、数字 0 或公式结果 0 的行不做价格和系数匹配，也不计入匹配统计。</p>
                    <label className="mapping-check-field" data-ui-key="check-field" style={uiStyle("check-field")}>
                      <input
                        checked={mergeVerticalCells}
                        type="checkbox"
                        onChange={(event) => setMergeVerticalCells(event.target.checked)}
                      />
                      <span>纵向合并单元格按每一行继承同一值</span>
                    </label>
                    <label className="mapping-check-field" data-ui-key="check-field" style={uiStyle("check-field")}>
                      <input
                        checked={mergeHorizontalCells}
                        type="checkbox"
                        onChange={(event) => setMergeHorizontalCells(event.target.checked)}
                      />
                      <span>横向合并单元格只让第一列继承值，其他列按空值</span>
                    </label>
                    <div className="mapping-grid">
                      {MAPPING_FIELDS.map((field) => {
                        const missing = isMappingMissing(field);
                        return (
                        <label className={`mapping-field ${missing ? "is-missing" : ""}`} data-ui-key="mapping-field" style={uiStyle("mapping-field")} key={field}>
                          <span>
                            {fieldLabel(field)}
                            {missing && <small>未识别</small>}
                          </span>
                          <select
                            value={activeMapping()[field] ?? ""}
                            disabled={isInspecting || activeColumns().length === 0}
                            onChange={(event) => updateActiveMapping(field, event.target.value)}
                          >
                            <option value="">请选择列</option>
                            {allowsEmptyElement(field) && (
                              <option value={EMPTY_ELEMENT_COLUMN}>{EMPTY_ELEMENT_COLUMN}</option>
                            )}
                            {activeColumns().map((column) => (
                              <option key={`${field}-${column.letter}`} value={column.letter}>
                                {column.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

          </section>

          <section className="brief-panel" data-ui-key="brief-panel" style={uiStyle("brief-panel")}>
            <div className="section-heading" data-ui-key="section-heading" style={uiStyle("section-heading")}>
              <span><PanelTop size={18} /></span>
              <div>
                <p>简报</p>
                <h2 data-ui-text-key="summary.title">{uiText("summary.title", "转换后概览")}</h2>
              </div>
            </div>

            {result || isProcessing ? (
              <>
                <div className="summary-hero" data-ui-key="summary-hero" style={uiStyle("summary-hero")}>
                  <span>
                    {isProcessing
                      ? "生成预览"
                      : isBatchMatchPending
                        ? "等待批量匹配"
                        : result?.summary.review_rows === 0
                          ? "匹配完成"
                          : "需要复核"}
                  </span>
                  <strong>{Math.round(displayCompletion)}%</strong>
                  <p>
                    {isProcessing
                      ? "正在读取输入表和列映射，先生成待匹配预览。"
                      : isBatchMatchPending
                        ? "已生成表格预览，点击预览窗口的“批量匹配”后再填写价格和两个系数。"
                      : result?.summary.report_text}
                  </p>
                </div>

                <div className="meter" aria-label={`回填完成率 ${Math.round(displayCompletion)}%`}>
                  <div className="meter-track">
                    <div className="meter-fill" style={{ width: `${displayCompletion}%` }} />
                  </div>
                </div>

                {isProcessing && (
                  <div className="process-stages" aria-label="转换阶段">
                    {PROCESSING_STAGES.map((stage) => {
                      const isActive = stage.title === processingStage.title;
                      const isDone = displayCompletion >= stage.min && !isActive;
                      return (
                        <div
                          className={`process-stage ${isActive ? "active" : ""} ${isDone ? "done" : ""}`}
                          key={stage.title}
                        >
                          <span>{stage.shortLabel}</span>
                        </div>
                      );
                    })}
                  </div>
                )}

                <div className="stats" data-ui-key="stats-grid" style={uiStyle("stats-grid")}>
                  <Metric label="输入行数" value={result?.summary.total_data_rows ?? "读取中"} />
                  <Metric label="转换成功" value={isBatchMatchPending ? "待匹配" : result?.summary.filled_rows ?? "处理中"} />
                  <Metric label="结构匹配" value={isBatchMatchPending ? "待执行" : result?.summary.matched_rows ?? "匹配中"} />
                  <Metric
                    label={isProcessing ? "当前阶段" : "待复核"}
                    value={isProcessing ? processingStage.shortLabel : result?.summary.review_rows ?? "检查中"}
                    tone={result?.summary.review_rows ? "warn" : "ok"}
                  />
                </div>

                {result && (
                  <div className="download-row" id="daweiba-output" data-ui-key="download-row" style={uiStyle("download-row")}>
                    <a className={`download-button ${!canDownloadOutputs ? "is-disabled" : ""}`} href={canDownloadOutputs ? excelDownloadHref : "#"} aria-disabled={!canDownloadOutputs}>
                      <Download size={18} />
                      下载 Excel
                    </a>
                    <a className={`download-button secondary ${!canDownloadOutputs ? "is-disabled" : ""}`} href={canDownloadOutputs ? `${API_BASE}${result.downloads.report}` : "#"} aria-disabled={!canDownloadOutputs}>
                      <Download size={18} />
                      下载 Word
                    </a>
                  </div>
                )}
              </>
            ) : (
              <div className="empty-summary">
                <PanelTop size={30} />
                <p>转换完成后，这里会显示输入行数、成功行数、待复核行数和下载入口。</p>
              </div>
            )}
          </section>

          <section className="daweiba-fill-insight-panel" aria-label="填价工作台状态">
              <div className="section-heading compact">
                <span><ShieldCheck size={18} /></span>
                <div>
                  <p>状态</p>
                  <h2>工作状态</h2>
                </div>
              </div>

              {result ? (
                <>
                  <div className="daweiba-fill-overview-row" aria-label="匹配状态和质量分布">
                    <div className="widescreen-status-card daweiba-fill-status-large">
                      <span>匹配状态</span>
                      <strong>
                        <CheckCircle2 size={18} />
                        {isBatchMatchPending ? "等待批量匹配" : `${result.summary.filled_rows}/${result.summary.total_data_rows} 行完成`}
                      </strong>
                      <small>
                        {isBatchMatchPending
                          ? "点击预览窗口“批量匹配”后填写价格和两个系数"
                          : `待复核 ${result.summary.review_rows} 行 · 预警 ${warningSummary?.executed ? `${warningSummary.warning_rows} 条` : "未运行"}`}
                      </small>
                    </div>
                    <div className="widescreen-ring-card daweiba-fill-quality-card">
                      <div className={`widescreen-ring ${isWideRingEmpty ? "is-empty" : ""}`} style={wideRingStyle}>
                        <span>{wideStablePercent}%</span>
                      </div>
                      <div>
                        <strong>匹配质量分布</strong>
                        <span>高置信匹配 {wideStableRows} 行</span>
                        <span>低风险 {wideLowWarningRows} 行 · 高风险 {wideHighWarningRows} 行</span>
                      </div>
                    </div>
                  </div>

                  <div className="daweiba-fill-system-grid" aria-label="工作台扩展状态">
                    {workbenchStatusCards.map((card) => (
                      <div className="daweiba-fill-system-card" key={card.label}>
                        <span>{card.label}</span>
                        <strong>{card.value}</strong>
                        <small>{card.detail}</small>
                      </div>
                    ))}
                  </div>

                  <div className="daweiba-fill-action-stack" aria-label="下一步动作">
                    <button type="button" onClick={() => setActiveDaweibaModule("preview")}>
                      <span><FileSpreadsheet size={18} /></span>
                      <strong>结果预览</strong>
                      <small>查看填价表格和 AI 行级入口</small>
                    </button>
                    <button type="button" onClick={() => setActiveDaweibaModule("experience")}>
                      <span><AlertTriangle size={18} /></span>
                      <strong>经验池预警</strong>
                      <small>跑同类记录和偏离率分析</small>
                    </button>
                    <button type="button" onClick={() => setActiveDaweibaModule("report")}>
                      <span><FileText size={18} /></span>
                      <strong>Word 报告</strong>
                      <small>生成、下载和预览成果文件</small>
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="daweiba-fill-status-card">
                    <span>{file ? "Excel 已就绪" : "等待输入"}</span>
                    <strong>{file ? "准备转换" : "先选择标准 Excel"}</strong>
                    <p>
                      {file
                        ? "点击开始转换后，智算会同步跟踪字段识别、结构化匹配和输出生成。"
                        : "拖入或选择 .xlsx 文件后，这里会显示匹配状态、匹配质量分布和关键进度。"}
                    </p>
                  </div>

                  <div className="daweiba-fill-mini-grid" aria-label="当前数据摘要">
                    <div>
                      <span>输入行</span>
                      <strong>{daweibaInputRows}</strong>
                    </div>
                    <div>
                      <span>已预览</span>
                      <strong>{daweibaPreviewRows}</strong>
                    </div>
                    <div>
                      <span>待复核</span>
                      <strong>{daweibaReviewCount}</strong>
                    </div>
                    <div>
                      <span>预警</span>
                      <strong>{daweibaWarningCount}</strong>
                    </div>
                  </div>
                </>
              )}
          </section>
        </div>

        <section className="daweiba-preview-section" id="preview-section" data-ui-key="preview-section" style={uiStyle("preview-section")}>
          <div className="section-heading" data-ui-key="section-heading" style={uiStyle("section-heading")}>
            <span><FileSpreadsheet size={18} /></span>
            <div>
              <p>预览</p>
              <h2 data-ui-text-key={activeDaweibaModule === "fill" ? undefined : "preview.title"}>
                {activeDaweibaModule === "fill" ? "表格预览" : uiText("preview.title", "可视化表格窗口")}
              </h2>
            </div>
          </div>

          {result ? (
            <div className="preview-grid">
              <div className="preview-window" data-ui-key="preview-window" style={uiStyle("preview-window")}>
                <div className="window-bar">
                  <span className="traffic" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                  <span className="preview-window-title">填价结果预览</span>
                  <span className="window-actions">
                    <strong className="preview-window-count">
                      前 {visiblePreviewRows.length} 行
                      {hiddenPreviewRowCount > 0 ? ` · 已隐藏 ${hiddenPreviewRowCount} 行` : ""}
                    </strong>
                    {previewManualEditMessage && (
                      <span className="preview-cell-edit-status" title={previewManualEditMessage}>
                        {previewManualEditMessage}
                      </span>
                    )}
                    <button
                      className={`window-primary-button ${isBatchMatchPending ? "" : "is-complete"}`}
                      type="button"
                      disabled={!isBatchMatchPending || isBatchMatching}
                      onClick={runBatchMatch}
                    >
                      {isBatchMatching ? <Loader2 size={15} className="spin" /> : <Sparkles size={15} />}
                      {isBatchMatchPending ? "批量匹配" : "已完成匹配"}
                    </button>
                    <button
                      className="window-settings-button"
                      type="button"
                      disabled={!result || isRecalculatingPreview || isBatchMatchPending}
                      onClick={recalculatePreviewWorkbook}
                    >
                      {isRecalculatingPreview ? <Loader2 size={15} className="spin" /> : <PanelTop size={15} />}
                      重算公式
                    </button>
                    <button className="window-settings-button" type="button" aria-label="预览列设置" onClick={openPreviewSettings}>
                      <Settings size={15} />
                      设置
                    </button>
                  </span>
                </div>
                {previewSheets.length > 0 && (
                  <div className="preview-tabs" data-ui-key="sheet-tabs" style={uiStyle("sheet-tabs")} role="tablist" aria-label="预览 sheet">
                    <span className="preview-tabs-label">Sheet 切换</span>
                    {previewSheets.map((sheet, sheetIndex) => {
                      const sheetName = previewSheetLabel(sheet, sheetIndex);
                      const activeSheetName = previewSheetLabel(activePreview, 0);
                      const isActive = sheetName === activeSheetName;
                      return (
                        <button
                          aria-pressed={isActive}
                          className={isActive ? "is-active" : ""}
                          key={`${sheetIndex}-${sheetName}`}
                          type="button"
                          title={`切换到 ${sheetName}`}
                          onClick={() => setActivePreviewSheetName(sheet.sheet_name || sheetName)}
                        >
                          {sheetName}
                        </button>
                      );
                    })}
                    <span className="preview-tabs-count">共 {previewSheets.length} 个</span>
                  </div>
                )}
                <div
                  className="table-scroll"
                  ref={previewScrollRef}
                  style={{ "--preview-cell-max-chars": `${previewColumnPreferences.maxDisplayChars}ch` } as CSSProperties}
                >
                  <table>
                    <thead>
                      <tr>
                        <th className="row-number-th">行号</th>
                        {previewColumns.map((column) => (
                          <th
                            className={previewColumnSavedWidth(activePreview, column) ? "preview-resizable-th preview-column-custom-width" : "preview-resizable-th"}
                            key={`${column.label}-${column.index}`}
                            style={previewColumnWidthStyle(activePreview, column)}
                            title={column.label}
                          >
                            <span className="preview-header-label">{column.label}</span>
                            <span
                              aria-label={`调整 ${column.label} 列宽`}
                              aria-orientation="vertical"
                              className="preview-column-resize-zone"
                              onPointerDown={(event) => startPreviewColumnResize(event, activePreview, column)}
                              role="separator"
                            />
                          </th>
                        ))}
                        <th className="action-th">AI</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visiblePreviewRows.map(({ row, sourceIndex }) => {
                        const excelRowNumber = previewExcelRowNumber(activePreview, sourceIndex, sheetConfigs);
                        const isFocusedRow = (
                          Boolean(focusedPreviewJump)
                          && normalizePreviewSheetName(activePreview.sheet_name) === normalizePreviewSheetName(focusedPreviewJump?.sheetName)
                          && focusedPreviewJump?.excelRow === excelRowNumber
                        );
                        const isTotalRow = isTotalSummaryRow(row);
                        return (
                        <tr
                          className={[
                            isFocusedRow ? "preview-row-focused" : "",
                            isTotalRow ? "preview-total-row" : "",
                          ].filter(Boolean).join(" ")}
                          data-preview-row={excelRowNumber}
                          data-preview-sheet={normalizePreviewSheetName(activePreview.sheet_name)}
                          key={`${sourceIndex}-${row.join("|")}`}
                        >
                          <td className="preview-row-number-cell">{excelRowNumber}</td>
                          {previewColumns.map((column) => (
                            (() => {
                              const columnNumber = column.index + 1;
                              const editKey = previewEditKey(previewSheetLabel(activePreview, 0), excelRowNumber, columnNumber);
                              const isEditable = isEditablePreviewColumn(column);
                              const isEditing = isEditingPreviewCell(sourceIndex, column);
                              const isSaving = savingPreviewCellKey === editKey;
                              return (
                            <td
                              className={[
                                previewCellClass(column, row, previewColumns),
                                column.kind === "number" ? "preview-number-cell" : "",
                                previewColumnSavedWidth(activePreview, column) ? "preview-column-custom-width" : "",
                                isFocusedRow && column.index === focusedPreviewColumnIndex ? "preview-cell-focused" : "",
                                isEditable ? "preview-cell-editable" : "preview-cell-readonly",
                                isEditing ? "is-editing" : "",
                                isSaving ? "is-saving" : "",
                              ].filter(Boolean).join(" ")}
                              data-preview-column={column.index}
                              key={`${sourceIndex}-${column.label}`}
                              style={previewColumnWidthStyle(activePreview, column)}
                              title={isEditable ? `${previewCellTitle(column, row, previewColumns)}\n双击人工修改` : previewCellTitle(column, row, previewColumns)}
                              onDoubleClick={() => startPreviewCellEdit(column, row, sourceIndex)}
                            >
                              {isEditing ? (
                                (() => {
                                  const editSnapshot = editingPreviewCell;
                                  return (
                                <input
                                  autoFocus
                                  className="preview-cell-edit-input"
                                  disabled={isSaving}
                                  value={editingPreviewCell?.draftValue ?? ""}
                                  onBlur={(event) => handlePreviewEditBlur(editSnapshot, event.currentTarget.value)}
                                  onChange={(event) => updateEditingPreviewCell(event.target.value)}
                                  onKeyDown={(event) => handlePreviewEditKeyDown(event, editSnapshot)}
                                />
                                  );
                                })()
                              ) : (
                                <span className="preview-cell-content">
                                  {isSaving ? "保存中..." : renderPreviewCellContent(column, row, previewColumns)}
                                </span>
                              )}
                            </td>
                              );
                            })()
                          ))}
                          <td className="row-ai-cell">
                            <div className="row-ai-actions">
                              <button
                                className="row-ai-button fill-assist-row-button"
                                type="button"
                                title="辅助填价"
                                aria-label="辅助填价"
                                onClick={() => openFillAssist(row, sourceIndex)}
                              >
                                <BookOpen size={16} />
                              </button>
                              <button
                                className="row-ai-button"
                                type="button"
                                title="行级AI复核"
                                aria-label="行级AI复核"
                                onClick={() => openRowAi(row, sourceIndex)}
                              >
                                <Bot size={16} />
                              </button>
                            </div>
                          </td>
                        </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            <div className="preview-empty">
              <FileSpreadsheet size={32} />
              <p>上传并转换后，将在这里显示回填后的前几行数据。</p>
            </div>
          )}
        </section>

        <section className="experience-section" id="experience-section" data-ui-key="experience-section" style={uiStyle("experience-section")}>
          <div className="section-heading" data-ui-key="section-heading" style={uiStyle("section-heading")}>
            <span><AlertTriangle size={18} /></span>
            <div>
              <p>经验池预警</p>
              <h2 data-ui-text-key="experience.title">{uiText("experience.title", "经验池预警与导入")}</h2>
            </div>
          </div>

          <div className="experience-panel daweiba-warning-module" data-ui-key="warning-panel" style={uiStyle("warning-panel")}>
              <div className="experience-panel-head">
                <div className="experience-copy">
                  <AlertTriangle size={24} />
                  <div>
                    <strong>经验池预警模块</strong>
                    <span>手动运行同类记录比选，生成预警参数、预警细节和风险定位；不参与正式价格裁决。</span>
                  </div>
                </div>
                <div className="settings-action-row compact">
                  <button className="experience-settings-button" type="button" onClick={openExperienceWarningSettings}>
                    {(isLoadingExperienceWarningSettings || isSavingExperienceWarningSettings) ? <Loader2 className="spin" size={17} /> : <Settings size={17} />}
                    设置
                  </button>
                  <button className="experience-settings-button" type="button" disabled={isExperienceGovernanceLoading} onClick={loadExperienceGovernance}>
                    {isExperienceGovernanceLoading ? <Loader2 className="spin" size={17} /> : <ShieldCheck size={17} />}
                    治理报告
                  </button>
                  <button className="primary-button" type="button" disabled={!result || isRunningWarnings || isBatchMatchPending} onClick={() => runExperienceWarnings()}>
                    {isRunningWarnings ? <Loader2 className="spin" size={18} /> : <AlertTriangle size={18} />}
                    {isRunningWarnings
                      ? "正在分析预警"
                      : warningSummary?.executed
                        ? "重新运行经验池预警分析"
                        : "运行经验池预警分析"}
                  </button>
                </div>
              </div>

              {isRunningWarnings && (
                <div className="warning-progress-card" data-ui-key="result-card" style={uiStyle("result-card")}>
                  <div className="warning-progress-head">
                    <strong>预警匹配进度</strong>
                    <span>已匹配 {warningProgress.processed_rows} / {warningProgress.total_rows} 行</span>
                  </div>
                  <div className="meter warning-progress-meter">
                    <div className="meter-track">
                      <div className="meter-fill warning-progress-fill" style={{ width: `${warningProgressPercent}%` }} />
                    </div>
                  </div>
                  <div className="warning-metric-row">
                    <span>已处理：{warningProgress.processed_rows}</span>
                    <span>已找到可比选：{warningProgress.matched_rows}</span>
                    <span>已触发预警：{warningProgress.warning_rows}</span>
                  </div>
                </div>
              )}

              {experienceGovernance && (
                <div className="governance-report-panel" data-ui-key="result-card" style={uiStyle("result-card")}>
                  <div className="warning-panel-head">
                    <span>
                      <ShieldCheck size={18} />
                      经验池治理报告
                    </span>
                    <strong>问题线索 {experienceGovernance.summary.issue_count} 项 · 有效记录 {experienceGovernance.summary.valid_key_rows}/{experienceGovernance.summary.total_rows}</strong>
                  </div>
                  <div className="warning-metric-cluster">
                    {Object.entries(experienceGovernance.summary.categories).map(([category, count]) => (
                      <span key={category}>{category}：{count}</span>
                    ))}
                  </div>
                  {experienceGovernance.report_path && <p className="settings-hint">报告路径：{experienceGovernance.report_path}</p>}
                  <div className="governance-issue-list">
                    {experienceGovernance.issues.slice(0, 5).map((issue, index) => (
                      <div className={`governance-issue severity-${issue.severity}`} key={`${issue.category}-${issue.row}-${index}`}>
                        <strong>{issue.title ?? issue.category} · {issue.sheet ? `${issue.sheet} 第 ${issue.row} 行` : "经验池"}</strong>
                        {issue.key_text && <small>{issue.key_text}</small>}
                        <span>{issue.message}</span>
                        <em>{issue.suggestion}</em>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {!result && (
                <div className="warning-panel warning-pending" data-ui-key="warning-panel" style={uiStyle("warning-panel")}>
                  <div className="warning-panel-head">
                    <span>
                      <AlertTriangle size={18} />
                      等待填价结果
                    </span>
                    <strong>先完成 Excel 转换</strong>
                  </div>
                  <p className="warning-summary-text">转换完成后，可在这里运行经验池预警分析。</p>
                </div>
              )}

              {result && warningSummary && !warningSummary.executed && (
                <div className="warning-panel warning-pending" data-ui-key="warning-panel" style={uiStyle("warning-panel")}>
                  <div className="warning-panel-head">
                    <span>
                      <AlertTriangle size={18} />
                      经验池预警未执行
                    </span>
                    <strong>手动运行后生成预警列</strong>
                  </div>
                  <p className="warning-summary-text">
                    {warningSummary.summary_text ?? "点击运行经验池预警分析后，会与经验池比选并写入预警参数、预警细节。"}
                  </p>
                </div>
              )}

              {warningSummary?.executed && warningSummary?.pool_enabled && (
                <div className="warning-panel" data-ui-key="warning-panel" style={uiStyle("warning-panel")}>
                  <div className="warning-panel-head">
                    <span>
                      <AlertTriangle size={18} />
                      经验池预警
                    </span>
                    <strong>可比选 {warningSummary.checked_rows} 行 · 未找到同类 {warningSummary.no_comparable_rows ?? 0} 行 · 高风险 {warningSummary.high_rows} · 低风险 {warningSummary.low_rows ?? warningSummary.medium_rows ?? 0}</strong>
                  </div>
                  <p className="warning-summary-text">
                    {warningSummary.summary_text ?? `经验池预警：发现 ${warningSummary.warning_rows} 条预警。`}
                  </p>
                  <div className="warning-metric-cluster" data-ui-key="result-card" style={uiStyle("result-card")}>
                    {typeof warningSummary.candidate_rows === "number" && (
                      <>
                        <span>输入候选：{warningSummary.candidate_rows}</span>
                        <span>可比选：{warningSummary.checked_rows}</span>
                        <span>未找到同类：{warningSummary.no_comparable_rows ?? 0}</span>
                      </>
                    )}
                    {warningSummary.match_mode_counts && Object.entries(warningSummary.match_mode_counts).map(([mode, count]) => (
                      <span key={`mode-${mode}`}>{mode}：{count}</span>
                    ))}
                    {warningSummary.metric_counts && Object.entries(warningSummary.metric_counts).map(([metric, count]) => (
                      <span key={`metric-${metric}`}>{metric}：{count}</span>
                    ))}
                    {typeof warningSummary.low_risk_threshold_percent === "number" && typeof warningSummary.high_risk_threshold_percent === "number" && (
                      <>
                        <span>低风险阈值：{warningSummary.low_risk_threshold_percent}%</span>
                        <span>高风险阈值：{warningSummary.high_risk_threshold_percent}%</span>
                      </>
                    )}
                  </div>
                  {warningDetails.length > 0 ? (
                    <div className="warning-list">
                      {visibleWarnings.map((warning, index) => (
                        <div
                          className={`warning-item severity-${warning.severity}`}
                          key={`${warning.sheet_name}-${warning.excel_row}-${warning.metric}-${index}`}
                        >
                          <div>
                            <strong>{warning.severity_label ?? (warning.severity === "high" ? "高风险" : warning.severity === "low" ? "低风险" : "无预警")} · {warning.sheet_name} 第 {warning.excel_row} 行 · {warning.metric}</strong>
                            {warning.row_key && <small>{warning.row_key}</small>}
                            {warning.match_mode_detail && <small>匹配模式：{warning.match_mode_detail}</small>}
                            <span>{warning.message}</span>
                            {warning.suggested_action && <em>{warning.suggested_action}</em>}
                            {warning.source_rows?.length > 0 && (
                              <small>
                                来源：{warning.source_rows.slice(0, 2).map((source) => `${source.source_file} ${source.source_sheet} 第${source.source_row}行`).join("；")}
                              </small>
                            )}
                          </div>
                          <div className="warning-side">
                            <div className="warning-values">
                              <span>当前 {warning.current_value}</span>
                              <span>平均 {String((warning as WarningDetail & { experience_average?: number }).experience_average ?? "")}</span>
                              <span>范围 {warning.experience_range_text ?? warning.experience_values.join(" / ")}</span>
                              <span>偏离 {String((warning as WarningDetail & { deviation_percent?: number }).deviation_percent ?? "")}%</span>
                              <span>样本 {warning.sample_count}</span>
                            </div>
                            <button
                              className="warning-jump-button"
                              type="button"
                              title={`跳转到 ${warning.sheet_name} 第 ${warning.excel_row} 行`}
                              onClick={() => jumpToWarningPreview(warning)}
                            >
                              <FileSpreadsheet size={14} />
                              跳到表格
                            </button>
                          </div>
                        </div>
                      ))}
                      {warningDetails.length > 6 && (
                        <button className="warning-more-button" type="button" onClick={() => setShowAllWarnings((current) => !current)}>
                          {showAllWarnings ? "收起预警" : `查看全部 ${warningDetails.length} 条预警`}
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="warning-empty">
                      <CheckCircle2 size={18} />
                      当前输出数字未触发经验池预警。
                    </div>
                  )}
                </div>
              )}
          </div>

          <div className={`experience-panel daweiba-experience-import-module ${isExperienceImportCollapsed ? "is-collapsed" : ""}`} data-ui-key="experience-panel" style={uiStyle("experience-panel")}>
            <div className="experience-panel-head">
              <div className="experience-copy">
                <Database size={24} />
                <div>
                  <strong>经验池导入模块</strong>
                  <span>先选择 sheet 和字段列，再写入独立经验池；经验池只用于预警比选，不改正式知识库，也不影响第二层经验提示。</span>
                </div>
              </div>
              <div className="settings-action-row compact">
                <button
                  className="experience-settings-button"
                  type="button"
                  onClick={() => setIsExperienceImportCollapsed((current) => !current)}
                >
                  <ChevronDown className="mapping-chevron" size={17} />
                  {isExperienceImportCollapsed ? "展开" : "折叠"}
                </button>
                <button className="experience-settings-button" type="button" onClick={openExperienceFieldSettings}>
                  {isLoadingExperienceFieldSettings ? <Loader2 className="spin" size={17} /> : <Settings size={17} />}
                  设置
                </button>
              </div>
            </div>

            {!isExperienceImportCollapsed && (
              <>

            <div
              className={`experience-actions ${isExperienceDragging ? "is-dragging" : ""} ${experienceFile ? "has-file" : ""}`}
              data-ui-key="experience-file-card"
              style={uiStyle("experience-file-card")}
              onDragOver={handleExperienceDragOver}
              onDragLeave={handleExperienceDragLeave}
              onDrop={handleExperienceDrop}
            >
              <input
                accept=".xlsx"
                ref={experienceFileInputRef}
                type="file"
                onChange={handleExperienceFileChange}
              />
              <button className="ghost-button" type="button" onClick={() => experienceFileInputRef.current?.click()}>
                <FileSpreadsheet size={18} />
                {experienceFile ? experienceFile.name : "选择控制价文件"}
              </button>
              <button className="primary-button" disabled={!experienceFile || isImportingExperience} type="button" onClick={importExperienceFile}>
                {isImportingExperience ? <Loader2 className="spin" size={18} /> : <Database size={18} />}
                {isImportingExperience ? "正在导入" : "导入经验池"}
              </button>
              <span className="file-drop-hint">可点击选择，也可拖入 .xlsx 控制价文件</span>
            </div>

            <div className="experience-field-row" data-ui-key="experience-field-row" style={uiStyle("experience-field-row")}>
              <span className="experience-field-label">导入预警数值</span>
              {EXPERIENCE_FIELD_OPTIONS.map((field) => (
                <label className="mapping-check-field" data-ui-key="check-field" style={uiStyle("check-field")} key={field}>
                  <input
                    checked={selectedExperienceFields.includes(field)}
                    type="checkbox"
                    onChange={(event) => toggleExperienceField(field, event.target.checked)}
                  />
                  <span>{field}</span>
                </label>
              ))}
            </div>

            {experienceFile && (
              <div className={`mapping-panel experience-mapping-panel ${isExperienceMappingOpen ? "is-open" : ""}`} data-ui-key="experience-mapping-panel" style={uiStyle("experience-mapping-panel")}>
                <button
                  className="mapping-toggle"
                  type="button"
                  aria-expanded={isExperienceMappingOpen}
                  onClick={() => setIsExperienceMappingOpen((current) => !current)}
                >
                  <span className="mapping-title">
                    <Columns3 size={18} />
                    <span>
                      <strong>经验池列选择窗口</strong>
                      <small>
                        {isInspectingExperience
                          ? "正在读取经验表表头"
                          : experienceSheetConfigs.length > 0
                            ? `已读取 ${experienceSheetConfigs.length} 个 sheet，当前 ${activeExperienceSheetConfig()?.sheet_name ?? ""}，已映射 ${mappedExperienceFieldCount}/${EXPERIENCE_MAPPING_FIELDS.length} 项`
                            : "选择文件后自动读取 sheet 和表头"}
                      </small>
                    </span>
                  </span>
                  <ChevronDown className="mapping-chevron" size={18} />
                </button>
                {isExperienceMappingOpen && (
                  <div className="mapping-body">
                    {experienceSheetConfigs.length > 0 && (
                      <div className="sheet-tabs" data-ui-key="sheet-tabs" style={uiStyle("sheet-tabs")} role="tablist" aria-label="经验池候选 sheet">
                        {experienceSheetConfigs.map((config) => (
                          <button
                            className={config.sheet_name === activeExperienceSheetName ? "is-active" : ""}
                            key={config.sheet_name}
                            type="button"
                            onClick={() => setActiveExperienceSheetName(config.sheet_name)}
                          >
                            {config.enabled ? "导入 · " : "跳过 · "}{config.sheet_name}
                          </button>
                        ))}
                      </div>
                    )}
                    {activeExperienceSheetConfig() && (
                      <>
                        <label className="mapping-check-field" data-ui-key="check-field" style={uiStyle("check-field")}>
                          <input
                            checked={activeExperienceSheetConfig()?.enabled ?? true}
                            type="checkbox"
                            onChange={(event) => toggleActiveExperienceSheet(event.target.checked)}
                          />
                          <span>导入该 sheet 到经验池</span>
                        </label>
                        <label className="mapping-row-field" data-ui-key="mapping-row-field" style={uiStyle("mapping-row-field")}>
                          <span>映射行</span>
                          <span className="mapping-row-control">
                            <input
                              min={1}
                              max={999}
                              type="number"
                              value={activeExperienceSheetConfig()?.header_row ?? 1}
                              disabled={isInspectingExperience}
                              onChange={(event) => updateActiveExperienceHeaderRow(Math.max(1, Number(event.target.value) || 1))}
                            />
                            <button
                              type="button"
                              disabled={isInspectingExperience || !experienceFile}
                              onClick={() => {
                                if (!experienceFile) return;
                                const config = activeExperienceSheetConfig();
                                inspectExperienceFile(experienceFile, config?.header_row ?? 1, config?.sheet_name);
                              }}
                            >
                              读取该行
                            </button>
                          </span>
                        </label>
                        <div className="mapping-grid experience-mapping-grid">
                          {EXPERIENCE_MAPPING_FIELDS.map((field) => {
                            const missing = isExperienceMappingMissing(field);
                            return (
                              <label className={`mapping-field ${missing ? "is-missing" : ""}`} data-ui-key="mapping-field" style={uiStyle("mapping-field")} key={field}>
                                <span>
                                  {field}
                                  {missing && <small>必选</small>}
                                </span>
                                <select
                                  value={activeExperienceMapping()[field] ?? ""}
                                  disabled={isInspectingExperience || activeExperienceColumns().length === 0}
                                  onChange={(event) => updateActiveExperienceMapping(field, event.target.value)}
                                >
                                  <option value="">不导入</option>
                                  {activeExperienceColumns().map((column) => (
                                    <option key={`${field}-${column.letter}`} value={column.letter}>
                                      {column.label}
                                    </option>
                                  ))}
                                </select>
                              </label>
                            );
                          })}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}

            {experienceImportSummary && (
              <div className="experience-result" data-ui-key="result-card" style={uiStyle("result-card")}>
                <CheckCircle2 size={18} />
                <div>
                  <strong>已导入 {experienceImportSummary.imported_rows} 行经验数据</strong>
                  <span>
                    来源：{experienceImportSummary.source_file} · 跳过 {experienceImportSummary.skipped_rows} 行 ·
                    经验池：{experienceImportSummary.pool_path}
                  </span>
                </div>
              </div>
            )}
              </>
            )}
          </div>
        </section>

        <section className="workload-section" id="workload-section" data-ui-key="workload-section" style={uiStyle("workload-section")}>
          <div className="section-heading" data-ui-key="section-heading" style={uiStyle("section-heading")}>
            <span><Columns3 size={18} /></span>
            <div>
              <p>没填数量？</p>
              <h2 data-ui-text-key="workload.title">{uiText("workload.title", "原始工作量抓取模块")}</h2>
            </div>
          </div>

          <div className="experience-panel" data-ui-key="workload-panel" style={uiStyle("workload-panel")}>
            <div className="experience-panel-head">
              <div className="experience-copy">
                <FileSpreadsheet size={24} />
                <div>
                  <strong>从委托方工作量表补齐控制价计算表</strong>
                  <span>工作量抓取按要素1-5和单位的模式A+B执行：先字段完全匹配，再用非空要素顺序匹配兜底；只在一对一确定时写入数量、系数和备注。</span>
                </div>
              </div>
              <div className="settings-action-row compact">
                <button className="experience-settings-button" type="button" onClick={openWorkloadFieldSettings}>
                  {(isLoadingWorkloadFieldSettings || isLoadingWorkloadTargetFieldSettings || isSavingWorkloadFieldSettings || isSavingWorkloadTargetFieldSettings)
                    ? <Loader2 className="spin" size={17} />
                    : <Settings size={17} />}
                  设置
                </button>
              </div>
            </div>

            <div className="workload-input-grid">
              <div className="workload-file-grid" data-ui-key="workload-file-grid" style={uiStyle("workload-file-grid")}>
                <div
                  className={`workload-file-card ${workloadDraggingRole === "source" ? "is-dragging" : ""} ${workloadFile ? "has-file" : ""}`}
                  data-ui-key="workload-file-card"
                  style={uiStyle("workload-file-card")}
                  onDragOver={(event) => handleWorkloadDragOver(event, "source")}
                  onDragLeave={(event) => handleWorkloadDragLeave(event, "source")}
                  onDrop={(event) => handleWorkloadDrop(event, "source")}
                >
                  <span>工作量表格</span>
                  <input
                    accept=".xlsx"
                    ref={workloadFileInputRef}
                    type="file"
                    onChange={handleWorkloadFileChange}
                  />
                  <button className="ghost-button" type="button" onClick={() => workloadFileInputRef.current?.click()}>
                    <FileSpreadsheet size={18} />
                    {workloadFile ? workloadFile.name : "选择工作量表格"}
                  </button>
                  <small>可拖入 .xlsx 工作量表格</small>
                </div>
              </div>

              <div className="workload-control-stack">
                <div className="experience-field-row workload-field-row" data-ui-key="workload-field-row" style={uiStyle("workload-field-row")}>
                  <span className="experience-field-label">抓取字段</span>
                  {WORKLOAD_CAPTURE_FIELD_OPTIONS.map((field) => (
                    <label className="mapping-check-field" data-ui-key="check-field" style={uiStyle("check-field")} key={field}>
                      <input
                        checked={selectedWorkloadFields.includes(field)}
                        type="checkbox"
                        onChange={(event) => toggleWorkloadField(field, event.target.checked)}
                      />
                      <span>{workloadFieldLabel(field)}</span>
                    </label>
                  ))}
                </div>

                <div className="experience-field-row workload-field-row workload-mode-row" data-ui-key="workload-field-row" style={uiStyle("workload-field-row")}>
                  <span className="experience-field-label">写入模式</span>
                  <label className="mapping-check-field" data-ui-key="check-field" style={uiStyle("check-field")}>
                    <input
                      checked={workloadWriteMode === "conservative"}
                      name="workload-write-mode"
                      type="radio"
                      onChange={() => setWorkloadWriteMode("conservative")}
                    />
                    <span>保守模式：已有值不覆盖</span>
                  </label>
                  <label className="mapping-check-field" data-ui-key="check-field" style={uiStyle("check-field")}>
                    <input
                      checked={workloadWriteMode === "overwrite"}
                      name="workload-write-mode"
                      type="radio"
                      onChange={() => setWorkloadWriteMode("overwrite")}
                    />
                    <span>覆盖模式：匹配成功即写入</span>
                  </label>
                </div>
              </div>
            </div>

            {(workloadFile || result) && (
              <div className={`mapping-panel experience-mapping-panel ${isWorkloadMappingOpen ? "is-open" : ""}`} data-ui-key="workload-mapping-panel" style={uiStyle("workload-mapping-panel")}>
                <button
                  className="mapping-toggle"
                  type="button"
                  aria-expanded={isWorkloadMappingOpen}
                  onClick={() => {
                    setIsWorkloadMappingOpen((current) => !current);
                    if (!isWorkloadMappingOpen && result && workloadTargetConfigs.length === 0) {
                      void inspectCurrentWorkloadTarget(result.job_id);
                    }
                  }}
                >
                  <span className="mapping-title">
                    <Columns3 size={18} />
                    <span>
                      <strong>工作量抓取列选择窗口</strong>
                      <small>工作量表和当前预览控制价表分别选择 sheet、映射行和字段列。</small>
                    </span>
                  </span>
                  <ChevronDown className="mapping-chevron" size={18} />
                </button>
                {isWorkloadMappingOpen && (
                  <div className="mapping-body workload-mapping-body">
                    {renderWorkloadMappingPanel("source")}
                    {renderWorkloadMappingPanel("target")}
                  </div>
                )}
              </div>
            )}

            <div className="workload-actions">
              <button
                className="primary-button"
                disabled={!workloadFile || !result || isRunningWorkloadCapture}
                type="button"
                onClick={runWorkloadCapture}
              >
                {isRunningWorkloadCapture ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />}
                {isRunningWorkloadCapture ? "正在抓取" : "开始抓取工作量"}
              </button>
            </div>

            {isRunningWorkloadCapture && (
              <div className="experience-result workload-result" data-ui-key="result-card" style={uiStyle("result-card")}>
                <Loader2 className="spin" size={18} />
                <div>
                  <strong>工作量抓取进行中 · {Math.round(workloadProgressPercent)}%</strong>
                  <span>{workloadProgressText}</span>
                  <div className="meter" aria-label={`工作量抓取进度 ${Math.round(workloadProgressPercent)}%`}>
                    <div className="meter-track">
                      <div className="meter-fill" style={{ width: `${workloadProgressPercent}%` }} />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {workloadCaptureResult && (
              <div className="experience-result workload-result" data-ui-key="result-card" style={uiStyle("result-card")}>
                <CheckCircle2 size={18} />
                <div>
                  <strong>
                    已填写 {workloadCaptureResult.summary.filled_rows} 行 · 覆盖 {workloadCaptureResult.summary.overwritten_rows ?? 0} 行 · 预警 {workloadCaptureResult.summary.warning_rows} 行
                  </strong>
                  <span>
                    工作量源行 {workloadCaptureResult.summary.source_rows} · 控制价目标行 {workloadCaptureResult.summary.target_rows} ·
                    保守跳过 {workloadCaptureResult.summary.skipped_existing_rows ?? 0} · 一对多预警 {workloadCaptureResult.summary.duplicate_warning_rows}
                  </span>
                  <div className="download-row compact" data-ui-key="download-row" style={uiStyle("download-row")}>
                    {workloadCaptureResult.downloads?.workload && (
                    <a className="download-button secondary" href={`${API_BASE}${workloadCaptureResult.downloads.workload}`}>
                      <Download size={16} />
                      下载标注工作量表
                    </a>
                    )}
                    <button
                      className="download-button"
                      type="button"
                      onClick={() => {
                        setWorkloadPreviewCountdown(null);
                        setActiveDaweibaModule("preview");
                      }}
                    >
                      <PanelTop size={16} />
                      {workloadPreviewCountdown !== null
                        ? `查看表格预览（${workloadPreviewCountdown}秒）`
                        : "查看表格预览"}
                    </button>
                  </div>
                  {visibleWorkloadIssueLogs.length > 0 && (
                    <div className="workload-log-preview">
                      {visibleWorkloadIssueLogs.map((item) => (
                        <span
                          className={`tone-${workloadLogPreviewTone(item.message)}`}
                          key={`${item.sheet_name}-${item.excel_row}`}
                        >
                          {item.sheet_name} 第 {item.excel_row} 行：{item.message}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="daweiba-report-module" id="daweiba-output" aria-label="报告生成和预览">
          <div className="daweiba-module-surface">
            {result ? (
              <div className="daweiba-report-workspace">
                <div className="daweiba-report-toolbar">
                  <div className="daweiba-report-heading">
                    <span className="daweiba-report-heading-icon"><FileText size={16} /></span>
                    <div className="daweiba-report-heading-line">
                      <h2>当前报告</h2>
                      <span className={`daweiba-report-state is-${isBatchMatchPending ? "pending" : reportPreviewStatus}`}>
                        <i aria-hidden="true" />
                        {isBatchMatchPending
                          ? "尚未生成"
                          : reportPreviewStatus === "loading"
                            ? reportPreviewUpdateMessage ? "报告更新中" : "正在读取"
                            : reportPreviewStatus === "ready"
                              ? "预览已就绪"
                              : reportPreviewStatus === "error"
                                ? "预览失败 · 可下载"
                                : "报告已生成"}
                      </span>
                    </div>
                  </div>
                  <div className="daweiba-report-toolbar-actions download-row compact" data-ui-key="download-row" style={uiStyle("download-row")}>
                    <a
                      className={`download-button ${!canDownloadOutputs ? "is-disabled" : ""}`}
                      href={canDownloadOutputs ? excelDownloadHref : "#"}
                      aria-disabled={!canDownloadOutputs}
                      tabIndex={canDownloadOutputs ? 0 : -1}
                      aria-label="下载当前报告 Excel"
                      onClick={(event) => { if (!canDownloadOutputs) event.preventDefault(); }}
                    >
                      <Download size={16} />
                      Excel
                    </a>
                    <a
                      className={`download-button secondary ${!reportDownloadHref ? "is-disabled" : ""}`}
                      href={reportDownloadHref || "#"}
                      aria-disabled={!reportDownloadHref}
                      tabIndex={reportDownloadHref ? 0 : -1}
                      aria-label="下载当前 Word 报告"
                      onClick={(event) => { if (!reportDownloadHref) event.preventDefault(); }}
                    >
                      <Download size={16} />
                      Word
                    </a>
                    <button
                      className="download-button secondary"
                      type="button"
                      disabled={!hasCurrentReport || reportPreviewStatus === "loading"}
                      aria-label="刷新当前真实 Word 报告预览"
                      onClick={refreshCurrentReportPreview}
                    >
                      {reportPreviewStatus === "loading" ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
                      刷新
                    </button>
                    <button className="download-button secondary" type="button" disabled={isRiskSummaryLoading || isBatchMatchPending} aria-label="查看当前报告风险清单" onClick={loadRiskSummary}>
                      {isRiskSummaryLoading ? <Loader2 className="spin" size={16} /> : <ShieldCheck size={16} />}
                      风险清单
                    </button>
                  </div>
                  <div className="daweiba-report-meta" aria-label="当前报告摘要">
                    <span className="daweiba-report-file" title={result.summary.output_report || result.summary.report_text}>
                      <FileText size={13} />
                      <span>{result.summary.output_report || result.summary.report_text}</span>
                    </span>
                    <span><b>{result.summary.total_data_rows}</b> 输入行</span>
                    <span><b>{result.summary.filled_rows}</b> 已填价</span>
                    <span className={result.summary.review_rows ? "is-warn" : ""}><b>{result.summary.review_rows}</b> 待复核</span>
                    <span><b>{warningSummary?.executed ? warningSummary.warning_rows : "未运行"}</b> 预警</span>
                  </div>
                </div>

                {result.needs_recalculate && (
                  <div className="daweiba-report-sync-notice" role="status">
                    <AlertTriangle size={16} />
                    <span>人工修改已保存，但尚未点击“重算公式”；当前 Word 报告可能还未同步最新金额。</span>
                    <button type="button" disabled={isRecalculatingPreview} onClick={recalculatePreviewWorkbook}>
                      {isRecalculatingPreview ? <Loader2 className="spin" size={15} /> : <RefreshCw size={15} />}
                      重算并更新报告
                    </button>
                  </div>
                )}

                {riskSummary && (
                  <details className="daweiba-report-risk-panel" open>
                    <summary>结构化风险清单 · {riskSummary.summary.total} 项</summary>
                    <div className="risk-card-list">
                      {riskSummary.items.slice(0, 6).map((item) => (
                        <button
                          className={`risk-card severity-${item.severity}`}
                          type="button"
                          key={item.id}
                          onClick={() => {
                            if (item.sheet_name && item.excel_row) {
                              jumpToWarningPreview({
                                sheet_name: item.sheet_name,
                                excel_row: Number(item.excel_row),
                                metric: item.metric || "",
                                current_value: 0,
                                experience_values: [],
                                experience_min: 0,
                                experience_max: 0,
                                sample_count: 0,
                                severity: item.severity,
                                message: item.message,
                                source_rows: [],
                              });
                            }
                          }}
                        >
                          <span>{item.severity_label ?? item.severity} · {item.risk_type}</span>
                          <b>{item.title}</b>
                          <small>{item.message}</small>
                        </button>
                      ))}
                    </div>
                  </details>
                )}

                <div className="daweiba-report-preview">
                  <div className="daweiba-report-preview-head">
                    <div>
                      <span className={`daweiba-report-preview-dot is-${reportPreviewStatus}`} aria-hidden="true" />
                      <strong>文档预览</strong>
                    </div>
                    <span>{result.summary.output_report || "等待报告生成"}</span>
                  </div>
                  {activeDaweibaModule === "report" && (
                    <WordReportPreview
                      enabled
                      isAvailable={hasCurrentReport}
                      jobId={result.job_id}
                      reportUrl={reportDownloadHref}
                      reportFilename={result.summary.output_report}
                      revisionKey={reportPreviewRevision}
                      updateMessage={reportPreviewUpdateMessage}
                      unavailableMessage={isBatchMatchPending
                        ? "当前只是待批量匹配预览。请先执行“批量匹配”，完成后系统会生成真实 Word 报告。"
                        : "当前任务尚无可读取的 Word 报告，请返回结果预览重算或重新生成。"}
                      downloadUrl={reportDownloadHref}
                      onReturnToPreview={() => setActiveDaweibaModule("preview")}
                      onStatusChange={setReportPreviewStatus}
                    />
                  )}
                  <p className="daweiba-report-preview-note">网页预览用于快速核对，正式排版以下载后的 Word 文件为准。</p>
                </div>
              </div>
            ) : (
              <div className="daweiba-module-empty">
                <FileText size={34} />
                <p>完成批量匹配后，这里会读取当前任务实际生成的 DOCX，并保留 Excel / Word 下载与失败兜底。</p>
                <button className="primary-button" type="button" onClick={() => setActiveDaweibaModule("fill")}>
                  返回填价工作台
                </button>
              </div>
            )}
          </div>
        </section>

        <section className="daweiba-knowledge-module" aria-label="知识库问答状态">
          <div className="daweiba-module-surface">
            <div className="daweiba-module-head">
              <span><Database size={18} /></span>
              <div>
                <p>知识库问答</p>
                <h2>知识库状态</h2>
              </div>
            </div>
            <div className="daweiba-knowledge-grid">
              <div className="daweiba-knowledge-card is-primary">
                <Database size={26} />
                <div>
                  <strong>本地证据检索可用</strong>
                  <span>查库问题会优先检索标准资料、项目规则和规则卡片；有证据时再交给智算解释。</span>
                </div>
              </div>
              <div className="daweiba-knowledge-card">
                <ShieldCheck size={24} />
                <div>
                  <strong>价格裁决边界</strong>
                  <span>知识库问答只解释依据，不反向修改基价、单价和两个调整系数。</span>
                </div>
              </div>
              <div className="daweiba-knowledge-card">
                <MessageSquareText size={24} />
                <div>
                  <strong>强制查库入口</strong>
                  <span>{FORCE_KNOWLEDGE_PREFIXES.join(" / ")}</span>
                </div>
              </div>
              <div className="daweiba-knowledge-card">
                <Bot size={24} />
                <div>
                  <strong>随行助手联动</strong>
                  <span>点击下方按钮会展开右侧智算，并预置“@知识库：”问题前缀。</span>
                </div>
              </div>
            </div>
            <div className="daweiba-knowledge-actions">
              <button className="primary-button" type="button" onClick={openDaweibaKnowledge}>
                <MessageSquareText size={18} />
                打开问问智算
              </button>
              <button className="ghost-button" type="button" onClick={() => setActiveDaweibaModule("preview")}>
                <FileSpreadsheet size={18} />
                查看表格结果
              </button>
            </div>
          </div>
        </section>

        <section className="daweiba-collaboration-module" aria-label="智能协同飞书机器人">
          <div className="daweiba-collaboration-head">
            <div className="daweiba-module-head">
              <span><Send size={18} /></span>
              <div>
                <p>智能协同</p>
                <h2>飞书机器人 · 两层协同</h2>
              </div>
            </div>
            <p>第一层负责主动通知；第二层从群聊接收 Excel，按单任务队列自动完成匹配、风险识别和成果回传。</p>
          </div>

          <div className="daweiba-collaboration-status" aria-label="飞书连接状态">
            <span className={`daweiba-collaboration-badge ${feishuWebhookStatus.enabled ? "is-success" : feishuWebhookStatus.configured ? "is-idle" : "is-muted"}`}>
              连接 · {feishuConnectionLabel}
            </span>
            <span className={`daweiba-collaboration-badge ${feishuWebhookStatus.security_enabled ? "is-success" : "is-warning"}`}>
              签名 · {feishuWebhookStatus.security_enabled ? "已配置" : "未配置"}
            </span>
            <span className={`daweiba-collaboration-badge ${latestFeishuDelivery?.success ? "is-success" : latestFeishuDelivery ? "is-error" : "is-muted"}`}>
              最近发送 · {latestFeishuDelivery ? latestFeishuDelivery.success ? "成功" : "失败" : "暂无记录"}
            </span>
            <div className="daweiba-collaboration-status-actions">
              <button className="ghost-button" type="button" onClick={openFeishuBotConsole}>
                <MonitorUp size={15} />
                运行控制台
              </button>
              <button className="ghost-button" type="button" disabled={isLoadingFeishuWebhook} onClick={() => void loadFeishuWebhookData()}>
                <RefreshCw size={15} className={isLoadingFeishuWebhook ? "spin" : ""} />
                刷新
              </button>
            </div>
          </div>

          <div className="daweiba-collaboration-body">
            <section className="daweiba-collaboration-settings" aria-label="第二层企业应用机器人状态">
              <div className="daweiba-collaboration-section-title">
                <div><h3>第二层 · 企业应用长连接机器人</h3><p>群聊先 @机器人再发送 .xlsx；单聊可直接发送。群聊 @机器人或单聊后输入“@知识库：问题”，会自动查询本地知识库。服务器与本机只能选择一个实例启用。</p></div>
                <div className="daweiba-collaboration-title-actions">
                  {feishuAppBotStatus?.profiles?.length ? <label className="daweiba-collaboration-bot-picker">
                    <span>机器人</span>
                    <select
                      value={feishuAppBotStatus.active_profile}
                      disabled={isTogglingFeishuAppBot}
                      onChange={(event) => void selectFeishuAppBotProfile(event.target.value)}
                    >
                      {feishuAppBotStatus.profiles.map((profile) => <option key={profile.profile_id} value={profile.profile_id}>{profile.label}</option>)}
                    </select>
                  </label> : null}
                  <label className="daweiba-collaboration-switch">
                    <input type="checkbox" checked={Boolean(feishuAppBotStatus?.enabled)} disabled={isTogglingFeishuAppBot || !feishuAppBotStatus?.configured} onChange={(event) => void toggleFeishuAppBot(event.target.checked)} />
                    <span>启用接收</span>
                  </label>
                  <span className={`daweiba-collaboration-badge ${feishuAppBotStatus?.enabled && feishuAppBotStatus.running ? "is-success" : feishuAppBotStatus?.enabled ? "is-warning" : "is-muted"}`}>
                    {!feishuAppBotStatus?.configured ? "凭证未配置" : feishuAppBotStatus.enabled ? feishuAppBotStatus.running ? "运行中" : isTogglingFeishuAppBot ? "正在启动" : "启用但未运行" : "已关闭"}
                  </span>
                </div>
              </div>
              <div className="daweiba-feishu-app-metrics"><span><strong>{feishuAppBotStatus?.concurrency ?? 1}</strong>并发任务</span><span><strong>{feishuAppBotStatus?.counts?.queued ?? 0}</strong>等待中</span><span><strong>{feishuAppBotStatus?.counts?.completed ?? 0}</strong>已完成</span><span><strong>{feishuAppBotStatus?.retention_days ?? 30}</strong>天留存</span></div>
              {feishuAppBotStatus?.current_task && <p className="daweiba-collaboration-feedback">正在处理：{feishuAppBotStatus.current_task.task_id} · {feishuAppBotStatus.current_task.file_name} · {feishuAppBotStatus.current_task.stage}</p>}
              {feishuAppBotStatus?.recent_tasks?.length ? <div className="daweiba-collaboration-history-table" role="table"><div className="is-header" role="row"><span>任务</span><span>文件</span><span>状态</span><span>风险</span></div>{feishuAppBotStatus.recent_tasks.slice(0, 8).map((task) => <div role="row" key={task.task_id}><span title={task.task_id}>{task.task_id}</span><span title={task.file_name}>{task.file_name}</span><span>{task.status}</span><span>{task.risk_total ?? 0} 项 / 高 {task.risk_high ?? 0}</span></div>)}</div> : <p className="daweiba-collaboration-empty">暂无第二层任务。应用凭证只保存在本机运行目录，不会回显到前端。</p>}
            </section>

            <section className="daweiba-collaboration-settings" aria-label="Webhook 设置">
              <div className="daweiba-collaboration-section-title">
                <div>
                  <h3>第一层：Webhook</h3>
                  <p>凭证只保存在后端运行目录，保存后不会再次回显完整值。</p>
                </div>
                <div className="daweiba-collaboration-title-actions">
                  {feishuWebhookStatus.profiles.length > 0 && (
                    <label className="daweiba-collaboration-bot-picker">
                      <span>Webhook</span>
                      <select
                        value={feishuWebhookStatus.active_profile}
                        disabled={isSavingFeishuWebhook}
                        onChange={(event) => void selectFeishuWebhookProfile(event.target.value)}
                      >
                        {feishuWebhookStatus.profiles.map((profile) => (
                          <option key={profile.profile_id} value={profile.profile_id}>
                            {profile.label}{profile.host ? ` · ${profile.host}` : ""}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <label className="daweiba-collaboration-switch">
                    <input
                      type="checkbox"
                      checked={feishuEnabledDraft}
                      disabled={isSavingFeishuWebhook}
                      onChange={(event) => void toggleFeishuWebhook(event.target.checked)}
                    />
                    <span>启用通知</span>
                  </label>
                </div>
              </div>

              <div className="daweiba-collaboration-form-grid">
                <label>
                  <span>飞书群机器人 Webhook 地址</span>
                  <input
                    type="password"
                    autoComplete="off"
                    value={feishuWebhookDraft}
                    placeholder={feishuWebhookStatus.configured ? "已安全保存；留空表示保留原地址" : "https://open.feishu.cn/open-apis/bot/v2/hook/..."}
                    onChange={(event) => setFeishuWebhookDraft(event.target.value)}
                  />
                </label>
                <label>
                  <span>签名密钥</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={feishuSecretDraft}
                    placeholder={feishuWebhookStatus.security_enabled ? "已安全保存；留空表示保留原密钥" : "建议在飞书端启用签名校验后填写"}
                    onChange={(event) => setFeishuSecretDraft(event.target.value)}
                  />
                </label>
                <label className="is-wide">
                  <span>进入造价智算 URL（可选）</span>
                  <input
                    type="url"
                    value={feishuAppUrlDraft}
                    placeholder="例如：http://127.0.0.1:5174/"
                    onChange={(event) => setFeishuAppUrlDraft(event.target.value)}
                  />
                  <small>仅用于完成卡片的跳转按钮，不接收卡片回调，也不会直接修改业务数据。</small>
                </label>
              </div>

              <div className="daweiba-collaboration-actions">
                <button className="primary-button" type="button" disabled={isSavingFeishuWebhook} onClick={() => void saveFeishuWebhookSettings()}>
                  {isSavingFeishuWebhook ? <Loader2 size={16} className="spin" /> : <ShieldCheck size={16} />}
                  保存设置
                </button>
                <button
                  className="ghost-button"
                  type="button"
                  disabled={isTestingFeishuWebhook || !feishuWebhookStatus.configured || !feishuWebhookStatus.enabled}
                  onClick={() => void testFeishuWebhookConnection()}
                >
                  {isTestingFeishuWebhook ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
                  发送测试消息
                </button>
                <button className="ghost-button is-danger" type="button" disabled={isSavingFeishuWebhook || !feishuWebhookStatus.configured} onClick={() => void clearFeishuWebhookSettings()}>
                  清空当前配置
                </button>
              </div>
              {feishuWebhookFeedback && <p className="daweiba-collaboration-feedback">{feishuWebhookFeedback}</p>}
              <p className="daweiba-collaboration-security-note">
                <ShieldCheck size={16} />
                推荐在飞书端启用签名校验；自定义关键词和 IP 白名单由飞书端配置，本页面不伪造其启用状态。
              </p>
            </section>

            <section className="daweiba-collaboration-rules" aria-label="通知规则">
              <div className="daweiba-collaboration-section-title">
                <div>
                  <h3>通知规则</h3>
                  <p>关闭任一类型后，该类事件不会发起飞书网络请求。</p>
                </div>
              </div>
              <div className="daweiba-collaboration-rule-list">
                {(
                  [
                    ["task_started", "任务开始", "读取输入或开始批量匹配时通知"],
                    ["progress", "任务进度", "待匹配预览生成等关键阶段通知"],
                    ["task_completed", "任务完成", "使用后端返回的处理行数、命中数和待复核数生成摘要"],
                    ["task_failed", "任务失败", "发送脱敏错误摘要，不改变原业务失败结论"],
                  ] as Array<[FeishuNotificationType, string, string]>
                ).map(([id, label, description]) => (
                  <label className="daweiba-collaboration-rule" key={id}>
                    <span>
                      <strong>{label}</strong>
                      <small>{description}</small>
                    </span>
                    <input
                      type="checkbox"
                      checked={feishuNotificationDraft[id]}
                      onChange={(event) => setFeishuNotificationDraft((current) => ({ ...current, [id]: event.target.checked }))}
                    />
                  </label>
                ))}
              </div>
            </section>

            <section className="daweiba-collaboration-history" aria-label="最近发送记录">
              <div className="daweiba-collaboration-section-title">
                <div>
                  <h3>最近发送记录</h3>
                  <p>仅显示时间、通知类型、结果、状态码和脱敏错误。</p>
                </div>
              </div>
              {feishuWebhookHistory.length ? (
                <div className="daweiba-collaboration-history-table" role="table">
                  <div className="is-header" role="row">
                    <span>时间</span><span>类型</span><span>结果</span><span>状态</span>
                  </div>
                  {feishuWebhookHistory.map((item, index) => (
                    <div role="row" key={`${item.timestamp}-${item.notification_type}-${index}`}>
                      <span>{new Date(item.timestamp).toLocaleString("zh-CN", { hour12: false })}</span>
                      <span>{FEISHU_NOTIFICATION_LABELS[item.notification_type] ?? item.notification_type}</span>
                      <span className={item.success ? "is-success" : "is-error"}>{item.success ? "成功" : "失败"}</span>
                      <span title={item.error || ""}>{item.error || (item.business_code ?? item.http_status ?? "-")}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="daweiba-collaboration-empty">暂无发送记录。配置并启用后，可先发送一条明确标记为测试的消息。</p>
              )}
            </section>
          </div>

          <div className="daweiba-collaboration-boundary">
            <AlertTriangle size={17} />
            <p><strong>当前边界：</strong>第二层支持群聊收取单个 .xlsx、自动处理和成果回传；暂不包含审批、多维表格、风险派单、用户角色权限、多文件任务和群内逐行改值。</p>
          </div>
        </section>

        <section className="daweiba-digital-project-assistant-module" aria-label="数字化项目助手">
          <div className="daweiba-digital-project-assistant-frame">
            {digitalProjectAssistantFrameStatus !== "ready" && (
              <div className={`daweiba-digital-project-assistant-state is-${digitalProjectAssistantFrameStatus}`}>
                {digitalProjectAssistantFrameStatus === "loading" ? <Loader2 className="spin" size={24} /> : <AlertTriangle size={24} />}
                <div>
                  <strong>{digitalProjectAssistantFrameStatus === "loading" ? "正在加载数字化项目助手" : "数字化项目助手服务可能未启动"}</strong>
                  <span>{digitalProjectAssistantFrameStatus === "loading" ? "正在连接独立服务，请稍候。" : "请确认独立前端服务已启动，然后重试或在新窗口打开。"}</span>
                </div>
                {digitalProjectAssistantFrameStatus === "timeout" && (
                  <div className="daweiba-digital-project-assistant-actions">
                    <button
                      className="primary-button"
                      type="button"
                      onClick={() => {
                        setDigitalProjectAssistantFrameStatus("loading");
                        setDigitalProjectAssistantFrameKey((current) => current + 1);
                      }}
                    >
                      <RefreshCw size={16} />
                      重试
                    </button>
                    <a className="ghost-button" href={DIGITAL_PROJECT_ASSISTANT_URL} target="_blank" rel="noreferrer">
                      <ExternalLink size={16} />
                      新窗口打开
                    </a>
                  </div>
                )}
              </div>
            )}
            <iframe
              key={digitalProjectAssistantFrameKey}
              className={digitalProjectAssistantFrameStatus === "ready" ? "is-ready" : ""}
              src={DIGITAL_PROJECT_ASSISTANT_URL}
              title="数字化项目助手"
              onLoad={() => setDigitalProjectAssistantFrameStatus("ready")}
            />
          </div>
        </section>
      </section>
        </div>

        <aside className={`ai-dock zhisuan-style-${zhisuanDockStyle} ${isAiDockCollapsed ? "is-collapsed" : ""}`} id="ai-dock" data-ui-key="ai-dock" style={uiStyle("ai-dock")} aria-label="智算助手">
          {isAiDockCollapsed ? (
            <button className="ai-dock-rail" type="button" aria-label="展开智算" title="展开智算" onClick={() => setIsAiDockCollapsed(false)}>
              <ZhisuanAvatar className="ai-dock-rail-avatar" state={zhisuanAvatarState} size="normal" />
              <span className="ai-dock-rail-label" data-ui-text-key="ai.title">{uiText("ai.title", "智算")}</span>
            </button>
          ) : (
            <section className="llm-section ai-dock-panel">
              <div className="ai-dock-head">
                <div className="ai-dock-title">
                  <span className="ai-dock-avatar-frame">
                    <ZhisuanAvatar className="ai-dock-avatar" state={zhisuanAvatarState} size="normal" />
                  </span>
                  <div>
                    <p>随行助手 · {zhisuanAvatarLabel}</p>
                    <h2>智算</h2>
                  </div>
                </div>
                <div className="ai-dock-actions">
                  <button className="icon-button" type="button" aria-label="大模型设置" onClick={() => setIsLlmSettingsOpen(true)}>
                    <Settings size={18} />
                  </button>
                  <button className="ai-collapse-button" type="button" onClick={() => setIsAiDockCollapsed(true)}>
                    收起
                  </button>
                </div>
              </div>

              <div className={`chat-window ${isChatOpen ? "is-open" : ""}`}>
                <button className="llm-window-toggle" type="button" onClick={() => setIsChatOpen((current) => !current)}>
                  <span>
                    <MessageSquareText size={18} />
                    问问智算
                  </span>
                  <ChevronDown className="mapping-chevron" size={16} />
                </button>
                {isChatOpen && (
                  <>
                    <div className="chat-log" ref={chatLogRef} style={{ height: zhisuanChatHeight }}>
                      {chatMessages.length === 0 ? (
                        <div className="chat-empty">
                          <Bot size={22} />
                          <span>{zhisuanWelcomeMessage}</span>
                        </div>
                      ) : (
                        chatMessages.map((message, index) => (
                          <div
                            className={`chat-message ${message.role} ${message.source ? `source-${message.source}` : ""} ${message.isTyping ? "is-typing" : ""}`}
                            key={message.id ?? `${message.role}-${index}`}
                            onClick={() => {
                              if (message.role === "assistant" && message.isTyping) {
                                revealZhisuanMessage(message.id);
                              }
                            }}
                            title={message.role === "assistant" && message.isTyping ? "点击立即显示全部" : undefined}
                          >
                            <span className="chat-message-speaker">{message.role === "user" ? "U" : "Z"}</span>
                            <div className="chat-message-body">
                              {renderZhisuanMessageText(message.role === "assistant" ? (message.displayContent ?? message.content) : message.content)}
                              {message.role === "assistant" && message.isTyping && <i className="typing-caret" />}
                              {message.role === "assistant" && !message.isTyping && message.rowDetailContext && (
                                <div className="zhisuan-message-actions">
                                  <button
                                    className="zhisuan-action-button"
                                    type="button"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      openRowAiDetail(message.rowDetailContext);
                                    }}
                                  >
                                    <BookOpen size={14} />
                                    详细情况
                                  </button>
                                </div>
                              )}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                    <div className={`quick-command-drawer ${zhisuanQuickSettings.autoHide ? "is-auto-hide" : "is-pinned"}`} aria-label="智算快捷指令">
                      <button className="quick-command-handle" type="button">
                        快捷指令
                        <ChevronDown size={14} />
                      </button>
                      <div className="quick-command-row">
                        {visibleZhisuanQuickItems.map((command) => (
                          <button
                            key={command.id}
                            type="button"
                            disabled={isChatting || isRunningWarnings || isGeneratingRisk}
                            onClick={() => void runZhisuanQuickItem(command)}
                          >
                            {command.label}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="chat-compose">
                      <textarea
                        ref={chatInputRef}
                        value={chatInput}
                        rows={3}
                        placeholder="输入一句问题"
                        onChange={(event) => setChatInput(event.target.value)}
                        onFocus={() => setIsChatInputFocused(true)}
                        onBlur={() => setIsChatInputFocused(false)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" && !event.altKey) {
                            event.preventDefault();
                            sendChatMessage();
                          }
                        }}
                      />
                      <div className="chat-compose-footer">
                        <span>Enter 发送 · Alt+Enter 换行</span>
                        <button className="chat-send-button" disabled={isChatting} type="button" onClick={sendChatMessage}>
                          {isChatting ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
                          {isChatting ? "发送中" : "发送"}
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>

              {zhisuanDockVisibility.rowReview && rowAiContext && (
                <div className="ai-row-current">
                  <div className="ai-row-current-head">
                    <div>
                      <span>
                        <Bot size={16} />
                        行级AI复核
                      </span>
                      <strong>{rowAiContext.sheetName} · 第 {rowAiContext.rowNumber} 行</strong>
                    </div>
                    <button type="button" onClick={() => setRowAiContext(null)}>
                      关闭
                    </button>
                  </div>
                  <div className="row-ai-context">
                    {Object.entries(rowAiContext.values)
                      .filter(([, value]) => value)
                      .slice(0, 6)
                      .map(([key, value]) => (
                        <span key={key}>
                          {key}：{value}
                        </span>
                      ))}
                  </div>
                  <div className="row-ai-compose">
                    <textarea
                      rows={3}
                      value={rowAiQuestion}
                      onChange={(event) => setRowAiQuestion(event.target.value)}
                    />
                    <button className="chat-send-button row-ai-send-button" disabled={isRowAiLoading} type="button" onClick={() => askRowAi()}>
                      {isRowAiLoading ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
                      {isRowAiLoading ? "分析中" : "复核"}
                    </button>
                  </div>
                  <div className="row-ai-answer">
                    {isRowAiLoading ? (
                      <span>正在结合本行要素、三个数字和匹配说明生成复核意见...</span>
                    ) : rowAiAnswer ? (
                      <p>{rowAiAnswer}</p>
                    ) : (
                      <span>点击表格末列 AI 按钮后，会先把问题填入上方“问问智算”；也可以在这里单独复核。</span>
                    )}
                  </div>
                </div>
              )}

              {showZhisuanStatusGrid && (
                <div className="ai-dock-status-grid" data-ui-key="ai-status-grid" style={uiStyle("ai-status-grid")}>
                  {zhisuanDockVisibility.conclusion && (
                    <div className="ai-status-card">
                      <span>本次结论</span>
                      <strong>{result ? `${result.summary.filled_rows}/${result.summary.total_data_rows}` : "待转换"}</strong>
                      <small>{result ? result.summary.report_text : "上传 Excel 后生成结构化结论"}</small>
                    </div>
                  )}
                  {zhisuanDockVisibility.review && (
                    <div className="ai-status-card">
                      <span>待复核</span>
                      <strong>{result ? result.summary.review_rows : "--"}</strong>
                      <small>AI 只解释复核原因，不改最终价格</small>
                    </div>
                  )}
                  {zhisuanDockVisibility.warning && (
                    <div className="ai-status-card">
                      <span>预警</span>
                      <strong>{warningSummary?.executed ? warningSummary.warning_rows : "未运行"}</strong>
                      <small>{warningSummary?.executed ? "可继续追问预警细节" : "运行经验池预警后显示"}</small>
                    </div>
                  )}
                </div>
              )}

              {zhisuanDockVisibility.ruleNotice && (
                <div className="llm-panel" data-ui-key="llm-panel" style={uiStyle("llm-panel")}>
                  <div className="llm-summary">
                    <Bot size={24} />
                    <div>
                      <strong>智算只做解释与提示</strong>
                      <span>风险报告、导出、预警和行级追问都可以从上方“问问智算”触发；价格裁决仍由结构化规则完成。</span>
                    </div>
                  </div>
                </div>
              )}

              {zhisuanDockVisibility.debugInfo && (
                <div className={`llm-debug-window ${isLlmDebugOpen ? "is-open" : ""}`}>
                  <button
                    className="llm-window-toggle"
                    type="button"
                    onClick={() => setIsLlmDebugOpen((current) => !current)}
                  >
                    <span>
                      <Settings size={15} />
                      调试信息：最近 10 次发送给大模型的内容
                    </span>
                    <ChevronDown className="mapping-chevron" size={16} />
                  </button>
                  {isLlmDebugOpen && (
                    <pre>
                      {llmDebugHistory.length > 0
                        ? JSON.stringify(llmDebugHistory, null, 2)
                        : "尚未发送大模型请求。输出风险报告、行级 AI 复核或发送问答后，这里会显示最近 10 条不含 API Key 的请求信息，并包含可打开的 prompt_markdown 路径。"}
                    </pre>
                  )}
                </div>
              )}

            </section>
          )}
        </aside>
      </div>

      {isFeishuBotConsoleOpen && (
        <div className="modal-backdrop daweiba-bot-console-backdrop" role="presentation" onClick={() => setIsFeishuBotConsoleOpen(false)}>
          <div className="settings-modal daweiba-bot-console-modal" role="dialog" aria-modal="true" aria-labelledby="feishu-bot-console-title" onClick={(event) => event.stopPropagation()}>
            <div className="daweiba-bot-console-modal-head">
              <div>
                <p>智能协同 · 第二层机器人</p>
                <h2 id="feishu-bot-console-title">机器人运行控制台</h2>
                <small>查看长连接、消息接收和任务处理情况；消息日志包含发送人、会话和正文。</small>
              </div>
              <div className="daweiba-bot-console-modal-actions">
                <label className="daweiba-collaboration-switch">
                  <input type="checkbox" checked={isFeishuBotConsoleLive} onChange={(event) => setIsFeishuBotConsoleLive(event.target.checked)} />
                  <span>实时刷新</span>
                </label>
                <button className="ghost-button" type="button" disabled={isLoadingFeishuBotConsole} onClick={() => void loadFeishuBotConsole()}>
                  <RefreshCw size={15} className={isLoadingFeishuBotConsole ? "spin" : ""} />
                  刷新日志
                </button>
                <button className="ghost-button" type="button" onClick={() => setIsFeishuBotConsoleOpen(false)} autoFocus>
                  关闭
                </button>
              </div>
            </div>
            <div className="daweiba-bot-console-summary">
              <span className={feishuAppBotStatus?.enabled && feishuAppBotStatus.running ? "is-online" : "is-offline"}>
                <i />{feishuAppBotStatus?.enabled && feishuAppBotStatus.running ? "长连接进程运行中" : feishuAppBotStatus?.enabled ? "已启用但未运行" : "接收已关闭"}
              </span>
              <span>当前机器人：{feishuAppBotStatus?.profiles?.find((profile) => profile.profile_id === feishuAppBotStatus.active_profile)?.label ?? "未配置"}</span>
              <span>日志：{feishuBotConsoleEvents.length} 条</span>
            </div>
            <div className="daweiba-bot-console" role="log" aria-label="机器人业务运行日志" ref={feishuBotConsoleRef}>
              {feishuBotConsoleEvents.length ? feishuBotConsoleEvents.map((item, index) => (
                <div className={`daweiba-bot-console-line is-${item.level}`} key={`${item.timestamp}-${item.source ?? "log"}-${item.task_id ?? ""}-${index}`}>
                  <time title={item.timestamp}>{formatFeishuConsoleTime(item.timestamp)}</time>
                  <span className="daweiba-bot-console-category">{FEISHU_BOT_CONSOLE_CATEGORY_LABELS[item.category] ?? item.category}</span>
                  <span className="daweiba-bot-console-message">{item.message}{item.task_id ? <code>{item.task_id}</code> : null}</span>
                </div>
              )) : <p className="daweiba-bot-console-empty">暂无运行日志。启用机器人或收到消息后，这里会自动显示连接和处理过程。</p>}
            </div>
            <p className="daweiba-collaboration-security-note">
              <ShieldCheck size={16} />
              控制台会显示发送人名称与 ID、群名与会话 ID、消息正文和附件名；飞书长连接不提供发送者来源 IP。App Secret、访问令牌、连接票据、文件 Key 和完整 WebSocket 地址仍不显示。
            </p>
          </div>
        </div>
      )}

      {rowAiDetailPrompt && (
        <div className="modal-backdrop row-ai-detail-backdrop" role="presentation" onClick={() => setRowAiDetailPrompt(null)}>
          <div className="settings-modal row-ai-detail-modal" role="dialog" aria-modal="true" aria-label="行级AI复核详情" onClick={(event) => event.stopPropagation()}>
            <div className="settings-modal-head">
              <div>
                <p>行级AI复核</p>
                <h2>{rowAiDetailPrompt.sheetName} 第 {rowAiDetailPrompt.rowNumber} 行</h2>
              </div>
              <button type="button" onClick={() => setRowAiDetailPrompt(null)}>
                关闭
              </button>
            </div>
            <div className="row-ai-detail-body">
              <p>本行复核意见已生成。如需查看价格匹配信息、候选来源和当前价格依据追溯，可以打开辅助填价详情。</p>
              <div className="row-ai-detail-context">
                {Object.entries(rowAiDetailPrompt.values)
                  .filter(([, value]) => value)
                  .slice(0, 5)
                  .map(([key, value]) => (
                    <span key={key}>
                      {key}：{value}
                    </span>
                  ))}
              </div>
            </div>
            <div className="settings-modal-actions">
              <button type="button" className="secondary-button" onClick={() => setRowAiDetailPrompt(null)}>
                稍后再看
              </button>
              <button type="button" className="primary-button" onClick={() => openRowAiDetail()}>
                <BookOpen size={16} />
                详细情况
              </button>
            </div>
          </div>
        </div>
      )}

      {fillAssistDialog && (
        <div className="modal-backdrop fill-assist-backdrop" role="presentation" onClick={() => setFillAssistDialog(null)}>
          <div className="settings-modal fill-assist-modal" role="dialog" aria-modal="true" aria-label="辅助填价" onClick={(event) => event.stopPropagation()}>
            <div className="settings-modal-head">
              <div>
                <p>辅助填价</p>
                <h2>{fillAssistDialog.context.sheet_name} 第 {fillAssistDialog.context.excel_row} 行</h2>
              </div>
              <button className="icon-button" type="button" onClick={() => setFillAssistDialog(null)}>×</button>
            </div>
            <div className="fill-assist-context">
              <span>待填字段：<strong>{fillAssistDialog.context.target_header || "基价/单价"}</strong></span>
              <span>当前值：<strong>{String(fillAssistDialog.context.current_value ?? "") || "空"}</strong></span>
              {Object.entries(fillAssistDialog.context.row).map(([key, value]) => (
                <span key={key}>{key}：<strong>{String(value ?? "") || "-"}</strong></span>
              ))}
              {Object.entries(fillAssistDialog.context.diagnostics).filter(([, value]) => String(value ?? "").trim()).map(([key, value]) => (
                <span className="is-wide" key={key}>{key}：<strong>{String(value)}</strong></span>
              ))}
            </div>
            <div className="fill-assist-body">
              {fillAssistDialog.isLoading ? (
                <div className="fill-assist-loading">
                  <Loader2 className="spin" size={20} />
                  正在整理结构化候选
                </div>
              ) : (
                <>
                  {fillAssistDialog.error && (
                    <div className="notice error">
                      <AlertTriangle size={18} />
                      {fillAssistDialog.error}
                    </div>
                  )}
                  {fillAssistDialog.candidates.length > 0 ? (
                    <div className="fill-assist-candidates">
                      {fillAssistDialog.candidates.map((candidate) => (
                        <label className={`fill-assist-candidate confidence-${candidate.confidence}`} key={candidate.id}>
                          <input
                            type="radio"
                            name="fill-assist-candidate"
                            checked={fillAssistDialog.selectedCandidateId === candidate.id}
                            onChange={() => setFillAssistDialog((current) => current ? { ...current, selectedCandidateId: candidate.id } : current)}
                          />
                          <span className="fill-assist-value">{candidate.value}</span>
                          <span className={`fill-assist-source ${fillAssistSourceClass(candidate)}`}>{fillAssistSourceDisplay(candidate)}</span>
                          <span className="fill-assist-confidence">{candidate.confidence_label}</span>
                          {typeof candidate.similarity === "number" && <small>相似度 {candidate.similarity}%</small>}
                          {typeof candidate.sample_count === "number" && <small>样本 {candidate.sample_count} 条</small>}
                          <em>{candidate.reason}</em>
                          <small>{candidate.basis}</small>
                          {candidate.risk_tips?.map((tip) => <small className="fill-assist-risk" key={tip}>{tip}</small>)}
                        </label>
                      ))}
                    </div>
                  ) : (
                    <div className="warning-empty">
                      <AlertTriangle size={18} />
                      未找到结构化候选，请人工处理当前单元格。
                    </div>
                  )}
                  <section className="fill-assist-trace" aria-label="当前价格依据追溯">
                    <div className="fill-assist-section-title">
                      <span>
                        <FileText size={16} />
                        当前价格依据追溯
                      </span>
                      <small>轻量追溯</small>
                    </div>
                    {fillAssistDialog.trace.length > 0 ? (
                      <div className="fill-assist-trace-list">
                        {fillAssistDialog.trace.map((trace, index) => (
                          <article className="fill-assist-trace-card" key={`${trace.kind}-${trace.title}-${index}`}>
                            <div className="fill-assist-trace-head">
                              <span className={`fill-assist-trace-kind ${standardTraceKindClass(trace)}`}>{trace.kind}</span>
                              <strong>{trace.title}</strong>
                            </div>
                            <p>{trace.text || "当前追溯项暂无更详细说明。"}</p>
                            <small>来源：{trace.source || "暂无来源说明"}</small>
                            {trace.source_rows && trace.source_rows.length > 0 && (
                              <div className="fill-assist-trace-rows">
                                {trace.source_rows.slice(0, 3).map((sourceRow, rowIndex) => (
                                  <span key={rowIndex}>
                                    {Object.entries(sourceRow)
                                      .filter(([, value]) => String(value ?? "").trim())
                                      .map(([key, value]) => `${key}：${String(value)}`)
                                      .join("；")}
                                  </span>
                                ))}
                              </div>
                            )}
                          </article>
                        ))}
                      </div>
                    ) : (
                      <div className="fill-assist-trace-empty">
                        暂无当前行追溯线索，请结合匹配说明列和项目规则说明人工复核。
                      </div>
                    )}
                    <div className="fill-assist-trace-footnote">
                      当前为价格轻量追溯：展示匹配过程、经验池来源和项目规则入口；规则资产未维护完整标准出处时，系统必须明示“暂无标准出处映射”，不编造正式条款。
                    </div>
                  </section>
                  <label className="fill-assist-note">
                    <span>确认备注</span>
                    <textarea
                      value={fillAssistDialog.note}
                      onChange={(event) => setFillAssistDialog((current) => current ? { ...current, note: event.target.value } : current)}
                      placeholder="说明人工采用理由，可留空；自定义候选时必填。"
                    />
                  </label>
                </>
              )}
            </div>
            <div className="settings-modal-actions">
              <button className="ghost-button" type="button" onClick={() => setFillAssistDialog(null)}>取消</button>
              <button className="primary-button" type="button" disabled={fillAssistDialog.isLoading || fillAssistDialog.isConfirming || fillAssistDialog.candidates.length === 0} onClick={confirmFillAssist}>
                {fillAssistDialog.isConfirming ? <Loader2 className="spin" size={18} /> : <CheckCircle2 size={18} />}
                确认写入输出副本
              </button>
            </div>
          </div>
        </div>
      )}

      {isInputFieldSettingsOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setIsInputFieldSettingsOpen(false)}>
          <div className="settings-modal experience-field-settings-modal" role="dialog" aria-modal="true" aria-label="输入字段设置" onClick={(event) => event.stopPropagation()}>
            <div className="modal-title">
              <strong>输入字段设置</strong>
              <button type="button" onClick={() => setIsInputFieldSettingsOpen(false)}>关闭</button>
            </div>
            <div className="field-preference-grid">
              {MAPPING_FIELDS.map((field) => (
                <label className="field-preference-item" key={field}>
                  <span>{field}</span>
                  <textarea
                    value={preferenceText(inputFieldDraft[field])}
                    rows={3}
                    onChange={(event) => updateInputFieldDraft(field, event.target.value)}
                  />
                </label>
              ))}
            </div>
            {inputFieldPreferencesPath && (
              <p className="settings-hint">项目默认来源：{inputFieldPreferencesPath}</p>
            )}
            <div className="settings-action-row">
              <button className="ghost-button" type="button" onClick={resetInputFieldDraft}>
                恢复项目默认
              </button>
              <button className="primary-button" type="button" disabled={isSavingInputFieldSettings} onClick={saveInputFieldPreferences}>
                {isSavingInputFieldSettings ? <Loader2 className="spin" size={17} /> : <Settings size={17} />}
                {file ? "应用临时设置并重新识别" : "应用临时设置"}
              </button>
            </div>
          </div>
        </div>
      )}

      {isPreviewSettingsOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setIsPreviewSettingsOpen(false)}>
          <div className="settings-modal preview-column-settings-modal" role="dialog" aria-modal="true" aria-label="预览列设置" onClick={(event) => event.stopPropagation()}>
            <div className="modal-title">
              <span>
                <strong>预览列设置</strong>
                <small>默认列、表头行和列宽来自项目默认；本窗口修改只临时生效</small>
              </span>
              <button type="button" onClick={() => setIsPreviewSettingsOpen(false)}>关闭</button>
            </div>
            <div className="preview-settings-summary">
              <span>
                <strong>默认打开</strong>
                <small>{parsePreferenceText(previewDefaultLabelsDraft).length || DEFAULT_CORE_PREVIEW_LABELS.length} 列</small>
              </span>
              <span>
                <strong>当前表头</strong>
                <small>{previewSheets.length > 0 ? `第 ${previewHeaderRowValue(activePreviewSettingsSheet)} 行` : "使用预设"}</small>
              </span>
              <span>
                <strong>保存范围</strong>
                <small>项目默认由配置文件统一提供</small>
              </span>
            </div>
            <div className="preview-settings-section">
              <div className="settings-subsection-title">全局默认</div>
              <div className="preview-settings-default-grid">
                <label className="preview-default-column-editor">
                  <span>默认打开的列</span>
                  <textarea
                    value={previewDefaultLabelsDraft}
                    rows={4}
                    onChange={(event) => setPreviewDefaultLabelsDraft(event.target.value)}
                  />
                </label>
                <label className="preview-width-control">
                  <span>列内容宽度</span>
                  <input
                    type="number"
                    min={4}
                    max={40}
                    value={previewColumnPreferences.maxDisplayChars}
                    onChange={(event) => updatePreviewMaxDisplayChars(Number(event.target.value))}
                  />
                  <em>字符</em>
                  <small>超出后自动换行，鼠标悬浮可看完整内容。</small>
                </label>
              </div>
              <p className="settings-hint">未单独设置 sheet 时，优先按这里的列名打开；本次修改只影响当前页面，绿色版首开按项目默认配置生效。</p>
            </div>
            {previewSheets.length > 0 && (
              <div className="preview-settings-section">
                <div className="settings-subsection-title">当前 sheet 单独设置</div>
                <div className="preview-settings-tabs" role="tablist" aria-label="预览列配置 sheet">
                  {previewSheets.map((sheet, sheetIndex) => {
                    const sheetKey = previewSheetKey(sheet);
                    const isActive = sheetKey === previewSheetKey(activePreviewSettingsSheet);
                    return (
                      <button
                        className={isActive ? "is-active" : ""}
                        key={`${sheetKey}-${sheetIndex}`}
                        type="button"
                        onClick={() => setActivePreviewSettingsSheetName(sheetKey)}
                      >
                        {previewSheetLabel(sheet, sheetIndex)}
                      </button>
                    );
                  })}
                </div>
                <div className="preview-settings-body">
                  <div className="preview-settings-head">
                    <span className="preview-settings-sheet-title">
                      <strong>{previewSheetLabel(activePreviewSettingsSheet, Math.max(0, previewSheets.findIndex((sheet) => previewSheetKey(sheet) === previewSheetKey(activePreviewSettingsSheet))))}</strong>
                      <small>勾选本 sheet 默认打开的列；改表头行后点一次刷新列名。</small>
                    </span>
                    <label className="preview-header-row-control">
                      <span>读取第</span>
                      <input
                        type="number"
                        min={1}
                        max={999}
                        value={previewHeaderRowValue(activePreviewSettingsSheet)}
                        onChange={(event) => updatePreviewSheetHeaderRow(activePreviewSettingsSheet, Number(event.target.value))}
                      />
                      <span>行作为列名</span>
                    </label>
                    <button
                      className="ghost-button"
                      type="button"
                      disabled={isRefreshingPreviewSettings || !result}
                      onClick={refreshActivePreviewSettingsSheet}
                    >
                      <RefreshCw className={isRefreshingPreviewSettings ? "spin" : undefined} size={16} />
                      刷新列名
                    </button>
                    <button className="ghost-button" type="button" onClick={resetPreviewSheetColumns}>
                      恢复默认列
                    </button>
                  </div>
                    <div className="preview-settings-grid">
                      {previewSettingColumns.map((column) => {
                        const sheetKey = previewSheetKey(activePreviewSettingsSheet);
                        const selected = resolvePreviewPreferenceLabels(
                          previewSettingColumns,
                          previewColumnPreferences.sheetOverrides[sheetKey] ?? previewColumnPreferences.defaultLabels,
                          activePreviewSettingsSheet,
                          result?.summary.price_column,
                        );
                        return (
                          <label className="mapping-check-field preview-settings-check" key={`${sheetKey}-${column.label}`}>
                            <input
                              checked={selected.includes(column.label)}
                            type="checkbox"
                            onChange={(event) => updatePreviewSheetColumns(column.label, event.target.checked)}
                          />
                          <span>{column.label}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
            <div className="settings-action-row">
              <button className="ghost-button" type="button" onClick={() => setPreviewDefaultLabelsDraft(preferenceText(previewColumnPreferences.defaultLabels))}>
                撤销默认列编辑
              </button>
              <button className="ghost-button" type="button" disabled={isRefreshingPreviewSettings} onClick={restorePreviewProjectDefaults}>
                恢复项目默认
              </button>
              <button className="primary-button" type="button" disabled={isRefreshingPreviewSettings} onClick={savePreviewColumnPreferences}>
                {isRefreshingPreviewSettings ? <Loader2 className="spin" size={17} /> : <Settings size={17} />}
                {isRefreshingPreviewSettings ? "应用中" : "应用临时设置"}
              </button>
            </div>
          </div>
        </div>
      )}

      {isExperienceFieldSettingsOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setIsExperienceFieldSettingsOpen(false)}>
          <div className="settings-modal experience-field-settings-modal" role="dialog" aria-modal="true" aria-label="经验池字段设置" onClick={(event) => event.stopPropagation()}>
            <div className="modal-title">
              <strong>经验池字段设置</strong>
              <button type="button" onClick={() => setIsExperienceFieldSettingsOpen(false)}>关闭</button>
            </div>
            <div className="field-preference-grid">
              {EXPERIENCE_MAPPING_FIELDS.map((field) => (
                <label className="field-preference-item" key={field}>
                  <span>{field}</span>
                  <textarea
                    value={preferenceText(experienceFieldDraft[field])}
                    rows={3}
                    onChange={(event) => updateExperienceFieldDraft(field, event.target.value)}
                  />
                </label>
              ))}
            </div>
            <div className="settings-filter-row">
              <label className="mapping-check-field">
                <input
                  checked={onlyImportExperienceRowsWithValue}
                  type="checkbox"
                  onChange={(event) => setOnlyImportExperienceRowsWithValue(event.target.checked)}
                />
                <span>只导入某一列有值的行</span>
              </label>
              <label className="settings-filter-select">
                <span>判断字段</span>
                <select
                  value={experienceValueFilterField}
                  disabled={!onlyImportExperienceRowsWithValue}
                  onChange={(event) => setExperienceValueFilterField(event.target.value as ExperienceMappingField)}
                >
                  {EXPERIENCE_MAPPING_FIELDS.map((field) => (
                    <option key={field} value={field}>
                      {field === "工程量" ? "工程量 / 数量" : field}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {experienceFieldPreferencesPath && (
              <p className="settings-hint">保存位置：{experienceFieldPreferencesPath}</p>
            )}
            <div className="settings-action-row">
              <button className="ghost-button" type="button" onClick={resetExperienceFieldDraft}>
                恢复默认
              </button>
              <button className="primary-button" type="button" disabled={isSavingExperienceFieldSettings} onClick={saveExperienceFieldPreferences}>
                {isSavingExperienceFieldSettings ? <Loader2 className="spin" size={17} /> : <Settings size={17} />}
                {experienceFile ? "保存并重新识别" : "保存设置"}
              </button>
            </div>
          </div>
        </div>
      )}

      {isExperienceWarningSettingsOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setIsExperienceWarningSettingsOpen(false)}>
          <div className="settings-modal experience-field-settings-modal" role="dialog" aria-modal="true" aria-label="预警设置" onClick={(event) => event.stopPropagation()}>
            <div className="modal-title">
              <strong>预警设置</strong>
              <button type="button" onClick={() => setIsExperienceWarningSettingsOpen(false)}>关闭</button>
            </div>
            <div className="field-preference-grid warning-settings-grid">
              <label className="field-preference-item">
                <span>低风险预警比率（%）</span>
                <input
                  min={0}
                  step="0.01"
                  type="number"
                  value={experienceWarningSettingsDraft.low_risk_warning_ratio}
                  onChange={(event) => updateExperienceWarningSetting("low_risk_warning_ratio", event.target.value)}
                />
              </label>
              <label className="field-preference-item">
                <span>高风险预警比率（%）</span>
                <input
                  min={0}
                  step="0.01"
                  type="number"
                  value={experienceWarningSettingsDraft.high_risk_warning_ratio}
                  onChange={(event) => updateExperienceWarningSetting("high_risk_warning_ratio", event.target.value)}
                />
              </label>
              <label className="mapping-check-field warning-settings-toggle">
                <input
                  checked={experienceWarningSettingsDraft.only_check_rows_with_value}
                  type="checkbox"
                  onChange={(event) => updateExperienceWarningToggle(event.target.checked)}
                />
                <span>只核查指定列有值的行</span>
              </label>
              <label className="field-preference-item">
                <span>指定列字段</span>
                <select
                  value={experienceWarningSettingsDraft.value_filter_field}
                  disabled={!experienceWarningSettingsDraft.only_check_rows_with_value}
                  onChange={(event) => updateExperienceWarningFilterField(event.target.value)}
                >
                  {experienceWarningFilterFields.map((field) => (
                    <option key={field} value={field}>
                      {field}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="settings-hint">前端输入百分比，后端计算时会自动换算成小数；高风险预警比率必须大于等于低风险预警比率；指定列按当前 sheet 检测到的实际表头定位，`0` 视为没有值。</p>
            {experienceWarningSettingsPath && (
              <p className="settings-hint">保存位置：{experienceWarningSettingsPath}</p>
            )}
            <div className="settings-action-row">
              <button className="ghost-button" type="button" onClick={resetExperienceWarningSettingsDraft}>
                恢复当前值
              </button>
              <button className="primary-button" type="button" disabled={isSavingExperienceWarningSettings} onClick={saveExperienceWarningSettings}>
                {isSavingExperienceWarningSettings ? <Loader2 className="spin" size={17} /> : <Settings size={17} />}
                保存设置
              </button>
            </div>
          </div>
        </div>
      )}

      {isWorkloadFieldSettingsOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setIsWorkloadFieldSettingsOpen(false)}>
          <div className="settings-modal experience-field-settings-modal" role="dialog" aria-modal="true" aria-label="工作量抓取字段设置" onClick={(event) => event.stopPropagation()}>
            <div className="modal-title">
              <strong>工作量抓取字段设置</strong>
              <button type="button" onClick={() => setIsWorkloadFieldSettingsOpen(false)}>关闭</button>
            </div>

            <div className="settings-subsection">
              <div className="settings-subsection-title">工作量表字段识别</div>
              <label className="mapping-check-field">
                <input
                  checked={workloadElementSequenceEnabled}
                  type="checkbox"
                  onChange={(event) => setWorkloadElementSequenceEnabled(event.target.checked)}
                />
                <span>匹配到要素1后，要素2-5默认识别后面的连续列（遇到单位列不当作要素）</span>
              </label>
              <label className="mapping-check-field">
                <input
                  checked={workloadAdjacentFallbackEnabled}
                  type="checkbox"
                  onChange={(event) => setWorkloadAdjacentFallbackEnabled(event.target.checked)}
                />
                <span>字段未识别时，默认选择前一字段的下一列</span>
              </label>
              <div className="field-preference-grid">
                {WORKLOAD_SOURCE_FIELDS.map((field) => (
                  <label className="field-preference-item" key={field}>
                    <span>{workloadFieldLabel(field)}</span>
                    <textarea
                      value={preferenceText(workloadFieldDraft[field])}
                      rows={3}
                      onChange={(event) => updateWorkloadFieldDraft(field, event.target.value)}
                    />
                  </label>
                ))}
              </div>
              <div className="settings-filter-row">
                <label className="mapping-check-field">
                  <input
                    checked={onlyCaptureWorkloadRowsWithValue}
                    type="checkbox"
                    onChange={(event) => setOnlyCaptureWorkloadRowsWithValue(event.target.checked)}
                  />
                  <span>只抓取某一列有值的行</span>
                </label>
                <label className="settings-filter-select">
                  <span>判断字段</span>
                  <select
                    value={workloadValueFilterField}
                    disabled={!onlyCaptureWorkloadRowsWithValue}
                    onChange={(event) => setWorkloadValueFilterField(event.target.value as WorkloadSourceField)}
                  >
                    {WORKLOAD_SOURCE_FIELDS.map((field) => (
                      <option key={field} value={field}>
                        {field === "数量" ? "数量（待抓取） / 工程量" : workloadFieldLabel(field)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {workloadFieldPreferencesPath && (
                <p className="settings-hint">项目默认来源：{workloadFieldPreferencesPath}</p>
              )}
            </div>

            <div className="settings-subsection">
              <div className="settings-subsection-title">控制价计算表字段识别</div>
              <label className="mapping-check-field">
                <input
                  checked={workloadTargetElementSequenceEnabled}
                  type="checkbox"
                  onChange={(event) => setWorkloadTargetElementSequenceEnabled(event.target.checked)}
                />
                <span>匹配到要素1后，要素2-5默认识别后面的连续列（遇到单位列不当作要素）</span>
              </label>
              <label className="mapping-check-field">
                <input
                  checked={workloadTargetAdjacentFallbackEnabled}
                  type="checkbox"
                  onChange={(event) => setWorkloadTargetAdjacentFallbackEnabled(event.target.checked)}
                />
                <span>字段未识别时，默认选择前一字段的下一列</span>
              </label>
              <div className="field-preference-grid">
                {WORKLOAD_TARGET_FIELDS.map((field) => (
                  <label className="field-preference-item" key={field}>
                    <span>{workloadFieldLabel(field)}</span>
                    <textarea
                      value={preferenceText(workloadTargetFieldDraft[field])}
                      rows={3}
                      onChange={(event) => updateWorkloadTargetFieldDraft(field, event.target.value)}
                    />
                  </label>
                ))}
              </div>
              {workloadTargetFieldPreferencesPath && (
                <p className="settings-hint">项目默认来源：{workloadTargetFieldPreferencesPath}</p>
              )}
            </div>

            <div className="settings-action-row">
              <button className="ghost-button" type="button" onClick={restoreProjectDefaultSettings}>
                恢复当前项目默认
              </button>
              <button
                className="primary-button"
                type="button"
                disabled={isSavingWorkloadFieldSettings || isSavingWorkloadTargetFieldSettings}
                onClick={saveWorkloadFieldPreferences}
              >
                {(isSavingWorkloadFieldSettings || isSavingWorkloadTargetFieldSettings) ? <Loader2 className="spin" size={17} /> : <Settings size={17} />}
                {(workloadFile || result) ? "应用临时设置并重新识别" : "应用临时设置"}
              </button>
            </div>
          </div>
        </div>
      )}

      {isPageSettingsOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setIsPageSettingsOpen(false)}>
          <div className="settings-modal page-settings-modal" role="dialog" aria-modal="true" aria-label="页面设置" onClick={(event) => event.stopPropagation()}>
            <div className="modal-title">
              <strong>页面设置</strong>
              <button type="button" onClick={() => setIsPageSettingsOpen(false)}>关闭</button>
            </div>
            <div className="settings-subsection">
              <span className="settings-subsection-title">界面微调</span>
              <label className="preference-row">
                <span>
                  <strong>启用用户界面微调</strong>
                  <small>只叠加间距、字号、圆角和文案，不改变转换逻辑。</small>
                </span>
                <input
                  checked={uiPreferencesDraft.enabled}
                  type="checkbox"
                  onChange={(event) => updateUiEnabled(event.target.checked)}
                />
              </label>
              <div className="settings-action-row compact">
                <button className="ghost-button" type="button" disabled={isLoadingUiPreferences} onClick={openUiTuner}>
                  {isLoadingUiPreferences ? <Loader2 className="spin" size={17} /> : <Settings size={17} />}
                  打开微调面板
                </button>
                <button className="primary-button" type="button" disabled={isSavingUiPreferences} onClick={saveUiPreferences}>
                  {isSavingUiPreferences ? <Loader2 className="spin" size={17} /> : <Settings size={17} />}
                  保存用户设置
                </button>
              </div>
              <p className="settings-hint">
                保存位置：{uiPreferencesPath || "Codex-Temp/runtime/ui-preferences-【codex】.json"}
              </p>
            </div>
            <div className="settings-subsection">
              <span className="settings-subsection-title">输出与预览</span>
              <label className="preference-row">
                <span>
                  <strong>隐藏指定列无值的行</strong>
                  <small>下载 Excel 和填价结果预览中，表2/表3/表4 第5行起生效，不改变匹配结果。</small>
                </span>
                <input
                  checked={outputRowFilterSettings.enabled}
                  type="checkbox"
                  onChange={(event) =>
                    setOutputRowFilterSettings((current) => ({
                      ...current,
                      enabled: event.target.checked,
                    }))
                  }
                />
              </label>
              <label className="settings-field-row">
                <span>指定列</span>
                <select
                  disabled={!outputRowFilterSettings.enabled}
                  value={outputRowFilterSettings.value_filter_field}
                  onChange={(event) =>
                    setOutputRowFilterSettings((current) => ({
                      ...current,
                      value_filter_field: event.target.value as WarningFilterField,
                    }))
                  }
                >
                  {experienceWarningFilterFields.map((field) => (
                    <option key={field} value={field}>{field}</option>
                  ))}
                </select>
              </label>
              <p className="settings-hint">字段选择和默认值复用预警模块“只核查指定列有值的行”的口径：当前默认按“数量”判断，空白和 0 都视为无值。</p>
            </div>
          </div>
        </div>
      )}

      {isUiTunerOpen && (
        <aside className="ui-tuner-panel" aria-label="界面微调面板">
          <div className="ui-tuner-head">
            <div>
              <strong>界面微调</strong>
              <span>{uiPreferencesDraft.enabled ? "当前已启用" : "当前未启用"}</span>
            </div>
            <button type="button" onClick={() => setIsUiTunerOpen(false)}>关闭</button>
          </div>

          <label className="ui-tuner-switch">
            <span>启用微调</span>
            <input
              checked={uiPreferencesDraft.enabled}
              type="checkbox"
              onChange={(event) => updateUiEnabled(event.target.checked)}
            />
          </label>

          <label className="ui-tuner-field">
            <span>调整元素</span>
            <select
              value={activeUiTarget}
              onChange={(event) => setActiveUiTarget(event.target.value as UiTunerTargetId)}
            >
              {UI_TUNER_TARGETS.map((target) => (
                <option key={target.id} value={target.id}>{target.name}</option>
              ))}
            </select>
          </label>

          <div className="ui-tuner-grid">
            {[
              ["paddingX", "左右留白", 0, 96],
              ["paddingY", "上下留白", 0, 96],
              ["fontSize", "字号", 10, 72],
              ["radius", "圆角", 0, 60],
              ["gap", "间距", 0, 64],
              ["marginTop", "上边距", -120, 120],
              ["opacity", "透明度", 20, 100],
            ].map(([field, label, min, max]) => (
              <label className="ui-tuner-field compact" key={field}>
                <span>{label}</span>
                <input
                  max={Number(max)}
                  min={Number(min)}
                  placeholder="默认"
                  type="number"
                  value={activeUiStyle[field as keyof UiStyleValues] ?? ""}
                  onChange={(event) => updateUiStyleValue(field as keyof UiStyleValues, event.target.value)}
                />
              </label>
            ))}
          </div>

          <div className="ui-tuner-text">
            <label className="ui-tuner-field">
              <span>界面文字</span>
              <select
                value={activeUiTextKey}
                onChange={(event) => setActiveUiTextKey(event.target.value as UiTextTargetId)}
              >
                {UI_TEXT_TARGETS.map((target) => (
                  <option key={target.id} value={target.id}>{target.name}</option>
                ))}
              </select>
            </label>
            <textarea
              rows={3}
              value={activeUiTextValue}
              onChange={(event) => updateUiTextValue(event.target.value)}
            />
          </div>

          <div className="ui-tuner-actions">
            <button className="ghost-button" type="button" onClick={() => setIsUiPickMode((current) => !current)}>
              {isUiPickMode ? "退出选取" : "选取页面元素"}
            </button>
            <button className="ghost-button" type="button" onClick={resetActiveUiStyle}>恢复当前元素</button>
            <button className="ghost-button" type="button" onClick={resetActiveUiText}>恢复当前文字</button>
            <button className="ghost-button" type="button" onClick={resetAllUiPreferences}>全部恢复默认</button>
            <button className="primary-button" type="button" disabled={isSavingUiPreferences} onClick={saveUiPreferences}>
              {isSavingUiPreferences ? <Loader2 className="spin" size={17} /> : <Settings size={17} />}
              保存用户设置
            </button>
          </div>

          <p className="ui-tuner-help">
            {isUiPickMode ? "点击页面中带高亮的区域即可选中。" : `设置文件：${uiPreferencesPath || "Codex-Temp/runtime/ui-preferences-【codex】.json"}`}
          </p>
        </aside>
      )}

      {isLlmSettingsOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setIsLlmSettingsOpen(false)}>
          <div className="settings-modal" role="dialog" aria-modal="true" aria-label="大模型设置" onClick={(event) => event.stopPropagation()}>
            <div className="modal-title">
              <strong>大模型设置</strong>
              <button type="button" onClick={() => setIsLlmSettingsOpen(false)}>关闭</button>
            </div>
            <label>
              <span>模型选择</span>
              <select
                value={LLM_PRESETS.find((preset) => (
                  preset.provider === llmSettings.provider
                  && preset.model === llmSettings.model
                  && preset.baseUrl === llmSettings.baseUrl
                ))?.id ?? "custom"}
                onChange={(event) => applyLlmPreset(event.target.value)}
              >
                {LLM_PRESETS.map((preset) => (
                  <option key={preset.id} value={preset.id}>{preset.name} - {preset.description}</option>
                ))}
                <option value="custom">自定义</option>
              </select>
            </label>
            <label>
              <span>接入标识</span>
              <input value={llmSettings.provider} onChange={(event) => setLlmSettings((current) => ({ ...current, provider: event.target.value }))} />
            </label>
            <label>
              <span>模型</span>
              <input value={llmSettings.model} onChange={(event) => setLlmSettings((current) => ({ ...current, model: event.target.value }))} />
            </label>
            <label>
              <span>接口地址</span>
              <input value={llmSettings.baseUrl} onChange={(event) => setLlmSettings((current) => ({ ...current, baseUrl: event.target.value }))} />
            </label>
            <p className="settings-hint">API Key 由后端环境变量提供，不在前端保存。官方 DeepSeek 使用 DEEPSEEK_API_KEY，硅基流动使用 SILICONFLOW_API_KEY。</p>
            <div className="settings-subsection zhisuan-window-settings">
              <span className="settings-subsection-title">智算窗口</span>
              <label className="field-preference-item">
                <span>聊天消息区高度（px）</span>
                <input
                  min={300}
                  max={720}
                  step={10}
                  type="number"
                  value={zhisuanChatHeightDraft}
                  onChange={(event) => setZhisuanChatHeightDraft(event.target.value)}
                />
              </label>
              <label className="field-preference-item">
                <span>智算窗口横向宽度（px）</span>
                <input
                  min={300}
                  max={560}
                  step={10}
                  type="number"
                  value={zhisuanDockWidthDraft}
                  onChange={(event) => setZhisuanDockWidthDraft(event.target.value)}
                />
              </label>
              <label className="preference-row">
                <span>
                  <strong>纵向高度跟随当前窗口</strong>
                  <small>开启后右侧智算 Dock 的高度按当前浏览器窗口自动适配，适合宽屏常驻。</small>
                </span>
                <input
                  checked={useZhisuanDockViewportHeight}
                  type="checkbox"
                  onChange={(event) => setUseZhisuanDockViewportHeight(event.target.checked)}
                />
              </label>
              <label className="preference-row">
                <span>
                  <strong>自动隐藏快捷指令</strong>
                  <small>开启后只露出“快捷指令”把手，鼠标移上去弹出完整按钮区。</small>
                </span>
                <input
                  checked={zhisuanQuickSettings.autoHide}
                  type="checkbox"
                  onChange={(event) => updateZhisuanQuickAutoHide(event.target.checked)}
                />
              </label>
              <label className="field-preference-item">
                <span>智算外观风格</span>
                <select
                  value={zhisuanDockStyle}
                  onChange={(event) => setZhisuanDockStyle(event.target.value as ZhisuanDockStyle)}
                >
                  {ZHISUAN_DOCK_STYLE_OPTIONS.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name} - {option.description}
                    </option>
                  ))}
                </select>
              </label>
              <div className="zhisuan-visibility-settings">
                <span className="settings-mini-title">显示项</span>
                <div className="zhisuan-visibility-grid">
                  {ZHISUAN_DOCK_VISIBILITY_OPTIONS.map((option) => (
                    <label className="preference-row" key={option.id}>
                      <span>
                        <strong>{option.name}</strong>
                        <small>{option.description}</small>
                      </span>
                      <input
                        checked={zhisuanDockVisibility[option.id]}
                        type="checkbox"
                        onChange={(event) => updateZhisuanDockVisibility(option.id, event.target.checked)}
                      />
                    </label>
                  ))}
                </div>
              </div>
              <label className="field-preference-item">
                <span>开场欢迎语</span>
                <textarea
                  value={zhisuanWelcomeDraft}
                  rows={3}
                  onChange={(event) => setZhisuanWelcomeDraft(event.target.value)}
                />
              </label>
              <div className="settings-action-row compact">
                <button className="ghost-button" type="button" onClick={resetZhisuanWelcomeMessage}>
                  恢复项目默认欢迎语
                </button>
                <button className="ghost-button" type="button" onClick={restoreZhisuanWindowProjectDefaults}>
                  恢复项目默认
                </button>
                <button className="primary-button" type="button" onClick={() => {
                  saveZhisuanChatHeightSetting();
                  saveZhisuanDockWidthSetting();
                  saveZhisuanWelcomeMessage();
                }}>
                  <Settings size={17} />
                  应用当前会话设置
                </button>
              </div>
              <p className="settings-hint">聊天区高度、横向宽度、纵向高度偏好、欢迎语、智算外观风格和显示项统一来自项目默认配置；本页调整仅在当前会话生效，不写入浏览器本地。横向宽度默认 400px；纵向高度跟随窗口默认关闭；显示项默认全部关闭；两版新外观默认不启用，只改变右侧智算 Dock 的外在表现，不改变功能逻辑。</p>
            </div>
            <div className="settings-subsection zhisuan-quick-settings">
              <span className="settings-subsection-title">问问智算快捷指令</span>
              <div className="zhisuan-quick-settings-grid">
                {ZHISUAN_BUILTIN_QUICK_ITEMS.map((item) => (
                  <label className="mapping-check-field" key={item.id}>
                    <input
                      checked={zhisuanQuickSettings.enabledIds.includes(item.id)}
                      type="checkbox"
                      onChange={(event) => toggleZhisuanQuickItem(item.id, event.target.checked)}
                    />
                    <span>{item.label}</span>
                  </label>
                ))}
              </div>
              <label className="field-preference-item">
                <span>自定义快捷指令</span>
                <textarea
                  value={customQuickCommandDraft}
                  rows={4}
                  placeholder="一行一个，例如：帮我解释本次未找到同类记录"
                  onChange={(event) => setCustomQuickCommandDraft(event.target.value)}
                />
              </label>
              <div className="settings-action-row compact">
                <button className="ghost-button" type="button" onClick={resetZhisuanQuickSettings}>
                  恢复项目默认快捷指令
                </button>
                <button className="primary-button" type="button" onClick={saveCustomZhisuanQuickCommands}>
                  <Settings size={17} />
                  保存自定义快捷指令
                </button>
              </div>
              <p className="settings-hint">内置指令开关和自定义指令只在当前会话生效；自定义指令按行应用，点击后只填入“问问智算”输入框，由用户按 Enter 或点击发送确认。</p>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

type PreviewRowItem = {
  row: Array<string | number | null>;
  sourceIndex: number;
};

function normalizePreviewSheetName(sheetName?: string) {
  return String(sheetName ?? "").trim() || "未命名";
}

function previewExcelRowNumber(
  sheet: TablePreview,
  sourceIndex: number,
  sheetConfigs?: SheetMappingConfig[],
) {
  const explicitRow = sheet.row_numbers?.[sourceIndex];
  if (Number.isFinite(explicitRow)) {
    return Number(explicitRow);
  }
  void sheetConfigs;
  const headerRow = Math.max(0, Math.floor(Number(sheet.header_row ?? 1) || 1));
  return sourceIndex + headerRow + 1;
}

function findPreviewMetricColumnIndex(
  sheet: TablePreview,
  previewColumns: PreviewColumn[],
  priceColumn: string | undefined,
  metric: string | undefined,
) {
  const normalizedMetric = compactHeader(metric);
  if (!normalizedMetric) return -1;
  const priceIndex = findPriceIndex(sheet, priceColumn);
  for (const column of previewColumns) {
    const normalizedLabel = compactHeader(column.label);
    if (
      normalizedMetric === compactHeader("基价")
      && (column.index === priceIndex || normalizedLabel.includes(compactHeader("基价")) || normalizedLabel.includes(compactHeader("单价")))
    ) {
      return column.index;
    }
    if (normalizedLabel.includes(normalizedMetric)) {
      return column.index;
    }
  }
  return -1;
}

function findFillAssistTargetColumn(previewColumns: PreviewColumn[], priceColumn?: string): PreviewColumn | null {
  const normalizedPriceColumn = compactHeader(priceColumn);
  return (
    previewColumns.find((column) => normalizedPriceColumn && compactHeader(column.label) === normalizedPriceColumn) ??
    previewColumns.find((column) => {
      const label = compactHeader(column.label);
      return label.includes(compactHeader("基价")) || label.includes(compactHeader("单价"));
    }) ??
    null
  );
}

function filterPreviewRows(sheet: TablePreview, settings: OutputRowFilterSettings): PreviewRowItem[] {
  const rows = sheet.rows.map((row, index) => ({ row, sourceIndex: index }));
  if (!settings.enabled || !isCorePreviewSheet(sheet)) return rows;
  const filterColumnIndex = warningFilterColumnIndex(sheet.headers, settings.value_filter_field);
  if (filterColumnIndex < 0) return rows;
  return rows.filter(({ row }) => isTotalSummaryRow(row) || hasWarningFilterValue(row[filterColumnIndex]));
}

function warningFilterColumnIndex(headers: Array<string | number | null>, field: WarningFilterField) {
  const aliases = WARNING_FILTER_FIELD_ALIASES[field] ?? [field];
  const normalizedAliases = aliases.map((alias) => compactHeader(alias));
  return headers.findIndex((header) => normalizedAliases.includes(compactHeader(header)));
}

function hasWarningFilterValue(value: unknown) {
  if (value === null || value === undefined || typeof value === "boolean") return false;
  if (typeof value === "number") return Math.abs(value) > 0.000001;
  const text = String(value).trim();
  if (!text) return false;
  const numeric = Number(text.replace(/,/g, ""));
  if (!Number.isNaN(numeric)) return Math.abs(numeric) > 0.000001;
  return true;
}

function isTotalSummaryRow(row: Array<string | number | null>) {
  return compactHeader(row[0]).startsWith("合计");
}

function buildAvailablePreviewColumns(sheet: TablePreview, priceColumn?: string): PreviewColumn[] {
  const priceIndex = findPriceIndex(sheet, priceColumn);
  return sheet.headers.map((header, index) => {
    const label = String(header || `列${index + 1}`);
    const compact = compactHeader(label);
    let kind: PreviewColumn["kind"] = "text";
    if (isWarningHeader(header)) {
      kind = "warning";
    } else if (compact.includes("匹配说明") || compact.includes("抓取日志")) {
      kind = "note";
    } else if (compact === compactHeader("匹配状态") || compact === compactHeader("候选数量")) {
      kind = "status";
    } else if (
      index === priceIndex
      || compact.includes(compactHeader("实物工作费调整系数"))
      || compact.includes(compactHeader("技术工作费调整系数"))
    ) {
      kind = "number";
    }
    return { label, index, kind };
  });
}

function buildPreviewColumns(
  sheet: TablePreview,
  priceColumn?: string,
  preferences?: PreviewColumnPreferences,
): PreviewColumn[] {
  const availableColumns = buildAvailablePreviewColumns(sheet, priceColumn);
  const normalizedPreferences = normalizePreviewColumnPreferences(preferences);
  const sheetKey = previewSheetKey(sheet);
  const preferredLabels = normalizedPreferences.sheetOverrides[sheetKey] ?? normalizedPreferences.defaultLabels;
  const selectedLabels = resolvePreviewPreferenceLabels(availableColumns, preferredLabels, sheet, priceColumn);
  const selectedColumns = selectedLabels
    .map((label) => availableColumns.find((column) => column.label === label))
    .filter((column): column is PreviewColumn => Boolean(column));
  if (selectedColumns.length > 0) {
    return [...selectedColumns].sort((left, right) => left.index - right.index);
  }
  return availableColumns;
}

function previewSheetKey(sheet: TablePreview) {
  return String(sheet.sheet_name ?? "").trim() || "未命名";
}

function previewSheetsFromTablePreview(tablePreview: TablePreview & { sheets?: TablePreview[] }) {
  return tablePreview.sheets?.length ? tablePreview.sheets : [tablePreview];
}

function isCorePreviewSheet(sheet: TablePreview) {
  const sheetName = previewSheetKey(sheet).replace(/\s+/g, "");
  return ["表2", "表3", "表4", "表二", "表三", "表四"].some((token) => sheetName.includes(token));
}

function resolvePreviewPreferenceLabels(
  availableColumns: PreviewColumn[],
  preferredLabels: string[],
  sheet: TablePreview,
  priceColumn?: string,
) {
  const usedIndexes = new Set<number>();
  const resolved: string[] = [];
  for (const preferredLabel of preferredLabels) {
    const matched = availableColumns.find(
      (column) => !usedIndexes.has(column.index) && previewColumnMatchesPreference(column, preferredLabel, sheet, priceColumn),
    );
    if (!matched) continue;
    usedIndexes.add(matched.index);
    resolved.push(matched.label);
  }
  return resolved;
}

function previewColumnMatchesPreference(
  column: PreviewColumn,
  preferredLabel: string,
  sheet: TablePreview,
  priceColumn?: string,
) {
  const preferred = compactHeader(preferredLabel);
  const label = compactHeader(column.label);
  if (!preferred) return false;
  if (label === preferred) return true;
  if (["单价", "基价", "价格"].some((candidate) => compactHeader(candidate) === preferred)) {
    return column.index === findPriceIndex(sheet, priceColumn);
  }
  if (preferred.startsWith("要素") || preferred === "单位") {
    return label.includes(preferred);
  }
  if (preferred.includes("调整系数") || preferred.includes("预警") || preferred.includes("匹配说明")) {
    return label.includes(preferred);
  }
  if (preferred === "匹配状态" || preferred === "候选数量") {
    return label.includes(preferred);
  }
  return label.includes(preferred);
}

function findPriceIndex(sheet: TablePreview, priceColumn?: string) {
  const configured = compactHeader(priceColumn);
  if (configured) {
    const configuredIndex = sheet.headers.findIndex((header) => compactHeader(header) === configured);
    if (configuredIndex >= 0) return configuredIndex;
  }
  return sheet.headers.findIndex((header) => {
    const text = compactHeader(header);
    return ["单价匹配-测试", "基价测试列", "基价", "单价", "价格"].some((candidate) =>
      text.includes(compactHeader(candidate)),
    );
  });
}

function findExactHeaderIndex(sheet: TablePreview, label: string) {
  const target = compactHeader(label);
  return sheet.headers.findIndex((header) => compactHeader(header) === target);
}

function findHeaderIndex(sheet: TablePreview, label: string, excludes: string[] = []) {
  const target = compactHeader(label);
  const exact = findExactHeaderIndex(sheet, label);
  if (exact >= 0) return exact;
  return sheet.headers.findIndex((header) => {
    const text = compactHeader(header);
    return text.includes(target) && excludes.every((token) => !text.includes(compactHeader(token)));
  });
}

function compactHeader(value: string | number | null | undefined) {
  return String(value ?? "").replace(/\s+/g, "");
}

function isWarningHeader(value: string | number | null | undefined) {
  const text = compactHeader(value);
  return text === "预警参数" || text === "预警细节";
}

function getProcessingStage(progress: number) {
  return [...PROCESSING_STAGES].reverse().find((stage) => progress >= stage.min) ?? PROCESSING_STAGES[0];
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone?: "ok" | "warn";
}) {
  return (
    <div className={`metric ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}



