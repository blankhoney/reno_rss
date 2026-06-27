import { AuthSessionGate } from "@/components/AuthSessionGate";
import { AdminConsole } from "@/components/AdminConsole";
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
      />
    </AuthSessionGate>
  );
}
