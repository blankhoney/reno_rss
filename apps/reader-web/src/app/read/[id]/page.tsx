import { AuthSessionGate } from "@/components/AuthSessionGate";
import { FocusedArticleScreen } from "@/components/FocusedArticleScreen";
import {
  resolveArticleSortId,
  resolveSummaryLangId,
  type ArticleSortId,
  type SummaryLangId,
} from "@/lib/articles/service";
import { buildWorkbenchHref, parseArticleId, parseCursorTrail } from "@/lib/articles/navigation";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function normalizeModule(raw: string | string[] | undefined): string {
  return typeof raw === "string" && raw !== "" ? raw : "all";
}

function parseResearchJobId(raw: string | string[] | undefined): number | null {
  if (typeof raw !== "string" || !/^\d+$/.test(raw)) return null;
  const jobId = Number(raw);
  return Number.isSafeInteger(jobId) && jobId > 0 ? jobId : null;
}

function workbenchHref(
  articleId: number | null,
  moduleId: string,
  sortId: ArticleSortId,
  langId: SummaryLangId,
  query: string,
  cursorStack: (string | null)[],
  researchJobId: number | null,
): string {
  const href = `/${buildWorkbenchHref({
    module: moduleId,
    sort: sortId,
    lang: langId,
    query,
    cursorStack,
    articleId,
  })}`;
  return researchJobId != null ? `${href}&job=${researchJobId}` : href;
}

export default async function FocusReadPage({ params, searchParams }: PageProps) {
  const { id: idRaw } = await params;
  const sp = (await searchParams) ?? {};
  const articleId = parseArticleId(idRaw);
  const currentModule = normalizeModule(sp.module);
  const sortResolution = resolveArticleSortId(
    typeof sp.sort === "string",
    typeof sp.sort === "string" ? sp.sort : null,
  );
  const currentSort = sortResolution.ok ? sortResolution.sortId : "default";
  const currentLang = resolveSummaryLangId(typeof sp.lang === "string" ? sp.lang : null);
  const currentQuery = typeof sp.q === "string" ? sp.q : "";
  const cursorStack = parseCursorTrail(typeof sp.trail === "string" ? sp.trail : null);
  const researchJobId = parseResearchJobId(sp.job);
  const initialCitation =
    typeof sp.quote === "string" ? sp.quote.trim().slice(0, 500) : "";

  const returnHref = workbenchHref(articleId, currentModule, currentSort, currentLang, currentQuery, cursorStack, researchJobId);

  return (
    <AuthSessionGate>
      {articleId == null ? (
        <main className="focusReader">
          <a className="readerToolbarBtn" href={returnHref}>
            返回工作台
          </a>
          <div className="readerEmpty">
            <p className="readerEmptyTitle">文章不存在</p>
            <p className="readerEmptyHint">当前文章 ID 无效。</p>
          </div>
        </main>
      ) : (
        <FocusedArticleScreen
          articleId={articleId}
          currentLang={currentLang}
          returnHref={returnHref}
          initialCitation={initialCitation || undefined}
        />
      )}
    </AuthSessionGate>
  );
}
