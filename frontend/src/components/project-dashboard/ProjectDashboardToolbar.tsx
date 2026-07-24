import {
  CalendarDays,
  ChevronDown,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { useId, useState } from "react";
import type { DashboardPayload, ProjectFilters } from "./projectDashboardUtils";
import { datePresetForRange, dateRangeForPreset } from "./projectDashboardUtils";

type Props = {
  filters: ProjectFilters;
  dashboard: DashboardPayload | null;
  onChange: (next: ProjectFilters) => void;
  onReset: () => void;
  onNewProject: () => void;
};

export default function ProjectDashboardToolbar({
  filters,
  dashboard,
  onChange,
  onReset,
  onNewProject,
}: Props) {
  const [isCollapsed, setIsCollapsed] = useState(true);
  const contentId = useId();
  const datePreset = datePresetForRange(filters.dateFrom, filters.dateTo);
  const dateLabel = {
    all: "全部时间",
    "7d": "最近 7 天",
    "30d": "最近 30 天",
    month: "本月",
    "90d": "最近 90 天",
    year: "本年",
    custom: "自定义日期",
  }[datePreset] ?? "自定义日期";
  const skillLabel = filters.skillId || "全部能力";
  const statusLabel = dashboard?.filter_options.statuses.find((item) => item.value === filters.status)?.label
    || filters.status
    || "全部状态";
  const sourceLabel = dashboard?.filter_options.sources.find((item) => item.value === filters.sourceType)?.label
    || filters.sourceType
    || "全部来源";
  const filterSummary = [dateLabel, skillLabel, statusLabel, sourceLabel]
    .filter(Boolean)
    .join(" · ");

  function applyPreset(preset: string) {
    onChange({ ...filters, ...dateRangeForPreset(preset) });
  }

  return (
    <div
      className={`project-dashboard__toolbar ${isCollapsed ? "is-collapsed" : ""}`}
      aria-label="项目看板筛选工具条"
    >
      <button
        className="project-dashboard__toolbar-toggle"
        type="button"
        aria-expanded={!isCollapsed}
        aria-controls={contentId}
        onClick={() => setIsCollapsed((current) => !current)}
      >
        <span className="project-dashboard__toolbar-toggle-title">
          <SlidersHorizontal size={15} />筛选条件
        </span>
        <span className="project-dashboard__toolbar-summary" title={filterSummary}>{filterSummary}</span>
        <span className="project-dashboard__toolbar-toggle-action">
          {isCollapsed ? "展开" : "收起"}
          <ChevronDown size={15} aria-hidden="true" />
        </span>
      </button>

      <div className="project-dashboard__toolbar-content" id={contentId} hidden={isCollapsed}>
        <div className="project-dashboard__toolbar-row is-period">
          <label className="project-dashboard__field is-range">
            <span><CalendarDays size={14} />时间范围</span>
            <select
              aria-label="选择时间范围"
              value={datePreset}
              onChange={(event) => applyPreset(event.target.value)}
            >
              <option value="all">全部时间</option>
              <option value="7d">最近 7 天</option>
              <option value="30d">最近 30 天</option>
              <option value="month">本月</option>
              <option value="90d">最近 90 天</option>
              <option value="year">本年</option>
              <option value="custom" disabled>自定义日期</option>
            </select>
          </label>
          <label className="project-dashboard__field project-dashboard__date">
            <span>开始日期</span>
            <input
              type="date"
              value={filters.dateFrom}
              onChange={(event) => onChange({ ...filters, dateFrom: event.target.value })}
            />
          </label>
          <span className="project-dashboard__range-separator">—</span>
          <label className="project-dashboard__field project-dashboard__date">
            <span>结束日期</span>
            <input
              type="date"
              value={filters.dateTo}
              onChange={(event) => onChange({ ...filters, dateTo: event.target.value })}
            />
          </label>
          <label className="project-dashboard__compare">
            <input
              type="checkbox"
              checked={filters.compare}
              onChange={(event) => onChange({ ...filters, compare: event.target.checked })}
            />
            <span>对比上一周期</span>
          </label>
        </div>

        <div className="project-dashboard__toolbar-row is-filters">
          <label className="project-dashboard__field">
            <span>专业能力</span>
            <select
              value={filters.skillId}
              onChange={(event) => onChange({ ...filters, skillId: event.target.value })}
            >
              <option value="">全部能力</option>
              {dashboard?.filter_options.skills.map(([id, version]) => (
                <option value={id} key={`${id}-${version}`}>{id} · v{version}</option>
              ))}
            </select>
          </label>
          <label className="project-dashboard__field">
            <span>状态</span>
            <select
              value={filters.status}
              onChange={(event) => onChange({ ...filters, status: event.target.value })}
            >
              <option value="">全部状态</option>
              {dashboard?.filter_options.statuses.map((item) => (
                <option value={item.value} key={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <label className="project-dashboard__field">
            <span>来源</span>
            <select
              value={filters.sourceType}
              onChange={(event) => onChange({ ...filters, sourceType: event.target.value })}
            >
              <option value="">全部来源</option>
              {dashboard?.filter_options.sources.map((item) => (
                <option value={item.value} key={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <label className="project-dashboard__search">
            <Search size={15} />
            <span className="visually-hidden">搜索项目</span>
            <input
              value={filters.keyword}
              placeholder="搜索项目名称或编号"
              onChange={(event) => onChange({ ...filters, keyword: event.target.value })}
            />
          </label>
          <button className="project-dashboard__reset" type="button" onClick={onReset}>
            <RotateCcw size={15} />重置
          </button>
          <button className="project-dashboard__primary" type="button" onClick={onNewProject}>
            <Sparkles size={15} />新建填价
          </button>
        </div>
      </div>
    </div>
  );
}
