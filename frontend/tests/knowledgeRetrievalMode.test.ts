import assert from "node:assert/strict";
import test from "node:test";
import {
  isKnowledgeRetrievalHybridAvailable,
  normalizeKnowledgeRetrievalMode,
} from "../src/components/knowledge/knowledgeRetrievalMode.ts";

test("hybrid mode is available only when the offline index is ready", () => {
  assert.equal(
    isKnowledgeRetrievalHybridAvailable({ available: true, hybrid_enabled: true, index_ready: true, offline: true }),
    true,
  );
  assert.equal(
    isKnowledgeRetrievalHybridAvailable({ available: true, hybrid_enabled: true, index_ready: false }),
    false,
  );
  assert.equal(
    isKnowledgeRetrievalHybridAvailable({ available: true, hybrid_enabled: false, index_ready: true }),
    false,
  );
});

test("invalid or missing preference falls back to classic", () => {
  assert.equal(normalizeKnowledgeRetrievalMode("hybrid"), "hybrid");
  assert.equal(normalizeKnowledgeRetrievalMode("unexpected"), "classic");
  assert.equal(normalizeKnowledgeRetrievalMode(undefined), "classic");
});
