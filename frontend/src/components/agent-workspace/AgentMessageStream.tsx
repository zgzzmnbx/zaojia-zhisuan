import { Bot } from "lucide-react";
import type { ReactNode, RefObject } from "react";

export type AgentWorkspaceMessage = {
  id?: string;
  role: "system" | "user" | "assistant";
  source?: "model" | "system" | "command" | "thinking";
  isTyping?: boolean;
};

type Props<T extends AgentWorkspaceMessage> = {
  messages: T[];
  logRef: RefObject<HTMLDivElement | null>;
  emptyMessage: string;
  renderMessage: (message: T) => ReactNode;
  onRevealMessage: (messageId?: string) => void;
};

export default function AgentMessageStream<T extends AgentWorkspaceMessage>({
  messages,
  logRef,
  emptyMessage,
  renderMessage,
  onRevealMessage,
}: Props<T>) {
  return (
    <div className="agent-workspace__messages" ref={logRef} role="log" aria-live="polite" aria-label="智算助手会话消息">
      {messages.length === 0 ? (
        <div className="agent-workspace__empty">
          <Bot size={24} />
          <p>{emptyMessage}</p>
        </div>
      ) : (
        <div className="agent-workspace__message-column">
          {messages.map((message, index) => (
            <article
              className={`agent-message ${message.role} ${message.source ? `source-${message.source}` : ""} ${message.isTyping ? "is-typing" : ""}`}
              key={message.id ?? `${message.role}-${index}`}
              onClick={() => {
                if (message.role === "assistant" && message.isTyping) onRevealMessage(message.id);
              }}
              title={message.role === "assistant" && message.isTyping ? "点击立即显示全部" : undefined}
            >
              <span className="agent-message__speaker">{message.role === "user" ? "U" : "Z"}</span>
              <div className="agent-message__body">{renderMessage(message)}</div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
