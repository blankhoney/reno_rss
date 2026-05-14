import { FocusedArticleReader } from "@/components/FocusedArticleReader";
import {
  resolveArticleSortId,
  resolveSummaryLangId,
  type ArticleSortId,
  type SummaryLangId,
} from "@/lib/articles/service";
import { getArticleForReader } from "@/lib/articles/server";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function parseArticleId(raw: string): number | null {
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function normalizeModule(raw: string | string[] | undefined): string {
  return typeof raw === "string" && raw !== "" ? raw : "all";
}

function workbenchHref(
  articleId: number | null,
  moduleId: string,
  sortId: ArticleSortId,
  langId: SummaryLangId,
): string {
  const qs = new URLSearchParams({
    module: moduleId,
    sort: sortId,
    lang: langId,
  });
  if (articleId != null) qs.set("article", String(articleId));
  return `/?${qs.toString()}`;
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

  if (articleId == null) {
    return (
      <main className="focusReader">
        <a className="readerToolbarBtn" href={workbenchHref(null, currentModule, currentSort, currentLang)}>
          返回工作台
        </a>
        <div className="readerEmpty">
          <p className="readerEmptyTitle">文章不存在</p>
          <p className="readerEmptyHint">当前文章 ID 无效。</p>
        </div>
      </main>
    );
  }

  const article = await getArticleForReader(articleId);
  const returnHref = workbenchHref(articleId, currentModule, currentSort, currentLang);

  if (article == null) {
    return (
      <main className="focusReader">
        <a className="readerToolbarBtn" href={returnHref}>
          返回工作台
        </a>
        <div className="readerEmpty">
          <p className="readerEmptyTitle">文章不存在</p>
          <p className="readerEmptyHint">Miniflux 没有返回这篇文章。</p>
        </div>
      </main>
    );
  }

  return (
    <FocusedArticleReader
      article={article}
      currentLang={currentLang}
      returnHref={returnHref}
    />
  );
}
