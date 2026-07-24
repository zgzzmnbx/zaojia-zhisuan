import { AlertTriangle, ChevronRight, CircleX, History, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import ProjectCharts from "./ProjectCharts";
import ProjectDashboardToolbar from "./ProjectDashboardToolbar";
import ProjectDetailDrawer from "./ProjectDetailDrawer";
import ProjectHistoryTable from "./ProjectHistoryTable";
import ProjectMetricGrid from "./ProjectMetricGrid";
import {
  clearFilterChip,
  defaultProjectFilters,
  EMPTY_FILTERS,
  filterChips,
  type DashboardPayload,
  type ProjectFilters,
  type ProjectListItem,
  type ProjectListPayload,
  projectQuery,
} from "./projectDashboardUtils";
import "./projectDashboard.css";

type Props = {
  active: boolean;
  apiBase: string;
  currentTask?: {
    projectName: string;
    status: string;
    jobId: string;
  } | null;
  onNewProject: () => void;
  onOpenCurrentTask: () => void;
  onOpenRun: (
    projectId: string,
    runId: string,
    target: "preview" | "report",
  ) => Promise<void>;
};

const EMPTY_LIST: ProjectListPayload = {
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
  pages: 1,
};

export default function ProjectDashboard({
  active,
  apiBase,
  currentTask,
  onNewProject,
  onOpenCurrentTask,
  onOpenRun,
}: Props) {
  const [filters, setFilters] = useState<ProjectFilters>(() => defaultProjectFilters());
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [projects, setProjects] = useState<ProjectListPayload>(EMPTY_LIST);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("updated_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [selectedItem, setSelectedItem] = useState<ProjectListItem | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [showSkeleton, setShowSkeleton] = useState(false);
  const [isBackfilling, setIsBackfilling] = useState(false);
  const [backfillMessage, setBackfillMessage] = useState("");
  const [openError, setOpenError] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setError("");
    const query = projectQuery(filters);
    const listQuery = projectQuery(filters, {
      page,
      page_size: 20,
      sort_by: sortBy,
      sort_order: sortOrder,
    });
    try {
      const [dashboardResponse, projectsResponse] = await Promise.all([
        fetch(`${apiBase}/api/projects/dashboard?${query}`, { signal }),
        fetch(`${apiBase}/api/projects?${listQuery}`, { signal }),
      ]);
      if (!dashboardResponse.ok || !projectsResponse.ok) {
        const failed = !dashboardResponse.ok ? dashboardResponse : projectsResponse;
        const payload = await failed.json().catch(() => ({}));
        throw new Error(payload.detail || "项目台账读取失败");
      }
      const [dashboardPayload, projectsPayload] = await Promise.all([
        dashboardResponse.json() as Promise<DashboardPayload>,
        projectsResponse.json() as Promise<ProjectListPayload>,
      ]);
      setDashboard(dashboardPayload);
      setProjects(projectsPayload);
    } catch (reason) {
      if ((reason as Error).name !== "AbortError") {
        setError((reason as Error).message || "项目台账读取失败");
      }
    } finally {
      setIsLoading(false);
    }
  }, [apiBase, filters, page, sortBy, sortOrder]);

  useEffect(() => {
    const controller = new AbortController();
    const delay = window.setTimeout(() => void load(controller.signal), 120);
    return () => {
      window.clearTimeout(delay);
      controller.abort();
    };
  }, [load]);

  useEffect(() => {
    if (!isLoading) {
      setShowSkeleton(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setShowSkeleton(true), 300);
    return () => window.clearTimeout(timer);
  }, [isLoading]);

  const chips = useMemo(() => filterChips(filters, dashboard), [filters, dashboard]);

  function updateFilters(next: ProjectFilters) {
    setPage(1);
    setFilters(next);
  }

  function onMetric(metric: "total" | "month" | "completed" | "review" | "risk") {
    if (metric === "total") {
      updateFilters({ ...filters, status: "", risk: "", quality: "" });
      return;
    }
    if (metric === "completed") updateFilters({ ...filters, status: "completed", risk: "" });
    if (metric === "review") updateFilters({ ...filters, status: "pending_review", risk: "" });
    if (metric === "risk") updateFilters({ ...filters, risk: "high" });
    if (metric === "month") {
      const today = new Date();
      const from = `${today.getFullYear()}-${`${today.getMonth() + 1}`.padStart(2, "0")}-01`;
      const to = `${today.getFullYear()}-${`${today.getMonth() + 1}`.padStart(2, "0")}-${`${today.getDate()}`.padStart(2, "0")}`;
      updateFilters({ ...filters, dateFrom: from, dateTo: to });
    }
  }

  function onPeriod(period: string) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(period)) {
      updateFilters({ ...filters, dateFrom: period, dateTo: period });
      return;
    }
    const [year, month] = period.split("-").map(Number);
    const last = new Date(year, month, 0).getDate();
    updateFilters({
      ...filters,
      dateFrom: `${period}-01`,
      dateTo: `${period}-${`${last}`.padStart(2, "0")}`,
    });
  }

  function onSort(next: string) {
    setPage(1);
    if (next === sortBy) {
      setSortOrder((current) => current === "asc" ? "desc" : "asc");
    } else {
      setSortBy(next);
      setSortOrder("desc");
    }
  }

  async function handleBackfill() {
    setIsBackfilling(true);
    setBackfillMessage("");
    try {
      const response = await fetch(`${apiBase}/api/projects/backfill`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "历史任务回填失败");
      setBackfillMessage(`回填完成：${payload.totals.projects} 个项目、${payload.totals.runs} 次任务，${payload.totals.unclassified_tasks} 条待归类。`);
      await load();
    } catch (reason) {
      setBackfillMessage((reason as Error).message || "历史任务回填失败");
    } finally {
      setIsBackfilling(false);
    }
  }

  async function openRun(item: ProjectListItem, target: "preview" | "report") {
    if (!item.project_id || !item.run_id) return;
    setOpenError("");
    try {
      await onOpenRun(item.project_id, item.run_id, target);
      setSelectedItem(null);
    } catch (reason) {
      setOpenError((reason as Error).message || "历史任务打开失败");
    }
  }

  if (!active) return null;

  return (
    <div className="project-dashboard">
      <header className="project-dashboard__header">
        <div>
          <h1>项目看板</h1>
          <p>汇总项目、任务、版本与复核进度，筛选结果同步到图表和历史项目。</p>
        </div>
        <button className="project-dashboard__backfill" type="button" disabled={isBackfilling} onClick={() => void handleBackfill()}>
          {isBackfilling ? <Loader2 size={15} className="spin" /> : <History size={15} />}回填历史任务
        </button>
      </header>

      {currentTask ? (
        <button className="project-dashboard__current-task" type="button" onClick={onOpenCurrentTask}>
          <span><i />当前任务</span>
          <strong>{currentTask.projectName || "当前填价任务"}</strong>
          <small>{currentTask.status} · {currentTask.jobId.slice(0, 8)}</small>
          <ChevronRight size={16} />
        </button>
      ) : null}

      <ProjectDashboardToolbar
        filters={filters}
        dashboard={dashboard}
        onChange={updateFilters}
        onReset={() => {
          setPage(1);
          setFilters(defaultProjectFilters());
        }}
        onNewProject={onNewProject}
      />

      {chips.length ? (
        <div className="project-dashboard__chips" aria-label="当前筛选">
          {chips.map((chip) => (
            <button
              type="button"
              key={`${chip.key}-${chip.label}`}
              onClick={() => updateFilters(clearFilterChip(filters, chip.key))}
            >
              {chip.label}<CircleX size={13} />
            </button>
          ))}
        </div>
      ) : null}

      {backfillMessage ? <div className="project-dashboard__backfill-message" role="status">{backfillMessage}</div> : null}
      {openError ? <div className="project-dashboard__error" role="alert"><AlertTriangle size={16} />{openError}</div> : null}
      {error ? (
        <div className="project-dashboard__unavailable" role="alert">
          <AlertTriangle size={22} />
          <div><strong>项目历史暂不可用</strong><span>{error}</span><small>新建填价和现有专业处理链路不受影响。</small></div>
          <button type="button" onClick={() => void load()}>重新加载</button>
        </div>
      ) : null}

      {showSkeleton && !dashboard ? <DashboardSkeleton /> : null}
      {dashboard ? (
        <>
          <ProjectMetricGrid dashboard={dashboard} onSelect={onMetric} />
          <ProjectCharts
            dashboard={dashboard}
            onStatus={(status) => updateFilters({ ...filters, status })}
            onProject={(keyword) => updateFilters({ ...filters, keyword })}
            onPeriod={onPeriod}
            onQuality={(quality) => updateFilters({ ...filters, quality })}
          />
          <ProjectHistoryTable
            apiBase={apiBase}
            payload={projects}
            isLoading={isLoading}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSort={onSort}
            onPage={setPage}
            onSelect={setSelectedItem}
            onOpenRun={(item, target) => void openRun(item, target)}
          />
        </>
      ) : null}

      <ProjectDetailDrawer
        apiBase={apiBase}
        item={selectedItem}
        onClose={() => setSelectedItem(null)}
        onOpenRun={(item, target) => void openRun(item, target)}
      />
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="project-dashboard__skeleton" aria-label="正在加载项目看板">
      <div className="is-metrics">{Array.from({ length: 5 }, (_, index) => <i key={index} />)}</div>
      <div className="is-charts">{Array.from({ length: 4 }, (_, index) => <i key={index} />)}</div>
    </div>
  );
}
