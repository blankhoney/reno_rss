import type { ReactElement } from "react";
import { AuthSessionGate } from "@/components/AuthSessionGate";
import { AdminConsole } from "@/components/AdminConsole";
import { DailyIntelligenceDashboard } from "@/components/DailyIntelligenceDashboard";
import { ModuleSidebar } from "@/components/ModuleSidebar";
import {
  ClustersPanel,
  CraftPanel,
  ExportPanel,
  InterestPanel,
  NotesSearchPanel,
  ResearchPanel,
  RulesPanel,
  SavedSearchesPanel,
  ThemesPanel,
  UnifiedSearchPanel,
} from "@/components/ProductModules";
import { ReaderWorkbench } from "@/components/ReaderWorkbench";
import { ReviewQueue } from "@/components/ReviewQueue";
import {
  resolveArticleSortId,
  resolveSummaryLangId,
  isModuleId,
} from "@/lib/articles/service";
import { isIntelligenceModule } from "@/lib/api/briefs";
import { parseCursorTrail } from "@/lib/articles/navigation";

function normalizeModule(raw: string | string[] | undefined): string {
  if (typeof raw === "string" && raw !== "") return raw;
  // Default home is the Daily Intelligence dashboard, not the full RSS list.
  return "home";
}

function parseResearchJobId(raw: string | string[] | undefined): number | null {
  if (typeof raw !== "string" || !/^\d+$/.test(raw)) return null;
  const jobId = Number(raw);
  return Number.isSafeInteger(jobId) && jobId > 0 ? jobId : null;
}

type PageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

const PRODUCT_PANELS: Record<string, () => ReactElement> = {
  clusters: () => <ClustersPanel />,
  themes: () => <ThemesPanel />,
  rules: () => <RulesPanel />,
  "saved-searches": () => <SavedSearchesPanel />,
  interest: () => <InterestPanel />,
  notes: () => <NotesSearchPanel />,
  craft: () => <CraftPanel />,
  export: () => <ExportPanel />,
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
  const currentQuery = typeof sp.q === "string" ? sp.q : "";

  if (currentModule === "admin") {
    return (
      <AuthSessionGate>
        <main className="workbench">
          <ModuleSidebar currentModule={currentModule} currentSort={currentSort} currentLang={currentLang} />
          <AdminConsole />
        </main>
      </AuthSessionGate>
    );
  }

  if (currentModule === "review") {
    return (
      <AuthSessionGate>
        <main className="workbench">
          <ModuleSidebar currentModule={currentModule} currentSort={currentSort} currentLang={currentLang} />
          <ReviewQueue />
        </main>
      </AuthSessionGate>
    );
  }

  if (currentModule === "search") {
    return (
      <AuthSessionGate>
        <main className="workbench">
          <ModuleSidebar currentModule={currentModule} currentSort={currentSort} currentLang={currentLang} />
          <UnifiedSearchPanel
            initialQuery={currentQuery}
            initialArticleModule={typeof sp.filter === "string" && isModuleId(sp.filter) ? sp.filter : "all"}
            initialSort={currentSort}
          />
        </main>
      </AuthSessionGate>
    );
  }

  if (currentModule === "research") {
    return (
      <AuthSessionGate>
        <main className="workbench">
          <ModuleSidebar currentModule={currentModule} currentSort={currentSort} currentLang={currentLang} />
          <ResearchPanel initialJobId={parseResearchJobId(typeof sp.job === "string" ? sp.job : undefined)} />
        </main>
      </AuthSessionGate>
    );
  }

  const productPanel = PRODUCT_PANELS[currentModule];
  if (productPanel) {
    return (
      <AuthSessionGate>
        <main className="workbench">
          <ModuleSidebar currentModule={currentModule} currentSort={currentSort} currentLang={currentLang} />
          {productPanel()}
        </main>
      </AuthSessionGate>
    );
  }

  if (isIntelligenceModule(currentModule)) {
    return (
      <AuthSessionGate>
        <main className="workbench">
          <ModuleSidebar currentModule="home" currentSort={currentSort} currentLang={currentLang} />
          <DailyIntelligenceDashboard />
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
        currentQuery={currentQuery}
        initialCursorStack={parseCursorTrail(typeof sp.trail === "string" ? sp.trail : null)}
      />
    </AuthSessionGate>
  );
}
