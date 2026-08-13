import type { ReactNode } from "react";
import ChartState, { type ChartStateKind } from "./ChartState";

type Props = {
  id: string;
  eyebrow: string;
  title: string;
  summary?: string;
  state?: ChartStateKind;
  stateMessage?: string;
  compact?: boolean;
  children: ReactNode;
};

export default function ChartFrame({ id, eyebrow, title, summary, state = "ready", stateMessage, compact, children }: Props) {
  return (
    <section className={`dv-chart-frame ${compact ? "is-compact" : ""}`} aria-labelledby={`${id}-title`}>
      <header>
        <div><p>{eyebrow}</p><h3 id={`${id}-title`}>{title}</h3></div>
        {summary ? <span>{summary}</span> : null}
      </header>
      <ChartState state={state} message={stateMessage}>{children}</ChartState>
    </section>
  );
}
