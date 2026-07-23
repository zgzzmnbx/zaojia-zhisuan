import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ReactNode } from "react";
import type { DashboardPayload } from "./projectDashboardUtils";
import { qualityPercentages } from "./projectDashboardUtils";

type Props = {
  dashboard: DashboardPayload;
  onStatus: (status: string) => void;
  onProject: (projectName: string) => void;
  onPeriod: (period: string) => void;
  onQuality: (quality: string) => void;
};

const STATUS_COLORS: Record<string, string> = {
  processing: "#2563eb",
  pending_review: "#60a5fa",
  completed: "#93c5fd",
  returned: "#bfdbfe",
  failed: "#1e40af",
};

function compactProjectName(value: string) {
  const withoutTags = value.replace(/【[^】]+】/g, "").replace(/\s+/g, " ").trim();
  const normalized = withoutTags || value;
  return normalized.length > 12 ? `${normalized.slice(0, 12)}…` : normalized;
}

function AnalysisEmpty({ children }: { children: ReactNode }) {
  return <div className="project-dashboard__chart-empty">{children}</div>;
}

function chartItemValue(item: unknown, key: string) {
  if (!item || typeof item !== "object") return "";
  const record = item as Record<string, unknown>;
  if (record[key] !== undefined) return String(record[key]);
  if (record.payload && typeof record.payload === "object") {
    const payload = record.payload as Record<string, unknown>;
    if (payload[key] !== undefined) return String(payload[key]);
  }
  return "";
}

export default function ProjectCharts({
  dashboard,
  onStatus,
  onProject,
  onPeriod,
  onQuality,
}: Props) {
  const trendTotal = dashboard.trend.reduce(
    (sum, item) => sum + item.new_projects + item.completed_projects,
    0,
  );
  const statusTotal = dashboard.status_distribution.reduce((sum, item) => sum + item.count, 0);
  const quality = qualityPercentages(dashboard.matching_quality);
  const qualityData = [{
    name: "整体匹配质量",
    standard: quality.standard,
    experience: quality.experience,
    review: quality.review,
  }];
  const riskChartData = dashboard.risk_ranking.map((item) => ({
    ...item,
    axis_name: compactProjectName(item.project_name),
  }));

  return (
    <div className="project-dashboard__charts">
      <section className="project-dashboard__analysis is-trend" aria-labelledby="dashboard-trend-title">
        <header>
          <div>
            <p>项目处理趋势</p>
            <h3 id="dashboard-trend-title">新增与完成</h3>
          </div>
          <strong>{trendTotal}</strong>
        </header>
        {dashboard.trend.length >= 2 ? (
          <div className="project-dashboard__chart" role="img" tabIndex={0} aria-label={`项目处理趋势，共 ${dashboard.trend.length} 个周期`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dashboard.trend} margin={{ top: 22, right: 10, left: -18, bottom: 4 }}>
                <CartesianGrid stroke="#dbeafe" vertical={false} />
                <XAxis dataKey="period" tick={{ fill: "#737373", fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fill: "#a3a3a3", fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip cursor={{ fill: "#eff6ff" }} />
                <Legend iconType="circle" iconSize={7} />
                <Bar dataKey="new_projects" name="新增" fill="#60a5fa" radius={[5, 5, 0, 0]} onClick={(data) => {
                  const period = chartItemValue(data, "period");
                  if (period) onPeriod(period);
                }}>
                  <LabelList dataKey="new_projects" position="top" fill="#404040" fontSize={12} />
                </Bar>
                <Bar dataKey="completed_projects" name="完成" fill="#bfdbfe" radius={[5, 5, 0, 0]} onClick={(data) => {
                  const period = chartItemValue(data, "period");
                  if (period) onPeriod(period);
                }}>
                  <LabelList dataKey="completed_projects" position="top" fill="#404040" fontSize={12} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <AnalysisEmpty>有效周期不足 2 个，暂不绘制趋势。当前真实任务共 {dashboard.kpis.total_runs} 次。</AnalysisEmpty>
        )}
        <p className="project-dashboard__chart-summary">
          {dashboard.trend.map((item) => `${item.period} 新增 ${item.new_projects}、完成 ${item.completed_projects}`).join("；") || "当前筛选范围内暂无项目。"}
        </p>
      </section>

      <section className="project-dashboard__analysis is-status" aria-labelledby="dashboard-status-title">
        <header>
          <div>
            <p>项目状态分布</p>
            <h3 id="dashboard-status-title">最新有效状态</h3>
          </div>
          <strong>{statusTotal}</strong>
        </header>
        {statusTotal ? (
          <div className="project-dashboard__donut-wrap">
            <div className="project-dashboard__chart is-donut" role="img" tabIndex={0} aria-label={`项目状态分布，总计 ${statusTotal} 个项目`}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={dashboard.status_distribution.filter((item) => item.count > 0)}
                    dataKey="count"
                    nameKey="label"
                    innerRadius="58%"
                    outerRadius="80%"
                    paddingAngle={2}
                    onClick={(data) => {
                      const status = chartItemValue(data, "status");
                      if (status) onStatus(status);
                    }}
                  >
                    {dashboard.status_distribution.filter((item) => item.count > 0).map((item) => (
                      <Cell key={item.status} fill={STATUS_COLORS[item.status] || "#94a3b8"} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <span className="project-dashboard__donut-center"><b>{statusTotal}</b><small>项目</small></span>
            </div>
            <ul className="project-dashboard__legend-list">
              {dashboard.status_distribution.map((item) => (
                <li key={item.status}>
                  <button type="button" onClick={() => onStatus(item.status)}>
                    <i style={{ background: STATUS_COLORS[item.status] || "#94a3b8" }} />
                    <span>{item.label}</span><b>{item.count}</b>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <AnalysisEmpty>当前筛选范围内暂无可统计项目。</AnalysisEmpty>
        )}
        <p className="project-dashboard__chart-summary">
          {dashboard.status_distribution.map((item) => `${item.label} ${item.count}`).join("；")}
        </p>
      </section>

      <section className="project-dashboard__analysis is-risk" aria-labelledby="dashboard-risk-title">
        <header>
          <div>
            <p>风险项目排行</p>
            <h3 id="dashboard-risk-title">高风险与低风险</h3>
          </div>
          <strong>{dashboard.risk_ranking.length}</strong>
        </header>
        {dashboard.risk_ranking.length ? (
          <div className="project-dashboard__chart is-risk-chart" role="img" tabIndex={0} aria-label={`风险项目排行，共 ${dashboard.risk_ranking.length} 个已运行预警项目`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={riskChartData} layout="vertical" margin={{ top: 4, right: 24, left: 4, bottom: 4 }}>
                <CartesianGrid stroke="#dbeafe" horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={{ fill: "#a3a3a3", fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis dataKey="axis_name" type="category" width={96} tick={{ fill: "#737373", fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip />
                <Legend iconType="circle" iconSize={7} />
                <Bar dataKey="risk_high" name="高风险" stackId="risk" fill="#3b82f6" radius={[5, 0, 0, 5]} onClick={(data) => {
                  const projectName = chartItemValue(data, "project_name");
                  if (projectName) onProject(projectName);
                }}>
                  <LabelList dataKey="risk_high" position="insideLeft" fill="#fff" fontSize={12} />
                </Bar>
                <Bar dataKey="risk_low" name="低风险" stackId="risk" fill="#bfdbfe" radius={[0, 5, 5, 0]} onClick={(data) => {
                  const projectName = chartItemValue(data, "project_name");
                  if (projectName) onProject(projectName);
                }}>
                  <LabelList dataKey="risk_low" position="right" fill="#404040" fontSize={12} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <AnalysisEmpty>暂无已运行预警的风险项目；未运行预警不会计为零风险。</AnalysisEmpty>
        )}
        <p className="project-dashboard__chart-summary">
          {dashboard.risk_ranking.map((item) => `${item.project_name}：高 ${item.risk_high}、低 ${item.risk_low}`).join("；") || `预警未运行项目 ${dashboard.kpis.warning_not_run} 个。`}
        </p>
      </section>

      <section className="project-dashboard__analysis is-quality" aria-labelledby="dashboard-quality-title">
        <header>
          <div>
            <p>整体匹配质量</p>
            <h3 id="dashboard-quality-title">标准、经验与复核</h3>
          </div>
          <strong>{dashboard.matching_quality.total_rows}</strong>
        </header>
        {dashboard.matching_quality.total_rows ? (
          <>
            <div className="project-dashboard__quality-numbers">
              <button type="button" onClick={() => onQuality("standard")}><i className="is-standard" /><span>标准命中</span><b>{dashboard.matching_quality.standard_hit_rows}</b><small>{quality.standard}%</small></button>
              <button type="button" onClick={() => onQuality("experience")}><i className="is-experience" /><span>经验提示</span><b>{dashboard.matching_quality.experience_hint_rows}</b><small>{quality.experience}%</small></button>
              <button type="button" onClick={() => onQuality("review")}><i className="is-review" /><span>待复核</span><b>{dashboard.matching_quality.review_rows}</b><small>{quality.review}%</small></button>
            </div>
            <div className="project-dashboard__chart is-quality-chart" role="img" tabIndex={0} aria-label={`整体匹配质量：标准命中 ${quality.standard}%，经验提示 ${quality.experience}%，待复核 ${quality.review}%`}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={qualityData} layout="vertical" margin={{ top: 0, right: 4, left: 4, bottom: 0 }}>
                  <XAxis type="number" domain={[0, 100]} hide />
                  <YAxis type="category" dataKey="name" hide />
                  <Tooltip formatter={(value) => `${Number(value).toFixed(1)}%`} />
                  <Bar dataKey="standard" stackId="quality" fill="#60a5fa" radius={[5, 0, 0, 5]} onClick={() => onQuality("standard")} />
                  <Bar dataKey="experience" stackId="quality" fill="#93c5fd" onClick={() => onQuality("experience")} />
                  <Bar dataKey="review" stackId="quality" fill="#dbeafe" radius={[0, 5, 5, 0]} onClick={() => onQuality("review")} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        ) : (
          <AnalysisEmpty>当前筛选范围内暂无可汇总的匹配行。</AnalysisEmpty>
        )}
        <p className="project-dashboard__chart-summary">
          标准命中 {dashboard.matching_quality.standard_hit_rows} 行，经验提示 {dashboard.matching_quality.experience_hint_rows} 行，待复核 {dashboard.matching_quality.review_rows} 行。
        </p>
      </section>
    </div>
  );
}
