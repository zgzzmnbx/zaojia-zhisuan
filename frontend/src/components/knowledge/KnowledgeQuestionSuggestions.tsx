import { BookOpen, ChevronLeft, ChevronRight, X } from "lucide-react";
import { useEffect, useState } from "react";
import { shouldShowKnowledgeQuestionSuggestions } from "../agent-workspace/agentWorkspaceUtils";

const QUESTIONS_PER_PAGE = 6;

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
  const [page, setPage] = useState(0);
  const totalPages = Math.max(1, Math.ceil(questions.length / QUESTIONS_PER_PAGE));

  useEffect(() => {
    if (!canShowSuggestions) {
      setIsDismissed(false);
      setPage(0);
    }
  }, [canShowSuggestions]);

  useEffect(() => {
    setPage((currentPage) => Math.min(currentPage, totalPages - 1));
  }, [totalPages]);

  if (!canShowSuggestions || questions.length === 0 || isDismissed) return null;

  return (
    <section
      className={`knowledge-question-suggestions is-${placement}`}
      aria-label="常见知识库问题"
    >
      <header>
        <span aria-hidden="true"><BookOpen size={15} /></span>
        <div className="knowledge-question-suggestions__title">
          <strong>常见问题</strong>
          <small>点击填入，仍可继续修改</small>
        </div>
        <div className="knowledge-question-suggestions__controls" aria-label="常见问题翻页">
          <button
            className="knowledge-question-suggestions__page-button"
            type="button"
            aria-label="上一页常见问题"
            title="上一页"
            disabled={page === 0}
            onClick={() => setPage((currentPage) => Math.max(0, currentPage - 1))}
          >
            <ChevronLeft size={14} aria-hidden="true" />
          </button>
          <span className="knowledge-question-suggestions__page-indicator" aria-live="polite">
            {page + 1}/{totalPages}
          </span>
          <button
            className="knowledge-question-suggestions__page-button"
            type="button"
            aria-label="下一页常见问题"
            title="下一页"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((currentPage) => Math.min(totalPages - 1, currentPage + 1))}
          >
            <ChevronRight size={14} aria-hidden="true" />
          </button>
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
        {questions
          .slice(page * QUESTIONS_PER_PAGE, (page + 1) * QUESTIONS_PER_PAGE)
          .map((question, index) => (
            <button
              key={`${question}-${index}`}
              type="button"
              onClick={() => onSelect(question)}
            >
              <span>{page * QUESTIONS_PER_PAGE + index + 1}</span>
              <strong>{question}</strong>
              <ChevronRight size={14} aria-hidden="true" />
            </button>
          ))}
      </div>
    </section>
  );
}
