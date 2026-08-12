import { AlertCircle, Check, Circle, Clock3, UserRoundCheck } from "lucide-react";
import type { TaskEvent, TaskTarget } from "./taskContextUtils";
import { formatTaskTime, taskEventStatusLabel, taskEventTarget, taskEventTone } from "./taskContextUtils";

type Props = {
  items: TaskEvent[];
  onNavigate: (target: TaskTarget) => void;
};

function EventIcon({ status }: { status: string }) {
  if (status === "completed") return <Check size={14} />;
  if (status === "failed") return <AlertCircle size={14} />;
  if (status === "pending_review") return <UserRoundCheck size={14} />;
  if (status === "in_progress") return <Clock3 size={14} />;
  return <Circle size={12} />;
}

export default function TaskTimeline({ items, onNavigate }: Props) {
  return (
    <ol className="task-timeline" aria-label="任务执行轨迹">
      {items.map((item) => {
        const target = taskEventTarget(item);
        return (
          <li className={`is-${taskEventTone(item.status)}`} key={item.event_id || item.event_type}>
            <span className="task-timeline__icon"><EventIcon status={item.status} /></span>
            <div className="task-timeline__content">
              <div><strong>{item.title}</strong><span>{taskEventStatusLabel(item.status)}</span></div>
              <p>{item.detail}</p>
              <small>{item.source_module}{item.occurred_at ? ` · ${formatTaskTime(item.occurred_at)}` : ""}</small>
            </div>
            {target ? <button type="button" onClick={() => onNavigate(target)}>进入</button> : null}
          </li>
        );
      })}
    </ol>
  );
}
