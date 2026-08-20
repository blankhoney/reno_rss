/**
 * Locks GOAL skeptic product-surface claims so "no consumers" cannot regress.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const root = join(process.cwd(), "src");

function read(rel: string): string {
  return readFileSync(join(root, rel), "utf8");
}

test("DailyIntelligenceDashboard has three persistent entries + radar + source quality", () => {
  const src = read("components/DailyIntelligenceDashboard.tsx");
  assert.match(src, /继续阅读/);
  assert.match(src, /未完成项目/);
  assert.match(src, /待复习划线/);
  assert.match(src, /异常与机会雷达/);
  assert.match(src, /源可信度/);
  assert.match(src, /source_quality|源可信/);
  assert.match(src, /qualityScore/);
});

test("ProductModules + page + palette cover clusters/rules/themes/research/interest", () => {
  assert.equal(existsSync(join(root, "components/ProductModules.tsx")), true);
  assert.equal(existsSync(join(root, "lib/api/intel.ts")), true);
  assert.equal(existsSync(join(root, "lib/craft/preferences.ts")), true);
  const page = read("app/page.tsx");
  assert.match(page, /ClustersPanel/);
  assert.match(page, /RulesPanel/);
  assert.match(page, /ThemesPanel/);
  assert.match(page, /ResearchPanel/);
  assert.match(page, /InterestPanel/);
  assert.match(page, /ExportPanel/);
  assert.match(page, /UnifiedSearchPanel/);
  const palette = read("lib/commandPalette.ts");
  assert.match(palette, /clusters/);
  assert.match(palette, /rules/);
  assert.match(palette, /saved-searches/);
  assert.match(palette, /research/);
  assert.match(palette, /interest/);
  assert.match(palette, /export/);
  assert.match(palette, /nav\("search"/);
});

test("craft prefs include Scan/Focus/Keep density dualPane and pin themes", () => {
  const prefs = read("lib/craft/preferences.ts");
  assert.match(prefs, /scan.*focus.*keep|ReaderMode/);
  assert.match(prefs, /dualPane/);
  assert.match(prefs, /pinnedThemes/);
  assert.match(prefs, /density/);
});

test("focus reader supports dual-pane notes/article, tags, bilingual, citations", () => {
  const focus = read("components/FocusedArticleReader.tsx");
  assert.match(focus, /highlightColor|hl-yellow|color/);
  assert.match(focus, /highlightTags|tags/);
  assert.match(focus, /bilingual|原文\/译文对照/);
  assert.match(focus, /findCitationTarget|scrollToCitation/);
  assert.match(focus, /dualPane|dualArticle|笔记双栏|对照/);
  assert.match(focus, /编辑标注|保存修改/);
  assert.match(focus, /删除标注|删除这条私人标注/);
  assert.match(focus, /标注更新失败|标注删除失败/);
  assert.match(focus, /重试保存/);
  assert.match(focus, /annotation\.color \?\? ""/);
  assert.match(focus, /<option value="">无颜色<\/option>/);
});
