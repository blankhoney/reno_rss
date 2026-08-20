import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { FocusedArticleReader } from "./FocusedArticleReader";
import type { Article } from "@/lib/articles/types";

function article(input: Partial<Article> = {}): Article {
  return {
    id: 42,
    userId: 1,
    feedId: 2,
    feedTitle: "Feed",
    categoryId: 3,
    categoryTitle: "AI",
    title: "Example title",
    url: "https://example.com",
    contentHtml: "<p>Short body</p>",
    contentStatus: "partial",
    contentIssue: "rss_fragment",
    contentFetchAttempted: true,
    summaryZh: "这是一段中文摘要。",
    summaryOriginal: "This is an original summary.",
    sourceLanguage: "en",
    status: "unread",
    starred: false,
    project: false,
    publishedAt: "2026-05-14T00:00:00Z",
    score: null,
    myFeedback: null,
    readLater: false,
    lastReadAt: null,
    ...input,
  };
}

const appRouter = {
  back() {},
  forward() {},
  prefetch() {},
  push() {},
  replace() {},
  refresh() {},
};

function renderFocusedReader(articleInput: Article, returnHref: string) {
  return renderToStaticMarkup(
    React.createElement(
      AppRouterContext.Provider,
      { value: appRouter as never },
      React.createElement(FocusedArticleReader, {
        article: articleInput,
        currentLang: "zh",
        returnHref,
      }),
    ),
  );
}

test("FocusedArticleReader renders the focus reading controls and partial notice", () => {
  const html = renderFocusedReader(article(), "/?module=all&sort=default&lang=zh&article=42");

  assert.match(html, /返回工作台/);
  assert.match(html, /打开原文/);
  assert.match(html, /翻译全文/);
  assert.doesNotMatch(html, /实时评分/);
  assert.match(html, /评分完成后将生成摘要、分数和理由/);
  assert.doesNotMatch(html, /管理控制台创建评分批次/);
  assert.match(html, /更多文章操作/);
  assert.match(html, /aria-haspopup="menu"/);
  assert.doesNotMatch(html, /<summary>操作<\/summary>/);
  assert.match(html, /正文：片段/);
  assert.match(html, /评分：未评分/);
  assert.match(html, /反馈校准/);
  assert.match(html, /保存反馈/);
  assert.doesNotMatch(html, /aria-pressed="true"/);
  assert.match(html, /译文：未翻译/);
  assert.match(html, /当前仍只有 RSS 片段/);
  assert.match(html, /文章助手/);
  assert.match(html, /总结、要点、解释选中、行动建议/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /agentDrawerBody/);
  assert.match(html, /inert=""/);
  assert.equal((html.match(/class="scoreFeedbackChip(?: |")/g) ?? []).length, 8);
});

test("FocusedArticleReader uses neutral summary copy before scoring", () => {
  const html = renderFocusedReader(
    article({
      summaryZh: "",
      summaryOriginal: "",
    }),
    "/?module=all&sort=default&lang=zh&article=42",
  );

  assert.match(html, /暂无摘要，评分完成后自动生成。/);
  assert.doesNotMatch(html, /管理控制台/);
});

test("FocusedArticleReader renders scored state and dimension reasons", () => {
  const html = renderFocusedReader(
    article({
        contentHtml: "<p>Long enough body ".repeat(30),
        contentStatus: "full",
        contentIssue: null,
        score: {
          overall: 80,
          tier: "read",
          dimensions: {
            topic_relevance: 81,
            information_density: 70,
            source_quality: 76,
            novelty: 64,
            timeliness: 78,
            actionability: 82,
            reading_cost_fit: 50,
            risk_uncertainty: 32,
          },
          tags: ["ai"],
          reason: "值得阅读。",
          summaryZh: "中文摘要",
          summaryOriginal: "English summary",
          sourceLanguage: "en",
          dimensionReasons: {
            topic_relevance: "主题明确。",
          },
          scoredAt: "2026-05-14T00:00:00.000Z",
        },
    }),
    "/?module=technical&sort=score&lang=zh&article=42",
  );

  assert.match(html, /正文：完整/);
  assert.match(html, /评分：已评分/);
  assert.match(html, /推荐/);
  assert.match(html, /总分/);
  assert.match(html, /scoreRing46/);
  assert.equal((html.match(/dimensionBarRow/g) ?? []).length, 8);
  assert.match(html, /主题相关性/);
  assert.match(html, /信息密度/);
  assert.match(html, /来源质量/);
  assert.match(html, /新颖度/);
  assert.match(html, /时效性/);
  assert.match(html, /可执行性/);
  assert.match(html, /阅读成本/);
  assert.match(html, /风险·不确定/);
  assert.match(html, /风险·不确定维度越高代表越需要谨慎/);
  assert.match(html, /维度理由/);
  assert.match(html, /主题明确/);
});

test("FocusedArticleReader prefills saved feedback controls", () => {
  const html = renderFocusedReader(
    article({
      myFeedback: {
        userScore: 35,
        feedbackType: "low_density",
        reason: "信息太散。",
        createdAt: "2026-06-25T00:00:00Z",
        updatedAt: "2026-06-25T00:00:01Z",
      },
    }),
    "/?module=all&sort=default&lang=zh&article=42",
  );

  assert.match(html, /value="35"/);
  assert.match(html, /信息密度低/);
  assert.match(html, /aria-pressed="true"/);
  assert.match(html, /信息太散。/);
});

test("FocusedArticleReader marks failed translation status as danger", () => {
  const html = renderFocusedReader(
    article({
      contentZhStatus: "failed",
    }),
    "/?module=all&sort=default&lang=zh&article=42",
  );

  assert.match(html, /译文：失败/);
  assert.match(html, /focusStatusChipDanger/);
  assert.match(html, /focusTranslationAlert/);
  assert.match(html, /译文生成失败/);
  assert.match(html, /重试翻译/);
});

test("FocusedArticleReader renders a pending translation alert", () => {
  const html = renderFocusedReader(
    article({
      contentZhStatus: "running",
    }),
    "/?module=all&sort=default&lang=zh&article=42",
  );

  assert.match(html, /译文：生成中/);
  assert.match(html, /focusTranslationAlertPending/);
  assert.match(html, /focusTranslationSpinner/);
});

test("FocusedArticleReader preserves edit and selection retry contracts", () => {
  const source = readFileSync(new URL("./FocusedArticleReader.tsx", import.meta.url), "utf8");

  assert.match(source, /annotationEditDraftRef\.current\.trim\(\)/);
  assert.match(source, /annotationEditColorRef\.current \|\| null/);
  assert.match(source, /annotationEditTagsRef\.current/);
  assert.match(source, /retryAnnotationMutationRef\.current = \(\) => void saveAnnotationEdit\(annotation\)/);
  assert.match(source, /window\.confirm\("删除这条私人标注/);
  assert.match(source, /async function submitConfirmedAnnotationDelete/);
  assert.match(source, /retryAnnotationMutationRef\.current = \(\) =>\s+void submitConfirmedAnnotationDelete\(annotation, requestArticleId\)/);
  const confirmedDeleteSource = source.slice(
    source.indexOf("async function submitConfirmedAnnotationDelete"),
    source.indexOf("function removeAnnotation"),
  );
  assert.doesNotMatch(confirmedDeleteSource, /window\.confirm/);
  assert.match(source, /setAnnotations\(\(current\) => current\.filter\(\(item\) => item\.id !== annotation\.id\)\)/);
  assert.match(source, /标注更新失败|标注删除失败/);
  assert.match(source, /重试标注操作/);
  assert.match(source, /anchor: settledAnchorRef\.current/);
  assert.match(source, /color: highlightColorRef\.current \|\| null/);
  assert.match(source, /retryAnnotationSaveRef\.current = desiredMetadata == null/);
  assert.match(source, /retrySelectionCreateWithCurrentMetadata\(snapshot\)/);
  assert.match(source, /annotationCreateMetadataChanged\(snapshot\.payload, desiredMetadata\)/);
  assert.match(source, /await updateArticleAnnotation\(created\.id/);
  assert.match(source, /annotationArticleIdRef\.current !== requestArticleId/);
});

test("FocusedArticleReader note submission uses immutable ownership snapshots", () => {
  const source = readFileSync(new URL("./FocusedArticleReader.tsx", import.meta.url), "utf8");
  const submitStart = source.indexOf("async function submitNoteSnapshot");
  const saveStart = source.indexOf("function saveNoteAnnotation", submitStart);
  const retryStart = source.indexOf("function retryNoteAnnotation", saveStart);
  const retryEnd = source.indexOf("const related = useMemo", retryStart);
  assert.ok(submitStart >= 0 && saveStart > submitStart && retryStart > saveStart && retryEnd > retryStart);
  const submitSource = source.slice(submitStart, saveStart);
  const retrySource = source.slice(retryStart, retryEnd);

  assert.match(source, /type NoteSubmissionSnapshot = \{[\s\S]*articleId: number;[\s\S]*selectionRevision: number;[\s\S]*draftRevision: number;[\s\S]*rawDraft: string;[\s\S]*payload:/);
  assert.match(source, /const snapshot: NoteSubmissionSnapshot = \{[\s\S]*articleId: article\.id,[\s\S]*selectionRevision: selectionRevisionRef\.current,[\s\S]*draftRevision: noteDraftRevisionRef\.current,[\s\S]*rawDraft,[\s\S]*content,[\s\S]*selectedText: selectedTextRef\.current\.trim\(\) \|\| null,[\s\S]*tags: highlightTagsRef\.current/);
  assert.doesNotMatch(submitSource, /noteDraftRef\.current\.trim|selectedTextRef|highlightColorRef|highlightTagsRef|settledAnchorRef/);
  assert.match(source, /pendingNoteRequestRef\.current = \{ seq, snapshot \};\s+setPendingNoteRequestSeq\(seq\);/);
  assert.match(source, /if \(!noteOwnerMountedRef\.current \|\| pendingNoteRequestRef\.current != null\) return;/);
  assert.equal((source.match(/if \(!ownsNoteAttempt\(seq, snapshot\)\) return;/g) ?? []).length, 3);
  assert.match(source, /noteOwnerMountedRef\.current &&[\s\S]*annotationArticleIdRef\.current === snapshot\.articleId &&[\s\S]*pendingNoteRequestRef\.current\?\.seq === seq/);
  assert.match(source, /noteDraftRevisionRef\.current === snapshot\.draftRevision/);
  assert.match(source, /setRetryNoteSubmission\(snapshot\)/);
  assert.match(source, /selectionRevisionRef\.current === snapshot\.selectionRevision/);
  assert.doesNotMatch(retrySource, /setNoteSaveError\(null\)|setRetryNoteSubmission\(null\)/);
  assert.match(source, /retryNoteSubmission \? \([\s\S]*disabled=\{pendingNoteRequestSeq != null\}[\s\S]*pendingNoteRequestSeq != null \? "保存中…" : "重试原提交"/);
  assert.match(source, /noteDraftRevisionRef\.current \+= 1;\s+noteDraftRef\.current = nextDraft;/);
});

test("FocusedArticleReader invalidates note ownership on selection, article change, and unmount", () => {
  const source = readFileSync(new URL("./FocusedArticleReader.tsx", import.meta.url), "utf8");

  assert.match(source, /setRetryNoteSubmission\(\(current\) =>[\s\S]*current\.selectionRevision !== selectionRevision \? null : current/);
  assert.match(source, /noteRequestSeqRef\.current \+= 1;\s+pendingNoteRequestRef\.current = null;\s+setPendingNoteRequestSeq\(null\);\s+setRetryNoteSubmission\(null\);\s+setNoteSaveError\(null\);\s+setNoteDraft\(""\);/);
  assert.match(source, /noteOwnerMountedRef\.current = true;[\s\S]*return \(\) => \{\s+noteOwnerMountedRef\.current = false;[\s\S]*noteRequestSeqRef\.current \+= 1;\s+pendingNoteRequestRef\.current = null;/);
});

test("FocusedArticleReader uses load sequence, mutation epoch, and exact selection ownership", () => {
  const source = readFileSync(new URL("./FocusedArticleReader.tsx", import.meta.url), "utf8");

  assert.match(source, /requestSeq: \+\+annotationLoadSeqRef\.current/);
  assert.match(source, /mutationEpoch: annotationMutationEpochRef\.current/);
  assert.match(source, /ownsAnnotationLoad\(attempt/);
  assert.equal((source.match(/annotationMutationEpochRef\.current \+= 1;/g) ?? []).length, 4);
  assert.match(source, /pendingSelectionCreateRef\.current = attempt;\s+setPendingSelectionCreateSeq\(attempt\.seq\);/);
  assert.match(source, /beforeSelectionRevisionChangeRef\.current = \(nextRevision\) => \{\s+cancelSelectionCreateAttempt\(nextRevision\);\s+selectionRevisionRef\.current = nextRevision;/);
  assert.match(source, /if \(!ownsSelectionCreateAttempt\(attempt\)\) return;/);
  assert.match(source, /setPendingSelectionCreateSeq\(\(current\) => clearExactPendingSeq\(current, attempt\.seq\)\)/);
  assert.match(source, /disabled=\{pendingSelectionCreateSeq != null\}/);
  assert.match(source, /pendingSelectionCreateSeq != null \? "保存中…" : "保存划线"/);
});

test("FocusedArticleReader keeps annotation lifecycle guards independent from note ownership", () => {
  const source = readFileSync(new URL("./FocusedArticleReader.tsx", import.meta.url), "utf8");

  assert.match(source, /setAnnotationSaveError\(null\);\s+retryAnnotationSaveRef\.current = null;/);
  assert.match(source, /retryAnnotationSelectionRevisionRef\.current = null;\s+clearSelection\(\);/);
  assert.match(source, /selectedTextRef\.current = "";\s+settledAnchorRef\.current = null;/);
  assert.match(source, /annotationArticleIdRef\.current = article\.id;/);
  assert.match(source, /setAnnotations\(\[\]\);/);
  assert.match(source, /item\.articleId === article\.id/);
  assert.match(source, /annotation\.articleId !== requestArticleId/);
});
