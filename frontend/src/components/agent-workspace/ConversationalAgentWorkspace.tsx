import { FileSpreadsheet, FileText, Plus, ShieldCheck, X } from "lucide-react";
import type { ReactNode, RefObject } from "react";
import type { ProfessionalSkillSnapshot, ProfessionalSkillSummary } from "../skills/ProfessionalSkillSelector";
import type { ZhisuanAvatarState } from "../ZhisuanAvatar";
import ZhisuanAvatar from "../ZhisuanAvatar";
import AgentComposer from "./AgentComposer";
import AgentMessageStream, { type AgentWorkspaceMessage } from "./AgentMessageStream";
import { agentSelectedSkill, agentTaskPhase, agentTaskPhaseLabel } from "./agentWorkspaceUtils";
import "./agentWorkspace.css";

type Props<T extends AgentWorkspaceMessage> = {
  messages: T[];
  logRef: RefObject<HTMLDivElement | null>;
  welcomeMessage: string;
  renderMessage: (message: T) => ReactNode;
  onRevealMessage: (messageId?: string) => void;
  skills: ProfessionalSkillSummary[];
  selectedSkillId: string;
  taskSkill?: ProfessionalSkillSnapshot;
  fileName: string;
  jobId: string;
  matchingPending: boolean;
  warningExecuted: boolean;
  currentContext: string;
  progressPercent: number;
  progressLabel: string;
  avatarState: ZhisuanAvatarState;
  avatarLabel: string;
  input: string;
  isChatting: boolean;
  isBusy: boolean;
  actions: ReactNode;
  artifacts: ReactNode;
  onInputChange: (value: string) => void;
  onInputFocusChange: (focused: boolean) => void;
  onSelectSkill: (skillId: string) => void;
  onPickFile: () => void;
  onSend: () => void;
  onStop: () => void;
  onNewConversation: () => void;
  onExit: () => void;
};

export default function ConversationalAgentWorkspace<T extends AgentWorkspaceMessage>({
  messages,
  logRef,
  welcomeMessage,
  renderMessage,
  onRevealMessage,
  skills,
  selectedSkillId,
  taskSkill,
  fileName,
  jobId,
  matchingPending,
  warningExecuted,
  currentContext,
  progressPercent,
  progressLabel,
  avatarState,
  avatarLabel,
  input,
  isChatting,
  isBusy,
  actions,
  artifacts,
  onInputChange,
  onInputFocusChange,
  onSelectSkill,
  onPickFile,
  onSend,
  onStop,
  onNewConversation,
  onExit,
}: Props<T>) {
  const phase = agentTaskPhase({
    hasFile: Boolean(fileName),
    hasResult: Boolean(jobId),
    matchingPending,
    warningExecuted,
  });
  const selected = agentSelectedSkill(skills, selectedSkillId, taskSkill);

  return (
    <section className="agent-workspace" aria-label="智算助手对话式工作台">
      <header className="agent-workspace__header">
        <div className="agent-workspace__identity">
          <ZhisuanAvatar state={avatarState} size="normal" />
          <div>
            <p>对话式专业工作台 · {avatarLabel}</p>
            <h1>智算助手</h1>
          </div>
        </div>
        <div className="agent-workspace__header-actions">
          <button type="button" onClick={onNewConversation}><Plus size={15} />新会话</button>
          <button type="button" onClick={onExit}><X size={15} />退出</button>
        </div>
      </header>

      <div className="agent-workspace__status" role="status">
        <span><ShieldCheck size={15} />{selected.displayName}{selected.version ? ` · v${selected.version}` : ""}</span>
        <span className="agent-workspace__phase">{agentTaskPhaseLabel(phase)}</span>
        <span>{jobId ? `任务 ${jobId}` : "尚未创建任务"}</span>
        {taskSkill && <span className="agent-workspace__locked">Skill 快照已锁定</span>}
      </div>

      {isBusy && (
        <div className="agent-workspace__progress" aria-label={progressLabel}>
          <div><span>{progressLabel}</span><strong>{Math.round(progressPercent)}%</strong></div>
          <i><span style={{ width: `${Math.max(4, progressPercent)}%` }} /></i>
        </div>
      )}

      <AgentMessageStream
        messages={messages}
        logRef={logRef}
        emptyMessage={welcomeMessage}
        renderMessage={renderMessage}
        onRevealMessage={onRevealMessage}
      />

      <div className="agent-workspace__operations" aria-label="当前任务操作">
        <div className="agent-workspace__action-strip">{actions}</div>
        {artifacts && <div className="agent-workspace__artifacts"><FileSpreadsheet size={15} /><FileText size={15} />{artifacts}</div>}
      </div>

      <AgentComposer
        skills={skills}
        selectedSkillId={selectedSkillId}
        taskSkill={taskSkill}
        fileName={fileName}
        contextLabel={currentContext}
        value={input}
        busy={isChatting}
        disabled={isBusy && !isChatting}
        onChange={onInputChange}
        onSelectSkill={onSelectSkill}
        onPickFile={onPickFile}
        onSend={onSend}
        onStop={onStop}
        onFocusChange={onInputFocusChange}
      />
    </section>
  );
}
