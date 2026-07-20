import { useEffect, useState } from "react";
import { CheckCircle2, Info, Loader2, RefreshCw, ShieldCheck, X } from "lucide-react";
import "./ProfessionalSkillSelector.css";

export type ProfessionalSkillSummary = {
  id: string;
  display_name: string;
  version: string;
  status: "active" | "beta" | "planned" | "disabled";
  status_label: string;
  domain: string;
  description: string;
  capabilities: string[];
  asset_count: number;
  validation_status: string;
  is_default: boolean;
  can_create_task: boolean;
};

export type ProfessionalSkillDetail = ProfessionalSkillSummary & {
  input_profile: {
    extensions?: string[];
    templateHints?: string[];
  };
  applicability: {
    includes?: string[];
    excludes?: string[];
  };
  asset_summary: Array<{ id: string; name: string; count: number }>;
  validation: {
    status?: string;
    sample?: string;
    updatedAt?: string;
    limitations?: string[];
  };
  boundary: string;
};

export type ProfessionalSkillSnapshot = {
  id: string;
  display_name: string;
  version: string;
  manifest_hash: string;
  created_at: string;
  compatibility_fallback: boolean;
};

type Props = {
  apiBase: string;
  items: ProfessionalSkillSummary[];
  selectedSkillId: string;
  taskSkill?: ProfessionalSkillSnapshot;
  loading: boolean;
  error: string;
  onSelect: (skill: ProfessionalSkillSummary) => void;
  onReload: () => void;
};

function apiErrorMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object") return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return fallback;
}

export default function ProfessionalSkillSelector({
  apiBase,
  items,
  selectedSkillId,
  taskSkill,
  loading,
  error,
  onSelect,
  onReload,
}: Props) {
  const [detailId, setDetailId] = useState("");
  const [detail, setDetail] = useState<ProfessionalSkillDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const selected = items.find((item) => item.id === selectedSkillId);

  useEffect(() => {
    if (!detailId) return;
    const controller = new AbortController();
    setIsDetailLoading(true);
    setDetail(null);
    setDetailError("");
    void fetch(`${apiBase}/api/professional-skills/${encodeURIComponent(detailId)}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(apiErrorMessage(payload, `读取能力详情失败：${response.status}`));
        }
        return response.json() as Promise<ProfessionalSkillDetail>;
      })
      .then(setDetail)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setDetailError(reason instanceof Error ? reason.message : "读取能力详情失败");
      })
      .finally(() => setIsDetailLoading(false));
    return () => controller.abort();
  }, [apiBase, detailId]);

  return (
    <section className="professional-skill-selector" aria-labelledby="professional-skill-title">
      <div className="professional-skill-selector__heading">
        <div>
          <p>专业能力 Skill</p>
          <h3 id="professional-skill-title">选择专业能力</h3>
        </div>
        {selected && (
          <button type="button" className="professional-skill-selector__detail-link" onClick={() => setDetailId(selected.id)}>
            <Info size={15} />
            查看当前能力详情
          </button>
        )}
      </div>

      {loading && (
        <div className="professional-skill-selector__state" role="status">
          <Loader2 className="spin" size={18} /> 正在校验专业能力清单…
        </div>
      )}
      {!loading && error && (
        <div className="professional-skill-selector__state is-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={onReload}><RefreshCw size={15} />重新加载</button>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="professional-skill-selector__state is-error" role="alert">
          当前没有可用的专业能力，暂不能创建任务。
        </div>
      )}
      {!loading && !error && items.length > 0 && (
        <div className="professional-skill-selector__grid" role="list" aria-label="专业能力清单">
          {items.map((item) => {
            const isSelected = item.id === selectedSkillId;
            return (
              <article
                key={item.id}
                className={`professional-skill-card ${isSelected ? "is-selected" : ""} ${item.can_create_task ? "" : "is-disabled"}`}
                role="listitem"
              >
                <div className="professional-skill-card__topline">
                  <span className={`professional-skill-card__status is-${item.status}`}>{item.status_label}</span>
                  <span>v{item.version}</span>
                </div>
                <strong>{item.display_name}</strong>
                <p>{item.description}</p>
                <div className="professional-skill-card__meta">
                  <span>{item.domain}</span>
                  <span>{item.asset_count} 项资产</span>
                </div>
                <div className="professional-skill-card__actions">
                  <button type="button" className="is-detail" onClick={() => setDetailId(item.id)}>查看详情</button>
                  {item.can_create_task ? (
                    <button type="button" className="is-select" aria-pressed={isSelected} onClick={() => onSelect(item)}>
                      {isSelected ? <CheckCircle2 size={15} /> : null}
                      {isSelected ? "已选择" : "选择此能力"}
                    </button>
                  ) : (
                    <button type="button" disabled>不可创建任务</button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {selected && (
        <div className="professional-skill-selector__selection" role="status">
          <ShieldCheck size={17} />
          <span>新任务将使用</span>
          <strong>{selected.display_name} · v{selected.version}</strong>
          {taskSkill && taskSkill.id !== selected.id && <em>当前已生成任务仍锁定原能力快照</em>}
        </div>
      )}

      {detailId && (
        <div className="professional-skill-modal" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) setDetailId("");
        }}>
          <section className="professional-skill-modal__dialog" role="dialog" aria-modal="true" aria-labelledby="professional-skill-detail-title">
            <button type="button" className="professional-skill-modal__close" aria-label="关闭能力详情" onClick={() => setDetailId("")}>
              <X size={19} />
            </button>
            {isDetailLoading && <div className="professional-skill-modal__loading"><Loader2 className="spin" size={20} />正在读取能力详情…</div>}
            {detailError && <div className="professional-skill-modal__error" role="alert">{detailError}</div>}
            {detail && (
              <>
                <div className="professional-skill-modal__hero">
                  <span>{detail.status_label} · v{detail.version}</span>
                  <h3 id="professional-skill-detail-title">{detail.display_name}</h3>
                  <p>{detail.description}</p>
                </div>
                <div className="professional-skill-modal__columns">
                  <div>
                    <h4>适用范围</h4>
                    <ul>{(detail.applicability.includes ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                  <div>
                    <h4>不适用范围</h4>
                    <ul>{(detail.applicability.excludes ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                </div>
                <div className="professional-skill-modal__section">
                  <h4>已声明能力</h4>
                  <div className="professional-skill-modal__chips">
                    {detail.capabilities.length > 0 ? detail.capabilities.map((item) => <span key={item}>{item}</span>) : <span>尚未开放</span>}
                  </div>
                </div>
                <div className="professional-skill-modal__section">
                  <h4>资产与验证</h4>
                  <p>{detail.asset_summary.length > 0 ? detail.asset_summary.map((item) => `${item.name} ${item.count} 项`).join(" · ") : "尚未配置独立业务资产"}</p>
                  <p>验证状态：{detail.validation.status ?? detail.validation_status}；样例：{detail.validation.sample ?? "尚未提供"}；更新时间：{detail.validation.updatedAt ?? "未登记"}</p>
                  {(detail.validation.limitations ?? []).map((item) => <p className="professional-skill-modal__limitation" key={item}>限制：{item}</p>)}
                </div>
                <div className="professional-skill-modal__boundary"><ShieldCheck size={17} />{detail.boundary}</div>
              </>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
