import { Loader2, Paperclip, Send, Square } from "lucide-react";
import type { KeyboardEvent } from "react";
import type { ProfessionalSkillSnapshot, ProfessionalSkillSummary } from "../skills/ProfessionalSkillSelector";
import { agentSelectedSkill } from "./agentWorkspaceUtils";

type Props = {
  skills: ProfessionalSkillSummary[];
  selectedSkillId: string;
  taskSkill?: ProfessionalSkillSnapshot;
  fileName: string;
  contextLabel: string;
  value: string;
  busy: boolean;
  disabled: boolean;
  onChange: (value: string) => void;
  onSelectSkill: (skillId: string) => void;
  onPickFile: () => void;
  onSend: () => void;
  onStop: () => void;
  onFocusChange: (focused: boolean) => void;
};

export default function AgentComposer({
  skills,
  selectedSkillId,
  taskSkill,
  fileName,
  contextLabel,
  value,
  busy,
  disabled,
  onChange,
  onSelectSkill,
  onPickFile,
  onSend,
  onStop,
  onFocusChange,
}: Props) {
  const selected = agentSelectedSkill(skills, selectedSkillId, taskSkill);
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    if (!busy && value.trim() && !disabled) onSend();
  };

  return (
    <div className="agent-composer" aria-label="智算助手输入区">
      <div className="agent-composer__context">
        <button className="agent-composer__attachment" type="button" aria-label="添加 Excel 附件" disabled={disabled} onClick={onPickFile}>
          <Paperclip size={16} />
          {fileName || "添加附件"}
        </button>
        <label className="agent-composer__skill">
          <span>专业能力</span>
          <select
            aria-label="选择专业能力 Skill"
            value={selected.id}
            disabled={selected.locked || disabled}
            onChange={(event) => onSelectSkill(event.target.value)}
          >
            {skills.map((skill) => (
              <option key={skill.id} value={skill.id} disabled={!skill.can_create_task}>
                {skill.display_name} · v{skill.version} · {skill.status_label}
              </option>
            ))}
          </select>
          {selected.locked && <em>任务已锁定</em>}
        </label>
        <span className="agent-composer__task-context" title={contextLabel}>{contextLabel}</span>
      </div>
      <textarea
        aria-label="输入任务目标或问题"
        rows={3}
        value={value}
        placeholder="说明任务目标，或输入“批量匹配”“运行经验池预警”“输出风险报告”…"
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => onFocusChange(true)}
        onBlur={() => onFocusChange(false)}
        onKeyDown={handleKeyDown}
      />
      <div className="agent-composer__footer">
        <span>Enter 发送 · Shift+Enter 换行 · Esc 退出</span>
        {busy ? (
          <button className="agent-composer__stop" type="button" aria-label="停止生成" onClick={onStop}>
            <Square size={14} />停止
          </button>
        ) : (
          <button className="agent-composer__send" type="button" disabled={disabled || !value.trim()} aria-label="发送消息" onClick={onSend}>
            {disabled ? <Loader2 className="spin" size={15} /> : <Send size={15} />}
            发送
          </button>
        )}
      </div>
    </div>
  );
}
