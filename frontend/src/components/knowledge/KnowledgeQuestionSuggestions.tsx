import { BookOpen, ChevronRight, X } from "lucide-react";
import { useEffect, useState } from "react";
import { shouldShowKnowledgeQuestionSuggestions } from "../agent-workspace/agentWorkspaceUtils";

type Props = {
  value: string;
  questions: string[];
  onSelect: (question: string) => void;
  placement: "agent" | "dock";
};

export default function KnowledgeQuestionSuggestions({
  value,
  questions = [],
  onSelect,
  placement,
}: Props) {
  const canShowSuggestions = shouldShowKnowledgeQuestionSuggestions(value);
  const [isDismissed, setIsDismissed] = useState(false);

  useEffect(() => {
    if (!canShowSuggestions) setIsDismissed(false);
  }, [canShowSuggestions]);

  if (!canShowSuggestions || questions.length === 0 || isDismissed) return null;

  return (
    <section
      className={`knowledge-question-suggestions is-${placement}`}
      aria-label="常见知识库问题"
    >
      <header>
        <span aria-hidden="true"><BookOpen size={15} /></span>
        <div>
          <strong>常见问题</strong>
          <small>点击填入，仍可继续修改</small>
        </div>
        <button
          className="knowledge-question-suggestions__close"
          type="button"
          aria-label="关闭常见问题"
          title="关闭"
          onClick={() => setIsDismissed(true)}
        >
          <X size={14} aria-hidden="true" />
        </button>
      </header>
      <div className="knowledge-question-suggestions__list">
        {questions.map((question, index) => (
          <button
            key={`${question}-${index}`}
            type="button"
            onClick={() => onSelect(question)}
          >
            <span>{index + 1}</span>
            <strong>{question}</strong>
            <ChevronRight size={14} aria-hidden="true" />
          </button>
        ))}
      </div>
    </section>
  );
}
