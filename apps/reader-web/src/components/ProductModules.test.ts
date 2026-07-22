import assert from "node:assert/strict";
import test from "node:test";
import { parseResearchJobId, researchResultFromJob } from "./ProductModules";
import type { ApiJob } from "@/lib/api/articles";

const completedResearchJob: ApiJob = {
  id: 88,
  jobType: "research",
  status: "succeeded",
  progress: null,
  result: {
    brief: {
      answer: "## 本周研究\n\n优先跟进检索质量。",
      citations: [{ article_id: 7, title: "Keyboard article one", quote: "检索质量" }],
      provider: "mock",
      question: "本周重点是什么？",
    },
  },
  lastError: null,
  createdAt: "2026-07-22T00:00:00Z",
  updatedAt: "2026-07-22T00:01:00Z",
  completedAt: "2026-07-22T00:01:00Z",
};

test("parseResearchJobId accepts only positive safe integer URL values", () => {
  assert.equal(parseResearchJobId("88"), 88);
  assert.equal(parseResearchJobId("0"), null);
  assert.equal(parseResearchJobId("-1"), null);
  assert.equal(parseResearchJobId("88.5"), null);
  assert.equal(parseResearchJobId("not-a-job"), null);
  assert.equal(parseResearchJobId(String(Number.MAX_SAFE_INTEGER + 1)), null);
});

test("researchResultFromJob decodes the brief envelope and preserves its question", () => {
  assert.deepEqual(researchResultFromJob(completedResearchJob, "fallback question"), {
    answer: "## 本周研究\n\n优先跟进检索质量。",
    citations: [{ article_id: 7, title: "Keyboard article one", quote: "检索质量" }],
    provider: "mock",
    question: "本周重点是什么？",
  });
});

test("researchResultFromJob supports legacy top-level results and fallback question", () => {
  const legacy = { ...completedResearchJob, result: { answer: "legacy answer" } };
  assert.deepEqual(researchResultFromJob(legacy, "fallback question"), {
    answer: "legacy answer",
    citations: [],
    provider: undefined,
    question: "fallback question",
  });
});
