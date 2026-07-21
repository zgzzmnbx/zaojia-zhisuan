import type { ProfessionalSkillSnapshot, ProfessionalSkillSummary } from "../skills/ProfessionalSkillSelector";

export type AgentTaskPhase = "empty" | "file-ready" | "preview-ready" | "matched" | "warning-complete";

export function agentConversationTurns<T extends { role: "system" | "user" | "assistant" }>(messages: T[]) {
  return messages.reduce<T[][]>((turns, message) => {
    if (turns.length === 0 || message.role === "user") {
      turns.push([message]);
    } else {
      turns[turns.length - 1].push(message);
    }
    return turns;
  }, []);
}

export function agentTaskPhase(options: {
  hasFile: boolean;
  hasResult: boolean;
  matchingPending: boolean;
  warningExecuted: boolean;
}): AgentTaskPhase {
  if (!options.hasFile) return "empty";
  if (!options.hasResult) return "file-ready";
  if (options.matchingPending) return "preview-ready";
  if (options.warningExecuted) return "warning-complete";
  return "matched";
}
export function agentTaskPhaseLabel(phase: AgentTaskPhase) {
  return {
    empty: "等待附件",
    "file-ready": "待开始转换",
    "preview-ready": "待批量匹配",
    matched: "匹配已完成",
    "warning-complete": "预警已完成",
  }[phase];
}

export function agentSelectedSkill(
  items: ProfessionalSkillSummary[],
  selectedSkillId: string,
  taskSkill?: ProfessionalSkillSnapshot,
) {
  if (taskSkill) {
    return {
      id: taskSkill.id,
      displayName: taskSkill.display_name,
      version: taskSkill.version,
      locked: true,
      executable: true,
    };
  }
  const selected = items.find((item) => item.id === selectedSkillId);
  return {
    id: selected?.id ?? "",
    displayName: selected?.display_name ?? "尚未选择专业能力",
    version: selected?.version ?? "",
    locked: false,
    executable: Boolean(selected?.can_create_task),
  };
}
