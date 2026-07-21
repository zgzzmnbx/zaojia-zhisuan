import { Folder, Plus, X } from "lucide-react";
import type { ReactNode, RefObject } from "react";
import type { ProfessionalSkillSnapshot, ProfessionalSkillSummary } from "../skills/ProfessionalSkillSelector";
import AgentComposer from "./AgentComposer";
import AgentMessageStream, { type AgentWorkspaceMessage } from "./AgentMessageStream";
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
  currentContext: string;
  progressPercent: number;
  progressLabel: string;
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
  onDropFile: (file: File) => void;
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
  currentContext,
  progressPercent,
  progressLabel,
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
  onDropFile,
  onSend,
  onStop,
  onNewConversation,
  onExit,
}: Props<T>) {
  return (
    <section className="agent-workspace" aria-label="智算助手对话式工作台">
      <header className="agent-workspace__header">
        <div className="agent-workspace__identity">
          <Folder aria-hidden="true" size={18} strokeWidth={1.8} />
          <h1>智算助手</h1>
          <span>对话式专业工作台 · {avatarLabel}</span>
        </div>
        <div className="agent-workspace__header-actions">
          <button type="button" onClick={onNewConversation}><Plus size={15} />新会话</button>
          <button type="button" onClick={onExit}><X size={15} />退出</button>
        </div>
      </header>

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

      <AgentComposer
        skills={skills}
        selectedSkillId={selectedSkillId}
        taskSkill={taskSkill}
        fileName={fileName}
        contextLabel={currentContext}
        value={input}
        busy={isChatting}
        disabled={isBusy && !isChatting}
        actions={actions}
        artifacts={artifacts}
        onChange={onInputChange}
        onSelectSkill={onSelectSkill}
        onPickFile={onPickFile}
        onDropFile={onDropFile}
        onSend={onSend}
        onStop={onStop}
        onFocusChange={onInputFocusChange}
      />
    </section>
  );
}
