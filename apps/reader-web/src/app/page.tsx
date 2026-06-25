import { AuthSessionGate } from "@/components/AuthSessionGate";
import { AdminConsole } from "@/components/AdminConsole";
import { FeedQualityPanel } from "@/components/FeedQualityPanel";
import { ModuleSidebar } from "@/components/ModuleSidebar";
import { ReaderWorkbench } from "@/components/ReaderWorkbench";
import {
  resolveArticleSortId,
  resolveSummaryLangId,
} from "@/lib/articles/service";

function normalizeModule(raw: string | string[] | undefined): string {
  if (typeof raw === "string" && raw !== "") return raw;
  return "all";
}

function parseArticleId(raw: string | string[] | undefined): number | null {
  const v = typeof raw === "string" ? raw : undefined;
  if (!v) return null;
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

type PageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function HomePage({ searchParams }: PageProps) {
  const sp = (await searchParams) ?? {};

  const currentModule = normalizeModule(sp.module);
  const sortResolution = resolveArticleSortId(
    typeof sp.sort === "string",
    typeof sp.sort === "string" ? sp.sort : null,
  );
  const currentSort = sortResolution.ok ? sortResolution.sortId : "default";
  const currentLang = resolveSummaryLangId(typeof sp.lang === "string" ? sp.lang : null);
  const requestedSelectedId = parseArticleId(sp.article);

  if (currentModule === "feeds") {
    return (
      <AuthSessionGate>
        <main className="workbench feedWorkbench">
          <ModuleSidebar currentModule={currentModule} currentSort={currentSort} currentLang={currentLang} />
          <FeedQualityPanel />
        </main>
      </AuthSessionGate>
    );
  }

  if (currentModule === "admin") {
    return (
      <AuthSessionGate>
        <main className="workbench feedWorkbench">
          <ModuleSidebar currentModule={currentModule} currentSort={currentSort} currentLang={currentLang} />
          <AdminConsole />
        </main>
      </AuthSessionGate>
    );
  }

  return (
    <AuthSessionGate>
      <ReaderWorkbench
        currentModule={currentModule}
        currentSort={currentSort}
        currentLang={currentLang}
        requestedSelectedId={requestedSelectedId}
      />
    </AuthSessionGate>
  );
}
