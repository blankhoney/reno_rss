import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function resetFixtures(page: import("@playwright/test").Page) {
  await page.request.post("/__e2e/reset");
}

function captureUnexpectedBrowserErrors(page: import("@playwright/test").Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => {
    errors.push(`pageerror: ${error.message}`);
  });
  return errors;
}

async function setCraftPreferences(
  page: import("@playwright/test").Page,
  preferences: {
    mode: "scan" | "focus" | "keep";
    dualPane?: boolean;
    dualPaneKind?: "notes" | "article";
  },
) {
  await page.addInitScript((prefs) => {
    window.localStorage.setItem(
      "ai-reader.craft.preferences",
      JSON.stringify({
        mode: prefs.mode,
        density: "comfortable",
        dualPane: prefs.dualPane ?? false,
        dualPaneKind: prefs.dualPaneKind ?? "notes",
        dualArticleId: null,
        pinnedThemes: [],
      }),
    );
    document.documentElement.dataset.readerMode = prefs.mode;
    document.documentElement.dataset.dualPane = prefs.dualPane ? "true" : "false";
  }, preferences);
}

async function enableNotesDualPane(page: import("@playwright/test").Page) {
  await setCraftPreferences(page, { mode: "focus", dualPane: true, dualPaneKind: "notes" });
}

async function selectReaderText(page: import("@playwright/test").Page) {
  const paragraph = page.locator(".focusContent p").first();
  await paragraph.scrollIntoViewIfNeeded();
  const box = await paragraph.boundingBox();
  if (box == null) throw new Error("E2E article fixture has no selectable text");
  const y = box.y + box.height / 2;
  await page.mouse.move(box.x + 1, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width - 1, y, { steps: 4 });
  await page.mouse.up();
}

async function selectReaderParagraph(page: import("@playwright/test").Page, text: string) {
  const paragraph = page.locator(".focusContent p").nth(1);
  await expect(paragraph).toHaveText(text, { exact: true });
  await paragraph.scrollIntoViewIfNeeded();
  await paragraph.click({ clickCount: 3, position: { x: 8, y: 12 } });
}

function contrastRatio(foreground: string, background: string): number {
  const luminance = (color: string) => {
    const hex = color.match(/^#([0-9a-f]{6})$/i)?.[1];
    const channels = hex
      ? [hex.slice(0, 2), hex.slice(2, 4), hex.slice(4, 6)].map((channel) => Number.parseInt(channel, 16))
      : color.match(/\d+/g)?.map(Number);
    if (channels == null || channels.length < 3) throw new Error(`Expected rgb color, received ${color}`);
    const [red, green, blue] = channels.slice(0, 3).map((channel) => {
      const normalized = channel / 255;
      return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  };
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}

test("muted reading text meets AA contrast and reduced motion disables nonessential transitions", async ({ page }) => {
  await resetFixtures(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?module=all&sort=default&lang=zh");

  const tokens = await page.evaluate(() => {
    const values = () => {
      const styles = getComputedStyle(document.documentElement);
      return { muted: styles.getPropertyValue("--muted").trim(), background: styles.getPropertyValue("--bg").trim() };
    };
    const light = values();
    document.documentElement.dataset.theme = "dark";
    const dark = values();
    return { light, dark, transitionDuration: getComputedStyle(document.body).transitionDuration };
  });
  expect(contrastRatio(tokens.light.muted, tokens.light.background)).toBeGreaterThanOrEqual(4.5);
  expect(contrastRatio(tokens.dark.muted, tokens.dark.background)).toBeGreaterThanOrEqual(4.5);
  expect(tokens.transitionDuration).toBe("0.001s");
});

test("registers and controls the second local page load", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/");
  await expect(page).toHaveTitle("AI Reader");

  const registration = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    return registration.active?.scriptURL ?? null;
  });
  expect(registration).toContain("/sw.js");

  await page.reload();
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller != null)).toBe(true);
});

test("core pages expose semantic landmarks, headings, and named controls", async ({ page }) => {
  await resetFixtures(page);

  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await expect(page.locator("main")).toBeVisible();
  await expect(page.locator("nav").first()).toBeVisible();
  await expect(page.getByRole("heading").first()).toBeVisible();
  await expect(page.getByRole("button").first()).toBeVisible();
  await expect(page.getByRole("link").first()).toBeVisible();

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await expect(page.locator("main")).toBeVisible();
  await expect(page.getByRole("toolbar", { name: "文章操作" })).toBeVisible();
  await expect(page.getByRole("button", { name: "翻译全文" })).toBeVisible();

  await page.request.post("/__e2e/article-list/fail-once");
  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText(/文章加载失败/)).toBeVisible();
  await expect(page.locator('[aria-live="polite"]').first()).toBeVisible();
});

test("keyboard Tab reaches interactive elements with visible focus", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();

  await page.keyboard.press("Tab");
  const firstFocused = await page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    const style = getComputedStyle(el);
    return {
      tag: el.tagName.toLowerCase(),
      hasOutline: style.outlineStyle !== "none" && style.outlineWidth !== "0px",
      hasBoxShadow: style.boxShadow !== "none",
    };
  });
  expect(firstFocused).not.toBeNull();
  expect(firstFocused!.hasOutline || firstFocused!.hasBoxShadow).toBe(true);

  for (let i = 0; i < 5; i++) await page.keyboard.press("Tab");
  const laterFocused = await page.evaluate(() => {
    const el = document.activeElement;
    return el && el !== document.body ? el.tagName.toLowerCase() : null;
  });
  expect(laterFocused).not.toBeNull();

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await page.keyboard.press("Tab");
  const readerFocused = await page.evaluate(() => {
    const el = document.activeElement;
    return el && el !== document.body ? el.getAttribute("aria-label") ?? el.tagName.toLowerCase() : null;
  });
  expect(readerFocused).not.toBeNull();
});

test("axe scan finds no critical accessibility violations on core pages", async ({ page }) => {
  await resetFixtures(page);

  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  const workbenchResults = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .disableRules(["color-contrast"])
    .analyze();
  const workbenchCritical = workbenchResults.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(workbenchCritical, `Workbench a11y: ${JSON.stringify(workbenchCritical.map((v) => v.id))}`).toEqual([]);

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  const readerResults = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .disableRules(["color-contrast"])
    .analyze();
  const readerCritical = readerResults.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(readerCritical, `Reader a11y: ${JSON.stringify(readerCritical.map((v) => v.id))}`).toEqual([]);
});

test("principal success fixtures render without unexpected browser errors", async ({ page }) => {
  const errors = captureUnexpectedBrowserErrors(page);
  await resetFixtures(page);

  await page.goto("/?module=home&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "今日研究简报" })).toBeVisible();

  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await expect(page.getByText("Evidence should survive navigation.", { exact: true })).toBeVisible();

  await page.goto("/?module=review&sort=default&lang=zh");
  await expect(page.getByText("A durable note returns when it matters.", { exact: true })).toBeVisible();

  await page.goto("/?module=search&filter=all&sort=default&lang=zh&q=fast");
  await expect(page.getByText("Fast search result", { exact: true }).first()).toBeVisible();

  await page.goto("/?module=research&sort=default&lang=zh&job=88");
  await expect(page.getByText("优先跟进检索质量。", { exact: true })).toBeVisible();

  await page.goto("/?module=export&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "立项导出" })).toBeVisible();

  await page.request.post("/__e2e/admin");
  await page.goto("/?module=admin&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "管理控制台" })).toBeVisible();
  await expect(page.getByText(/Score 0\/60/)).toBeVisible();

  expect(errors).toEqual([]);
});

test("keeps job polling on the network after service worker control", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller != null)).toBe(true);

  const statuses = await page.evaluate(async () => {
    const first = await fetch("/api/jobs/7").then((response) => response.json());
    const second = await fetch("/api/jobs/7").then((response) => response.json());
    return [first.status, second.status];
  });

  expect(statuses).toEqual(["queued", "succeeded"]);
});

test("never serves the previous user's cached article when the authenticated user changes", async ({ context, page }) => {
  await resetFixtures(page);
  await page.goto("/");
  await expect(page.getByText("Ada", { exact: true })).toBeVisible();
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller != null)).toBe(true);

  const articleForA = await page.evaluate(async () => {
    const response = await fetch("/api/articles/7");
    return { status: response.status, body: await response.json() };
  });
  expect(articleForA).toMatchObject({ status: 200, body: { owner: "user-a" } });

  await page.getByRole("button", { name: "退出登录" }).click();
  await page.getByRole("textbox", { name: "显示名称" }).fill("Babbage");
  await page.getByRole("button", { name: "进入阅读" }).click();
  await expect(page.getByText("Babbage", { exact: true })).toBeVisible();

  await context.setOffline(true);
  const articleForBOffline = await page.evaluate(async () => {
    try {
      const response = await fetch("/api/articles/7");
      return { status: response.status, body: await response.json(), networkError: false };
    } catch {
      return { status: null, body: null, networkError: true };
    }
  });
  await context.setOffline(false);

  if (articleForBOffline.networkError) {
    expect(articleForBOffline).toMatchObject({ status: null, body: null });
  } else if (articleForBOffline.status === 200) {
    expect(articleForBOffline.body).toMatchObject({ owner: "user-b" });
  } else {
    expect(articleForBOffline).toMatchObject({ status: 503, body: { error: { code: "offline" } } });
  }
});

test("mobile module drawer overlays the bottom navigation", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await resetFixtures(page);
  await page.goto("/?module=all");
  await page.getByRole("button", { name: "打开阅读模块" }).click();
  await expect(page.getByRole("dialog", { name: "阅读模块" })).toBeVisible();

  const layers = await page.evaluate(() => ({
    drawer: Number.parseInt(getComputedStyle(document.querySelector(".mobileNavOverlay")!).zIndex, 10),
    bottomNav: Number.parseInt(getComputedStyle(document.querySelector(".mobileBottomNav")!).zIndex, 10),
  }));
  expect(layers.drawer).toBeGreaterThan(layers.bottomNav);
});

for (const viewport of [
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
]) {
  test(`mobile module drawer isolates navigation at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await resetFixtures(page);
    await page.goto("/?module=all");
    await page.getByRole("button", { name: "打开阅读模块" }).click();
    const drawer = page.getByRole("dialog", { name: "阅读模块" });
    await expect(drawer).toBeVisible();
    await expect(page.locator(".mobileBottomNav")).toHaveJSProperty("inert", true);
    await expect.poll(() => drawer.evaluate((element) => element.getBoundingClientRect().left >= 0)).toBe(true);

    const geometry = await page.evaluate(() => {
      const drawer = document.querySelector<HTMLElement>(".mobileNavDrawer")!.getBoundingClientRect();
      const navigation = document.querySelector<HTMLElement>(".mobileBottomNav")!.getBoundingClientRect();
      return {
        drawerLeft: drawer.left,
        drawerRight: drawer.right,
        drawerTop: drawer.top,
        drawerBottom: drawer.bottom,
        navigationTop: navigation.top,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
      };
    });
    expect(geometry.drawerLeft).toBeGreaterThanOrEqual(0);
    expect(geometry.drawerRight).toBeLessThanOrEqual(geometry.viewportWidth);
    expect(geometry.drawerTop).toBeGreaterThanOrEqual(0);
    expect(geometry.drawerBottom).toBeLessThanOrEqual(geometry.viewportHeight);
    expect(geometry.navigationTop).toBeGreaterThan(geometry.drawerTop);
  });
}

for (const viewport of [
  { width: 320, height: 568 },
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
]) {
  test(`mobile selection toolbar stays above navigation and yields to the Agent drawer at ${viewport.width}px`, async ({ page }) => {
  await page.setViewportSize(viewport);
  await resetFixtures(page);
  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.getByRole("button", { name: /文章助手/ })).toBeVisible();
  await expect(page.locator(".toastHost")).toBeAttached();
  await page.evaluate(
    () => new Promise<void>((resolve) => window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()))),
  );
  await selectReaderText(page);
  const toolbar = page.getByRole("toolbar", { name: "选中文字操作" });
  await expect(toolbar).toBeVisible();
  await page.evaluate(() => {
    window.dispatchEvent(
      new CustomEvent("ai-reader:toast", { detail: { title: "选区布局检查", variant: "info" } }),
    );
  });
  await expect(page.getByText("选区布局检查", { exact: true })).toBeVisible();

  const geometry = await page.evaluate(() => {
    const selection = document.querySelector<HTMLElement>(".selectionPopover")!.getBoundingClientRect();
    const toast = document.querySelector<HTMLElement>(".toastCard")!.getBoundingClientRect();
    const navigation = document.querySelector<HTMLElement>(".mobileBottomNav")!.getBoundingClientRect();
    return {
      selectionLeft: selection.left,
      selectionRight: selection.right,
      selectionTop: selection.top,
      selectionBottom: selection.bottom,
      toastBottom: toast.bottom,
      navigationTop: navigation.top,
      viewportWidth: window.innerWidth,
    };
  });
  expect(geometry.selectionLeft).toBeGreaterThanOrEqual(0);
  expect(geometry.selectionRight).toBeLessThanOrEqual(geometry.viewportWidth);
  expect(geometry.selectionBottom).toBeLessThanOrEqual(geometry.navigationTop);
  expect(geometry.toastBottom).toBeLessThanOrEqual(geometry.selectionTop + 0.1);

  await page.getByRole("button", { name: /文章助手/ }).click();
  await expect(toolbar).toBeHidden();
  await expect(page.getByText(/已选中：Evidence persists\./)).toBeVisible();
  const agentGeometry = await page.evaluate(() => {
    const toast = document.querySelector<HTMLElement>(".toastCard")!.getBoundingClientRect();
    const agent = document.querySelector<HTMLElement>(".agentDrawer")!.getBoundingClientRect();
    return { toastBottom: toast.bottom, agentTop: agent.top };
  });
  expect(agentGeometry.toastBottom).toBeLessThanOrEqual(agentGeometry.agentTop + 0.1);
  });
}

test("saved selection carries a versioned text quote anchor", async ({ page }) => {
  await resetFixtures(page);
  let submitted: Record<string, unknown> | null = null;
  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        annotation: {
          id: 42,
          article_id: 7,
          type: "annotation",
          selected_text: submitted.selected_text,
          content: submitted.content,
          color: submitted.color,
          tags: submitted.tags,
          anchor: submitted.anchor,
          created_at: "2026-07-26T00:00:00Z",
          next_review_at: null,
          interval_days: 1,
          review_count: 0,
        },
      }),
    });
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.locator('mark[data-annotation-id="41"]')).toBeVisible();
  await selectReaderText(page);
  await page.getByRole("button", { name: "保存划线" }).click();
  await expect(page.getByText("已保存划线", { exact: true })).toBeVisible();

  expect(submitted).not.toBeNull();
  const anchor = submitted?.anchor as Record<string, unknown>;
  expect(anchor.kind).toBe("text-quote");
  expect(anchor.version).toBe(1);
  expect(anchor.exact).toBe("Evidence persists.");
  expect(typeof anchor.prefix).toBe("string");
  expect(typeof anchor.suffix).toBe("string");
  expect(anchor.end).toBe((anchor.start as number) + "Evidence persists.".length);
});

test("selection anchor survives note editor focus before save", async ({ page }) => {
  await resetFixtures(page);
  await enableNotesDualPane(page);
  let submitted: Record<string, unknown> | null = null;
  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        annotation: {
          id: 43,
          article_id: 7,
          type: "annotation",
          selected_text: submitted.selected_text,
          content: submitted.content,
          color: submitted.color,
          tags: [],
          anchor: submitted.anchor,
          created_at: "2026-07-26T00:00:00Z",
          next_review_at: null,
          interval_days: 1,
          review_count: 0,
        },
      }),
    });
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.locator('mark[data-annotation-id="41"]')).toBeVisible();
  await selectReaderText(page);
  await page.getByPlaceholder("边读边记…").fill("Selection-backed note");
  await page.getByRole("button", { name: "保存笔记" }).click();
  await expect(page.getByText("笔记已保存", { exact: true })).toBeVisible();

  expect(submitted?.selected_text).toBe("Evidence persists.");
  const anchor = submitted?.anchor as Record<string, unknown>;
  expect(anchor.exact).toBe("Evidence persists.");
  expect(anchor.kind).toBe("text-quote");
});

test("selection anchor survives Escape pressed during IME composition", async ({ page }) => {
  await resetFixtures(page);
  let submitted: Record<string, unknown> | null = null;
  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        annotation: {
          id: 44,
          article_id: 7,
          type: "annotation",
          selected_text: submitted.selected_text,
          content: submitted.content,
          color: submitted.color,
          tags: [],
          anchor: submitted.anchor,
          created_at: "2026-07-26T00:00:00Z",
          next_review_at: null,
          interval_days: 1,
          review_count: 0,
        },
      }),
    });
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.locator('mark[data-annotation-id="41"]')).toBeVisible();
  await selectReaderText(page);
  const toolbar = page.getByRole("toolbar", { name: "选中文字操作" });
  await expect(toolbar).toBeVisible();

  // Escape during IME composition cancels the composition, not the selection.
  await page.evaluate(() => {
    document.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", isComposing: true, bubbles: true }),
    );
  });
  await expect(toolbar).toBeVisible();

  await page.getByRole("button", { name: "保存划线" }).click();
  await expect(page.getByText("已保存划线", { exact: true })).toBeVisible();
  const anchor = (submitted?.anchor ?? null) as Record<string, unknown> | null;
  expect(anchor).not.toBeNull();
  expect(anchor?.kind).toBe("text-quote");
  expect(anchor?.exact).toBe("Evidence persists.");
});

test("annotation save 503 shows explicit retry and recovers without losing the selection", async ({ page }) => {
  await resetFixtures(page);
  let postCount = 0;
  let lastAnchor: unknown = null;
  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    postCount += 1;
    const body = route.request().postDataJSON() as Record<string, unknown>;
    lastAnchor = body.anchor;
    if (postCount === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "annotation_unavailable", message: "标注保存暂不可用，请重试。" } }),
      });
      return;
    }
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        annotation: {
          id: 60,
          article_id: 7,
          type: "annotation",
          selected_text: body.selected_text,
          content: body.content,
          color: body.color,
          tags: [],
          anchor: body.anchor,
          created_at: "2026-07-27T00:00:00Z",
          next_review_at: null,
          interval_days: 1,
          review_count: 0,
        },
      }),
    });
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.locator('mark[data-annotation-id="41"]')).toBeVisible();

  await selectReaderText(page);
  const toolbar = page.getByRole("toolbar", { name: "选中文字操作" });
  await expect(toolbar).toBeVisible();
  await page.getByRole("button", { name: "保存划线" }).click();

  await expect(page.getByText("划线保存失败")).toBeVisible();
  const retryButton = page.getByRole("button", { name: "重试保存" });
  await expect(retryButton).toBeVisible();
  await expect(toolbar).toBeVisible();

  await retryButton.click();
  await expect(page.getByText("已保存划线", { exact: true })).toBeVisible();
  expect(postCount).toBe(2);
  const anchor = lastAnchor as Record<string, unknown> | null;
  expect(anchor).not.toBeNull();
  expect(anchor?.kind).toBe("text-quote");
  expect(anchor?.exact).toBe("Evidence persists.");
  await expect(page.locator('mark[data-annotation-id="60"]')).toBeVisible();
});

test("new selection invalidates a stale annotation retry after save failure", async ({ page }) => {
  await resetFixtures(page);
  let postCount = 0;
  let submitted: Record<string, unknown> | null = null;
  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    postCount += 1;
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "annotation_unavailable", message: "标注保存暂不可用，请重试。" } }),
    });
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.locator('mark[data-annotation-id="41"]')).toBeVisible();

  await selectReaderText(page);
  const toolbar = page.getByRole("toolbar", { name: "选中文字操作" });
  await expect(toolbar).toBeVisible();
  await page.getByRole("button", { name: "保存划线" }).click();
  await expect(page.getByText("划线保存失败")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试保存" })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(toolbar).toBeHidden();
  await selectReaderParagraph(page, "Evidence should survive navigation.");
  await expect(toolbar).toBeVisible();
  await expect(page.getByRole("button", { name: "保存划线" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重试保存" })).toHaveCount(0);

  expect(postCount).toBe(1);
  expect(submitted?.selected_text).toBe("Evidence persists.");
});

test("selection save round-trips the anchor through POST and renders the highlight", async ({ page }) => {
  await resetFixtures(page);
  let submitted: Record<string, unknown> | null = null;
  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        annotation: {
          id: 61,
          article_id: 7,
          type: "annotation",
          selected_text: submitted.selected_text,
          content: submitted.content,
          color: submitted.color,
          tags: [],
          anchor: submitted.anchor,
          created_at: "2026-07-27T00:00:00Z",
          next_review_at: null,
          interval_days: 1,
          review_count: 0,
        },
      }),
    });
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.locator('mark[data-annotation-id="41"]')).toBeVisible();
  await selectReaderText(page);
  const toolbar = page.getByRole("toolbar", { name: "选中文字操作" });
  await expect(toolbar).toBeVisible();
  await page.getByRole("button", { name: "保存划线" }).click();
  await expect(page.getByText("已保存划线", { exact: true })).toBeVisible();

  expect(submitted?.selected_text).toBe("Evidence persists.");
  const anchor = submitted?.anchor as Record<string, unknown>;
  expect(anchor.exact).toBe("Evidence persists.");
  expect(anchor.kind).toBe("text-quote");
  await expect(page.locator('mark[data-annotation-id="61"]')).toBeVisible();
});

test("session switch isolates annotations between users", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.locator('mark[data-annotation-id="41"]')).toBeVisible();

  await selectReaderText(page);
  await expect(page.getByRole("toolbar", { name: "选中文字操作" })).toBeVisible();
  await page.getByRole("button", { name: "保存划线" }).click();
  await expect(page.getByText("已保存划线", { exact: true })).toBeVisible();
  await expect(page.locator('mark[data-annotation-id="60"]')).toBeVisible();

  await page.request.post("/api/auth/login");
  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.getByText("Babbage", { exact: true })).toBeVisible();
  await expect(page.locator('mark[data-annotation-id="41"]')).toBeVisible();
  await expect(page.locator('mark[data-annotation-id="60"]')).toHaveCount(0);
});

test("two browser contexts isolate annotations without cross-context leakage", async ({ browser }) => {
  const contextA = await browser.newContext();
  const pageA = await contextA.newPage();
  const contextB = await browser.newContext();
  const pageB = await contextB.newPage();

  await resetFixtures(pageA);
  await pageA.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(pageA.locator('mark[data-annotation-id="41"]')).toBeVisible();
  await selectReaderText(pageA);
  await expect(pageA.getByRole("toolbar", { name: "选中文字操作" })).toBeVisible();
  await pageA.getByRole("button", { name: "保存划线" }).click();
  await expect(pageA.getByText("已保存划线", { exact: true })).toBeVisible();
  await expect(pageA.locator('mark[data-annotation-id="60"]')).toBeVisible();

  await pageA.request.post("/api/auth/login");
  await pageB.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(pageB.getByText("Babbage", { exact: true })).toBeVisible();
  await expect(pageB.locator('mark[data-annotation-id="41"]')).toBeVisible();
  await expect(pageB.locator('mark[data-annotation-id="60"]')).toHaveCount(0);

  await contextA.close();
  await contextB.close();
});

test("refreshed repeated annotations restore only the context-proven quote and surface ambiguity", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/read/7?module=all&sort=default&lang=zh&fixture=annotation-repeated");

  const intendedParagraph = page.locator(".focusContent p").nth(1);
  await expect(intendedParagraph.locator('mark[data-annotation-id="51"]')).toHaveText("Repeated evidence.");
  await expect(page.locator(".focusContent p").first().locator('mark[data-annotation-id="51"]')).toHaveCount(0);
  await expect(page.getByText(/未安全定位/)).toHaveCount(0);

  await page.goto("/read/7?module=all&sort=default&lang=zh&fixture=annotation-ambiguous");
  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await expect(page.locator('mark[data-annotation-id="52"]')).toHaveCount(0);
  await expect(page.getByText(/有 1 条已保存划线因内容变化未安全定位/)).toBeVisible();
  await expect(page.locator(".focusContent")).toContainText("Repeated evidence.");
});

test("inline-markup annotation anchors remain visible but unresolved rather than wrapping partial markup", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/read/7?module=all&sort=default&lang=zh&fixture=annotation-inline-markup");

  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await expect(page.locator(".focusContent")).toContainText("Structured evidence survives refresh.");
  await expect(page.locator('mark[data-annotation-id="53"]')).toHaveCount(0);
  await expect(page.getByText(/有 1 条已保存划线因内容变化未安全定位/)).toBeVisible();
  await page.getByText("查看保留的未定位标注（1）", { exact: true }).click();
  await expect(page.getByText("Keep the structured evidence note.", { exact: true })).toBeVisible();
});

for (const viewport of [
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
]) {
  test(`mobile Agent and Toast avoid bottom-navigation overlap at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await resetFixtures(page);
    await page.goto("/read/7?module=all&sort=default&lang=zh");
    await expect(page.locator(".toastHost")).toBeAttached();
    await page.evaluate(
      () => new Promise<void>((resolve) => window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()))),
    );
    await page.getByRole("button", { name: /文章助手/ }).click();
    await expect(page.locator(".agentDrawer")).toHaveClass(/agentDrawerOpen/);
    await page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent("ai-reader:toast", { detail: { title: "移动布局检查", variant: "info" } }),
      );
    });
    await expect(page.getByText("移动布局检查", { exact: true })).toBeVisible();

    const geometry = await page.evaluate(() => {
      const toast = document.querySelector<HTMLElement>(".toastCard")!.getBoundingClientRect();
      const agent = document.querySelector<HTMLElement>(".agentDrawer")!.getBoundingClientRect();
      const navigation = document.querySelector<HTMLElement>(".mobileBottomNav")!.getBoundingClientRect();
      return {
        toastBottom: toast.bottom,
        agentTop: agent.top,
        agentBottom: agent.bottom,
        navigationTop: navigation.top,
        horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      };
    });
    expect(geometry.toastBottom).toBeLessThanOrEqual(geometry.agentTop + 0.1);
    expect(geometry.agentBottom).toBeLessThanOrEqual(geometry.navigationTop);
    expect(geometry.horizontalOverflow).toBe(false);
  });
}

test("article shortcuts only apply when the article list owns focus", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=all");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();

  const sortButton = page.getByRole("button", { name: /排序/ });
  await sortButton.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("listbox", { name: "排序方式" })).toBeVisible();
  await expect(page).toHaveURL(/\?module=all/);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("listbox", { name: "排序方式" })).toHaveCount(0);

  const list = page.locator(".articleList");
  await list.focus();
  await page.keyboard.press("j");
  await expect(page.getByRole("link", { name: /Keyboard article two/ })).toHaveAttribute("aria-current", "true");
});

test("article links and command input retain native keyboard behavior", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=all");
  const articleLink = page.getByRole("link", { name: /Keyboard article one/ });
  await articleLink.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/read\/7\?module=all/);

  await page.goto("/?module=all");
  await expect(page.getByRole("link", { name: /Keyboard article one/ })).toBeVisible();
  await page.keyboard.press("Meta+k");
  const input = page.getByRole("textbox");
  await expect(input).toBeFocused();
  await page.keyboard.type("search phrase");
  await expect(input).toHaveValue("search phrase");

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await page.getByRole("button", { name: /文章助手/ }).click();
  const question = page.getByPlaceholder("问当前文章...");
  await question.fill("keep this editor input");
  await expect(question).toHaveValue("keep this editor input");
});

test("later-page article return restores cursor page and its highlighted card", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=all");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "下一页 ›" }).click();
  await expect(page.getByText("Cursor article two", { exact: true })).toBeVisible();
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/trail=/);

  await page.getByRole("link", { name: /Cursor article two/ }).click();
  await expect(page).toHaveURL(/\/read\/9\?.*trail=/);
  await page.getByRole("link", { name: "返回工作台" }).click();

  await expect(page).toHaveURL(/article=9/);
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  const returnedCard = page.getByRole("link", { name: /Cursor article two/ });
  await expect(returnedCard).toHaveClass(/articleCardReturnTarget/);
});

test("scan mode paging failure hides stale cards and retries the current cursor", async ({ page }) => {
  await setCraftPreferences(page, { mode: "scan" });
  await resetFixtures(page);
  let pageTwoRequests = 0;
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/articles" && url.searchParams.get("cursor") === "cursor-page-2") {
      pageTwoRequests += 1;
    }
  });

  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await page.request.post("/__e2e/article-list/fail-once");
  const nextPage = page.getByRole("button", { name: "下一页 ›" });
  await nextPage.focus();
  await nextPage.press("Enter");

  const errorStatus = page.getByText("文章加载失败", { exact: true });
  const retryButton = page.getByRole("button", { name: "重试" });
  await expect(errorStatus).toBeVisible();
  await expect(retryButton).toBeFocused();
  await expect(page.getByText("Keyboard article one", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Keyboard article two", { exact: true })).toHaveCount(0);
  const viewport = await page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight }));
  for (const target of [errorStatus, retryButton]) {
    const bounds = await target.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.y).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width);
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(viewport.height);
  }
  await expect(page).toHaveURL(/trail=/);
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.readerMode)).toBe("scan");

  await retryButton.click();
  const articleList = page.locator("ul.articleList");
  await expect(page.getByText("Cursor article two", { exact: true })).toBeVisible();
  await expect(articleList).toBeFocused();
  await expect(page.getByText("文章加载失败", { exact: true })).toHaveCount(0);
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  expect(pageTwoRequests).toBe(2);
});

test("scan mode error offers a previous-page escape", async ({ page }) => {
  await setCraftPreferences(page, { mode: "scan" });
  await resetFixtures(page);
  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await page.request.post("/__e2e/article-list/fail-once");
  await page.getByRole("button", { name: "下一页 ›" }).click();

  await expect(page.getByText("文章加载失败", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "‹ 上一页" }).click();
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await expect(page.getByText("第 1 页", { exact: true })).toBeVisible();
  await expect(page).not.toHaveURL(/trail=/);
});

test("scan mode shows empty only after a successful empty response", async ({ page }) => {
  await setCraftPreferences(page, { mode: "scan" });
  await resetFixtures(page);
  let releaseEmptyResponse: (() => void) | null = null;
  const emptyResponseGate = new Promise<void>((resolve) => {
    releaseEmptyResponse = resolve;
  });
  await page.route("**/api/articles?**", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("module") !== "all" || url.searchParams.has("cursor")) {
      await route.fallback();
      return;
    }
    await emptyResponseGate;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], next_cursor: null, has_more: false }),
    });
  });

  const navigation = page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByLabel("文章加载中")).toBeVisible();
  await expect(page.getByText("暂无文章", { exact: true })).toHaveCount(0);
  await expect(page.getByText("文章加载失败", { exact: true })).toHaveCount(0);
  releaseEmptyResponse!();
  await navigation;

  await expect(page.getByLabel("文章加载中")).toHaveCount(0);
  await expect(page.getByText("暂无文章", { exact: true })).toBeVisible();
  await expect(page.getByText("当前模块没有可显示的文章。", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.readerMode)).toBe("scan");
});

test("scan mode restores direct pagination Back from the URL", async ({ page }) => {
  await setCraftPreferences(page, { mode: "scan" });
  await resetFixtures(page);
  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "下一页 ›" }).click();
  await expect(page.getByText("Cursor article two", { exact: true })).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/\/?module=all&sort=default&lang=zh$/);
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await expect(page.getByText("Cursor article two", { exact: true })).toHaveCount(0);
  await expect(page.getByText("第 1 页", { exact: true })).toBeVisible();
});

test("scan mode restores later-page context after return reload and browser Back", async ({ page }) => {
  await setCraftPreferences(page, { mode: "scan" });
  await resetFixtures(page);
  await page.goto("/?module=all&sort=latest&lang=original&q=fixture");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "下一页 ›" }).click();
  await expect(page.getByText("Cursor article two", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: /Cursor article two/ }).click();
  await expect(page).toHaveURL(/\/read\/9\?.*module=all.*sort=latest.*lang=original.*q=fixture.*trail=/);

  await page.getByRole("link", { name: "返回工作台" }).click();
  await expect(page).toHaveURL(/module=all.*sort=latest.*lang=original.*q=fixture.*trail=.*article=9/);
  const returnedCard = page.getByRole("link", { name: /Cursor article two/ });
  await expect(returnedCard).toHaveClass(/articleCardReturnTarget/);

  await page.reload();
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Cursor article two/ })).toHaveClass(/articleCardReturnTarget/);
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.readerMode)).toBe("scan");

  await page.getByRole("link", { name: /Cursor article two/ }).click();
  await expect(page).toHaveURL(/\/read\/9\?/);
  await page.goBack();
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Cursor article two/ })).toBeVisible();
  await expect(page).toHaveURL(/module=all.*sort=latest.*lang=original.*q=fixture.*trail=.*article=9/);
});

test("focus mode paging failure hides stale cards and retries the current cursor", async ({ page }) => {
  await setCraftPreferences(page, { mode: "focus" });
  await resetFixtures(page);
  let pageTwoRequests = 0;
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/articles" && url.searchParams.get("cursor") === "focus-cursor-page-2") {
      pageTwoRequests += 1;
    }
  });

  await page.goto("/?module=all&sort=score&lang=original&q=focus-fixture");
  await expect(page.getByText("Focus article one", { exact: true })).toBeVisible();
  await page.request.post("/__e2e/article-list/fail-once");
  const nextPage = page.getByRole("button", { name: "下一页 ›" });
  await nextPage.focus();
  await nextPage.press("Enter");

  const errorStatus = page.getByText("文章加载失败", { exact: true });
  const retryButton = page.getByRole("button", { name: "重试" });
  await expect(errorStatus).toBeVisible();
  await expect(retryButton).toBeFocused();
  await expect(page.getByText("Focus article one", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Focus article two", { exact: true })).toHaveCount(0);
  await expect(page).toHaveURL(/module=all.*sort=score.*lang=original.*q=focus-fixture.*trail=/);
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.readerMode)).toBe("focus");

  await retryButton.click();
  const articleList = page.locator("ul.articleList");
  await expect(page.getByText("Focus cursor article", { exact: true })).toBeVisible();
  await expect(articleList).toBeFocused();
  await expect(page.getByText("文章加载失败", { exact: true })).toHaveCount(0);
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  expect(pageTwoRequests).toBe(2);
});

test("focus mode error offers a previous-page escape", async ({ page }) => {
  await setCraftPreferences(page, { mode: "focus" });
  await resetFixtures(page);
  await page.goto("/?module=all&sort=score&lang=original&q=focus-fixture");
  await expect(page.getByText("Focus article one", { exact: true })).toBeVisible();
  await page.request.post("/__e2e/article-list/fail-once");
  await page.getByRole("button", { name: "下一页 ›" }).click();

  await expect(page.getByText("文章加载失败", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "‹ 上一页" }).click();
  await expect(page.getByText("Focus article one", { exact: true })).toBeVisible();
  await expect(page.getByText("第 1 页", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/module=all.*sort=score.*lang=original.*q=focus-fixture$/);
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.readerMode)).toBe("focus");
});

test("focus mode shows empty only after a successful empty response", async ({ page }) => {
  await setCraftPreferences(page, { mode: "focus" });
  await resetFixtures(page);
  let releaseEmptyResponse: (() => void) | null = null;
  const emptyResponseGate = new Promise<void>((resolve) => {
    releaseEmptyResponse = resolve;
  });
  await page.route("**/api/articles?**", async (route) => {
    const url = new URL(route.request().url());
    if (
      url.searchParams.get("module") !== "all" ||
      url.searchParams.has("cursor") ||
      url.searchParams.get("q") !== "focus-empty"
    ) {
      await route.fallback();
      return;
    }
    await emptyResponseGate;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], next_cursor: null, has_more: false }),
    });
  });

  const navigation = page.goto("/?module=all&sort=score&lang=original&q=focus-empty");
  await expect(page.getByLabel("文章加载中")).toBeVisible();
  await expect(page.getByText("暂无文章", { exact: true })).toHaveCount(0);
  await expect(page.getByText("文章加载失败", { exact: true })).toHaveCount(0);
  releaseEmptyResponse!();
  await navigation;

  await expect(page.getByLabel("文章加载中")).toHaveCount(0);
  await expect(page.getByText("暂无文章", { exact: true })).toBeVisible();
  await expect(page.getByText("当前模块没有可显示的文章。", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.readerMode)).toBe("focus");
});

test("focus mode restores direct pagination Back from the URL", async ({ page }) => {
  await setCraftPreferences(page, { mode: "focus" });
  await resetFixtures(page);
  await page.goto("/?module=all&sort=score&lang=original&q=focus-fixture");
  await expect(page.getByText("Focus article one", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "下一页 ›" }).click();
  await expect(page.getByText("Focus cursor article", { exact: true })).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/module=all.*sort=score.*lang=original.*q=focus-fixture$/);
  await expect(page.getByText("Focus article one", { exact: true })).toBeVisible();
  await expect(page.getByText("Focus cursor article", { exact: true })).toHaveCount(0);
  await expect(page.getByText("第 1 页", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.readerMode)).toBe("focus");
});

test("focus mode restores later-page context after return reload and browser Back", async ({ page }) => {
  await setCraftPreferences(page, { mode: "focus" });
  await resetFixtures(page);
  await page.goto("/?module=all&sort=score&lang=original&q=focus-fixture");
  await expect(page.getByText("Focus article one", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "下一页 ›" }).click();
  await expect(page.getByText("Focus cursor article", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: /Focus cursor article/ }).click();
  await expect(page).toHaveURL(/\/read\/13\?.*module=all.*sort=score.*lang=original.*q=focus-fixture.*trail=/);

  await page.getByRole("link", { name: "返回工作台" }).click();
  await expect(page).toHaveURL(/module=all.*sort=score.*lang=original.*q=focus-fixture.*trail=.*article=13/);
  const returnedCard = page.getByRole("link", { name: /Focus cursor article/ });
  await expect(returnedCard).toHaveClass(/articleCardReturnTarget/);

  await page.reload();
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Focus cursor article/ })).toHaveClass(/articleCardReturnTarget/);
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.readerMode)).toBe("focus");

  await page.getByRole("link", { name: /Focus cursor article/ }).click();
  await expect(page).toHaveURL(/\/read\/13\?/);
  await page.goBack();
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Focus cursor article/ })).toBeVisible();
  await expect(page).toHaveURL(/module=all.*sort=score.*lang=original.*q=focus-fixture.*trail=.*article=13/);
});

test("search URL state ignores slow results after a newer query", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=search&filter=all&sort=default&q=slow");
  const query = page.getByLabel("关键词");
  await expect(query).toHaveValue("slow");
  await query.fill("fast");
  await query.press("Enter");

  await expect(page).toHaveURL(/module=search.*q=fast/);
  const fastResult = page.getByRole("link", { name: "Fast search result" }).first();
  await expect(fastResult).toBeVisible();
  await expect(fastResult).toHaveAttribute("href", /module=search.*filter=all.*sort=default.*q=fast/);
  await page.waitForTimeout(450);
  await expect(page.getByText("Slow search result", { exact: true })).toHaveCount(0);

  await page.goBack();
  await expect(page).toHaveURL(/module=search.*q=slow/);
  await expect(query).toHaveValue("slow");
  await expect(page.getByText("Slow search result", { exact: true }).first()).toBeVisible();
  await page.goForward();
  await expect(page).toHaveURL(/module=search.*q=fast/);
  await expect(query).toHaveValue("fast");
  await expect(page.getByText("Fast search result", { exact: true }).first()).toBeVisible();
});

test("research job URL restores after reload and citation return", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=research&sort=default&lang=zh&job=88");
  await expect(page.getByText("优先跟进检索质量。", { exact: true })).toBeVisible();
  await expect(page.getByText(/job #88 · succeeded · mock/)).toBeVisible();

  await page.reload();
  await expect(page.getByText("优先跟进检索质量。", { exact: true })).toBeVisible();
  const citation = page.getByRole("link", { name: /Keyboard article one/ });
  await expect(citation).toHaveAttribute("href", /module=research.*job=88.*quote=/);
  await citation.click();
  await expect(page).toHaveURL(/\/read\/7\?.*module=research.*job=88/);
  await page.getByRole("link", { name: "返回工作台" }).click();
  await expect(page).toHaveURL(/module=research.*job=88/);
  await expect(page.getByText("优先跟进检索质量。", { exact: true })).toBeVisible();
});

test("starting research writes the durable job URL", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=research&sort=default&lang=zh");
  await page.getByRole("button", { name: "启动研究" }).click();

  await expect(page).toHaveURL(/module=research.*job=88/);
  await expect(page.getByText("优先跟进检索质量。", { exact: true })).toBeVisible();
});

test("failed research preserves its question and retries into a new durable job", async ({ page }) => {
  const errors = captureUnexpectedBrowserErrors(page);
  await resetFixtures(page);
  await page.request.post("/__e2e/research/fail-once");
  await page.goto("/?module=research&sort=default&lang=zh");

  const question = page.getByRole("textbox", { name: "问题" });
  await question.fill("哪些恢复路径仍需验证？");
  await page.getByRole("button", { name: "启动研究" }).click();

  await expect(page).toHaveURL(/module=research.*job=90/);
  const researchError = page.getByText("研究 provider 超时，请重试", { exact: true });
  await expect(researchError).toBeVisible();
  await expect(researchError).toHaveAttribute("role", "alert");
  await expect(question).toHaveValue("哪些恢复路径仍需验证？");
  await page.getByRole("button", { name: "重试研究" }).click();

  await expect(page).toHaveURL(/module=research.*job=88/);
  await expect(page.getByText("优先跟进检索质量。", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Keyboard article one/ })).toBeVisible();
  expect(errors).toEqual([]);
});

test("workbench failure does not render a contradictory empty state", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=all&sort=default&lang=zh&q=workbench-error");

  await expect(page.getByText(/文章加载失败/)).toBeVisible();
  await expect(page.getByText("暂无文章", { exact: true })).toHaveCount(0);
});

test("starred module shows empty state when no articles are saved", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await page.goto("/?module=starred&sort=default&lang=zh");
  await expect(page.getByText("暂无文章", { exact: true })).toBeVisible();
  await expect(page.getByText("当前模块没有可显示的文章。", { exact: true })).toBeVisible();
});

test("starred module renders saved articles from the server", async ({ page }) => {
  await resetFixtures(page);
  await page.route("**/api/articles?**", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("module") !== "starred") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [{
          id: 7,
          title: "Keyboard article one",
          url: "https://example.com/one",
          feed: { id: 1, title: "Fixture feed" },
          category: null,
          published_at: "2026-07-21T00:00:00Z",
          content_quality: "full",
          summary_zh: "第一篇测试文章。",
          score: null,
          state: { status: "unread", saved: true, project: false, read_progress: 0 },
        }],
        next_cursor: null,
        has_more: false,
      }),
    });
  });
  await page.goto("/?module=starred&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await expect(page.getByText("暂无文章", { exact: true })).toHaveCount(0);
});

test("article list failure shows error with retry and recovers", async ({ page }) => {
  await resetFixtures(page);
  await page.request.post("/__e2e/article-list/fail-once");
  await page.goto("/?module=all&sort=default&lang=zh");

  await expect(page.getByText(/文章加载失败/)).toBeVisible();
  await expect(page.getByText("暂无文章", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "重试" }).click();
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await expect(page.getByText(/文章加载失败/)).toHaveCount(0);
});

test("state language never contradicts itself across modules", async ({ page }) => {
  await resetFixtures(page);

  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await expect(page.getByText(/文章加载失败/)).toHaveCount(0);
  await expect(page.getByText("暂无文章", { exact: true })).toHaveCount(0);

  await page.request.post("/__e2e/article-list/fail-once");
  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText(/文章加载失败/)).toBeVisible();
  await expect(page.getByText("暂无文章", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Keyboard article one", { exact: true })).toHaveCount(0);

  await page.goto("/?module=starred&sort=default&lang=zh");
  await expect(page.getByText("暂无文章", { exact: true })).toBeVisible();
  await expect(page.getByText(/文章加载失败/)).toHaveCount(0);

  await page.goto("/?module=review&sort=default&lang=zh");
  await expect(page.getByText("A durable note returns when it matters.", { exact: true })).toBeVisible();
  await expect(page.getByText(/复习队列暂不可用/)).toHaveCount(0);
  await expect(page.getByText("今天没有到期划线", { exact: true })).toHaveCount(0);
});

test("review queue failure shows error with retry and recovers", async ({ page }) => {
  await resetFixtures(page);
  await page.request.post("/__e2e/review/fail-once");
  await page.goto("/?module=review&sort=default&lang=zh");

  await expect(page.getByText(/复习队列暂不可用/)).toBeVisible();
  await page.getByRole("button", { name: "重试" }).click();
  await expect(page.getByText("A durable note returns when it matters.", { exact: true })).toBeVisible();
  await expect(page.getByText(/复习队列暂不可用/)).toHaveCount(0);
});

test("export panel downloads project markdown", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=export&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "立项导出" })).toBeVisible();

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Markdown" }).click(),
  ]);
  expect(download.suggestedFilename()).toContain("project-export");
  await expect(page.getByText(/已下载/)).toBeVisible();
});

test("focused reader exposes retry for an article load failure", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/read/999?module=all&sort=default&lang=zh");

  await expect(page.getByText("文章加载失败", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "重试加载" })).toBeVisible();
});

test("Daily Intelligence labels failed sources instead of false empty states", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=home&sort=default&lang=zh&fixture=daily-error");

  await expect(page.getByRole("button", { name: "刷新情报" })).toBeVisible();
  await expect(page.getByText(/加载失败：/).first()).toBeVisible();
  await expect(page.getByText("暂无条目", { exact: true })).toHaveCount(0);
});

test("Daily Intelligence preserves usable research context through a secondary-source retry", async ({ page }) => {
  const errors = captureUnexpectedBrowserErrors(page);
  await resetFixtures(page);
  await page.request.post("/__e2e/daily/clusters-fail-once");
  await page.goto("/?module=home&sort=default&lang=zh");

  await expect(page.getByRole("heading", { name: "今日研究简报" })).toBeVisible();
  const article = page.getByRole("link", { name: "Durable research workflows" });
  await expect(article).toBeVisible();
  await expect(page.getByText(/主题簇加载失败：/)).toBeVisible();

  await page.getByRole("button", { name: "刷新情报" }).click();
  await expect(page.getByText(/主题簇加载失败：/)).toHaveCount(0);
  await expect(page.getByRole("link", { name: /可恢复研究工作流/ })).toBeVisible();
  await expect(article).toBeVisible();

  await article.click();
  await expect(page).toHaveURL(/\/read\/7\?.*module=home/);
  await page.getByRole("link", { name: "返回工作台" }).click();
  await expect(page).toHaveURL(/module=home/);
  await expect(page.getByRole("heading", { name: "今日研究简报" })).toBeVisible();
  // Chromium reports the intentionally injected one-time 500 as a console error.
  // Keeping this exact allowlist proves that no second unexpected console/page error leaked.
  expect(errors).toEqual([
    "console: Failed to load resource: the server responded with a status of 500 (Internal Server Error)",
  ]);
});

test("Reader keeps article context when Ask fails once and then retries", async ({ page }) => {
  const errors = captureUnexpectedBrowserErrors(page);
  await resetFixtures(page);
  await page.request.post("/__e2e/article-ask/fail-once");
  await page.goto("/read/7?module=home&sort=default&lang=zh");

  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await expect(page.getByText("Evidence should survive navigation.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /文章助手/ }).click();
  await page.getByRole("button", { name: "总结", exact: true }).click();
  await expect(page.getByText("文章助手暂不可用，请重试。", { exact: true })).toBeVisible();
  await expect(page.getByText("Evidence should survive navigation.", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "总结", exact: true }).click();
  await expect(page.getByText("E2E grounded answer.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Evidence should survive navigation/ })).toBeVisible();
  expect(errors).toEqual([
    "console: Failed to load resource: the server responded with a status of 503 (Service Unavailable)",
  ]);
});

test("Ask abort via 停止 returns to a clean state without error", async ({ page }) => {
  await resetFixtures(page);
  await page.route("**/api/articles/7/ask", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 3000));
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: 'data: {"type":"answer","content":"Late answer"}\n\ndata: {"type":"done"}\n\n',
    });
  });

  await page.goto("/read/7?module=home&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await page.getByRole("button", { name: /文章助手/ }).click();
  await page.getByRole("button", { name: "总结", exact: true }).click();

  await expect(page.getByRole("button", { name: "停止" })).toBeVisible();
  await page.getByRole("button", { name: "停止" }).click();

  await expect(page.getByRole("button", { name: "停止" })).toHaveCount(0);
  await expect(page.getByText("Late answer")).toHaveCount(0);
  await expect(page.getByText(/文章助手暂不可用/)).toHaveCount(0);
});

test("Reader preserves article context through a failed candidate write and retries to server-confirmed state", async ({ page }) => {
  const errors = captureUnexpectedBrowserErrors(page);
  await resetFixtures(page);
  await page.request.post("/__e2e/article-state/fail-once");
  await page.goto("/read/7?module=home&sort=default&lang=zh");

  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await expect(page.getByText("Evidence should survive navigation.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "更多文章操作" }).click();
  await page.getByRole("menuitem", { name: "加入候选" }).click();
  await expect(page.getByText("状态更新暂不可用，请重试。", { exact: true })).toBeVisible();
  await expect(page.getByText("Evidence should survive navigation.", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "重试操作" }).click();
  await expect(page.getByText("状态更新暂不可用，请重试。", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "更多文章操作" }).click();
  await expect(page.getByRole("menuitem", { name: "移出候选" })).toBeVisible();
  expect(errors).toEqual([
    "console: Failed to load resource: the server responded with a status of 503 (Service Unavailable)",
  ]);
});

test("continue-reading route uses actual partial progress rather than candidate state", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=read-later&sort=default&lang=zh");

  await expect(page.getByText("Unsaved in-progress article", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "继续阅读" }).first()).toBeVisible();
});

test("Admin usage failure is isolated and can retry without hiding pipeline", async ({ page }) => {
  await resetFixtures(page);
  await page.request.post("/__e2e/admin/usage-fail-once");
  await page.goto("/?module=admin&sort=default&lang=zh");

  const usageError = page.getByText(/费用加载失败：/);
  await expect(usageError).toBeVisible();
  await expect(page.getByText("调度常开 · 健康", { exact: true })).toBeVisible();
  await expect(page.getByText("2 篇待评分", { exact: true })).toBeVisible();
  await usageError.getByRole("button", { name: "重试" }).click();
  await expect(page.getByText(/Score 0\/60/)).toBeVisible();
  await expect(usageError).toHaveCount(0);
});

test("Admin terminal sync refreshes affected snapshot cards", async ({ page }) => {
  await resetFixtures(page);
  await page.request.post("/__e2e/admin");
  await page.goto("/?module=admin&sort=default&lang=zh");
  await expect(page.getByText("2 篇待评分", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "启动同步" }).click();
  await expect(page.getByText("同步 job #89 succeeded", { exact: true })).toBeVisible();
  await expect(page.getByText("3 篇待评分", { exact: true })).toBeVisible();
  await expect(page.getByText("排队 0", { exact: false })).toBeVisible();
});

test("search retains article results when annotation search fails", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=search&filter=all&sort=default&q=partial");
  await expect(page.getByText("Partial search result", { exact: true })).toBeVisible();
  await expect(page.getByText(/划线\/笔记搜索失败：/)).toBeVisible();
});

test("search retains annotations when article search fails", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=search&filter=all&sort=default&q=annotations-only");
  await expect(page.getByText("Annotation-only result", { exact: true })).toBeVisible();
  await expect(page.getByText(/文章搜索失败：/)).toBeVisible();
});

test("mobile module drawer traps focus, inerts the background, and restores its trigger", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await resetFixtures(page);
  await page.goto("/?module=all");
  const trigger = page.getByRole("button", { name: "打开阅读模块" });
  await trigger.click();
  const drawer = page.getByRole("dialog", { name: "阅读模块" });
  await expect(drawer).toBeVisible();
  await expect(page.locator(".workbenchMain")).toHaveJSProperty("inert", true);
  await expect(page.locator(".mobileBottomNav")).toHaveJSProperty("inert", true);

  const focusables = drawer.locator("a[href], button:not([disabled])");
  await focusables.last().focus();
  await page.keyboard.press("Tab");
  await expect.poll(() => drawer.evaluate((element) => element.contains(document.activeElement))).toBe(true);

  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("command palette inerts the app and restores prior focus after Escape", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=all");
  const sortButton = page.getByRole("button", { name: /排序/ });
  await sortButton.focus();
  await page.keyboard.press("Meta+k");
  const dialog = page.getByRole("dialog", { name: "命令面板" });
  await expect(dialog).toBeVisible();
  await expect(page.locator(".workbench")).toHaveJSProperty("inert", true);
  await expect(dialog.getByRole("textbox")).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(sortButton).toBeFocused();
});

test("sort listbox supports roving keys, selection, and Escape focus restoration", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=all");
  const trigger = page.getByRole("button", { name: /排序/ });
  await trigger.focus();
  await page.keyboard.press("ArrowDown");
  const listbox = page.getByRole("listbox", { name: "排序方式" });
  await expect(listbox).toBeVisible();
  await expect(page.getByRole("option", { name: "默认排序" })).toBeFocused();

  await page.keyboard.press("End");
  await expect(page.getByRole("option", { name: "按趋势" })).toBeFocused();
  await page.keyboard.press("Home");
  await expect(page.getByRole("option", { name: "默认排序" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("option", { name: "按最新" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/sort=latest/);

  await trigger.focus();
  await page.keyboard.press("ArrowDown");
  await expect(listbox).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(listbox).toBeHidden();
  await expect(trigger).toBeFocused();

  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("option", { name: "默认排序" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("option", { name: "按最新" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("option", { name: "按总分" })).toBeFocused();
  await page.keyboard.press(" ");
  await expect(page).toHaveURL(/sort=score/);
});

test("reader overflow menu supports roving keys and Escape focus restoration", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/read/7?module=all&sort=default&lang=zh");
  const trigger = page.getByRole("button", { name: "更多文章操作" });
  await expect(trigger).toBeVisible();
  await trigger.focus();
  await page.keyboard.press("ArrowDown");
  const menu = page.getByRole("menu", { name: "更多文章操作" });
  await expect(menu).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "刷新全文" })).toBeFocused();

  await page.keyboard.press("End");
  await expect(page.getByRole("menuitem", { name: "标记已读" })).toBeFocused();
  await page.keyboard.press("Home");
  await expect(page.getByRole("menuitem", { name: "刷新全文" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("dual-pane reader uses readable desktop columns at 1440px", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await enableNotesDualPane(page);
  await resetFixtures(page);
  await page.goto("/read/7?module=all&sort=default&lang=zh");
  const layout = page.locator(".focusReaderLayout");
  const notes = page.getByRole("complementary", { name: "笔记双栏" });
  await expect(notes).toBeVisible();
  await expect(page.locator(".focusReader")).toHaveClass(/focusReaderDualPane/);

  const geometry = await layout.evaluate((element) => {
    const primary = element.querySelector<HTMLElement>(".focusReaderPrimary")!;
    const secondary = element.querySelector<HTMLElement>(".focusedArticleNotes")!;
    const primaryBounds = primary.getBoundingClientRect();
    const secondaryBounds = secondary.getBoundingClientRect();
    return {
      display: getComputedStyle(element).display,
      primaryWidth: primaryBounds.width,
      secondaryWidth: secondaryBounds.width,
      secondaryLeft: secondaryBounds.left,
      primaryRight: primaryBounds.right,
    };
  });
  expect(geometry.display).toBe("grid");
  expect(geometry.primaryWidth).toBeGreaterThan(geometry.secondaryWidth);
  expect(geometry.secondaryLeft).toBeGreaterThanOrEqual(geometry.primaryRight);
});

test("dual-pane reader intentionally stacks notes after content at 899px", async ({ page }) => {
  await page.setViewportSize({ width: 899, height: 900 });
  await enableNotesDualPane(page);
  await resetFixtures(page);
  await page.goto("/read/7?module=all&sort=default&lang=zh");
  const layout = page.locator(".focusReaderLayout");
  const notes = page.getByRole("complementary", { name: "笔记双栏" });
  await expect(notes).toBeVisible();

  const geometry = await layout.evaluate((element) => {
    const primary = element.querySelector<HTMLElement>(".focusReaderPrimary")!;
    const secondary = element.querySelector<HTMLElement>(".focusedArticleNotes")!;
    const primaryBounds = primary.getBoundingClientRect();
    const secondaryBounds = secondary.getBoundingClientRect();
    return {
      display: getComputedStyle(element).display,
      secondaryTop: secondaryBounds.top,
      primaryBottom: primaryBounds.bottom,
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    };
  });
  expect(geometry.display).toBe("block");
  expect(geometry.secondaryTop).toBeGreaterThanOrEqual(geometry.primaryBottom - 0.1);
  expect(geometry.horizontalOverflow).toBe(false);
});

for (const viewport of [
  { width: 320, height: 568 },
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1024, height: 900 },
  { width: 1280, height: 960 },
  { width: 1440, height: 1000 },
]) {
  for (const mode of ["scan", "focus", "keep"] as const) {
    test(`${mode} mode remains navigable at ${viewport.width}px`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await setCraftPreferences(page, { mode });
      await resetFixtures(page);
      await page.goto("/?module=all");
      const articleLink = page.getByRole("link", { name: /Keyboard article one/ });
      await expect(articleLink).toBeVisible();
      await expect.poll(() => page.evaluate(() => document.documentElement.dataset.readerMode)).toBe(mode);
      await expect
        .poll(() => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth))
        .toBe(false);

      await articleLink.click();
      await expect(page).toHaveURL(/\/read\/7\?module=all/);
      await expect(page.getByRole("button", { name: "更多文章操作" })).toBeVisible();
    });
  }
}

test("Focus mode preserves desktop module navigation at 901px", async ({ page }) => {
  await page.setViewportSize({ width: 901, height: 900 });
  await resetFixtures(page);
  await page.goto("/?module=all");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await page.evaluate(() => {
    document.documentElement.dataset.readerMode = "focus";
  });

  const layout = await page.evaluate(() => {
    const sidebar = document.querySelector(".moduleSidebar");
    const bottomNav = document.querySelector(".mobileBottomNav");
    return {
      gridColumns: getComputedStyle(document.querySelector(".workbench")!).gridTemplateColumns,
      sidebarDisplay: sidebar == null ? "none" : getComputedStyle(sidebar).display,
      bottomNavDisplay: bottomNav == null ? "none" : getComputedStyle(bottomNav).display,
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    };
  });
  expect(layout.gridColumns.startsWith("0px")).toBe(false);
  expect(layout.sidebarDisplay).not.toBe("none");
  expect(layout.bottomNavDisplay).toBe("none");
  expect(layout.horizontalOverflow).toBe(false);
  await expect(page.getByRole("link", { name: "新到" })).toBeVisible();
});

test("Focus mode preserves a visible workbench column at the 899px breakpoint", async ({ page }) => {
  await page.setViewportSize({ width: 899, height: 900 });
  await resetFixtures(page);
  await page.goto("/?module=all");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await page.evaluate(() => {
    document.documentElement.dataset.readerMode = "focus";
  });

  const gridColumns = await page.locator(".workbench").evaluate((element) => getComputedStyle(element).gridTemplateColumns);
  expect(gridColumns.startsWith("0px")).toBe(false);
  const moduleTrigger = page.getByRole("button", { name: "打开阅读模块" });
  await expect(moduleTrigger).toBeVisible();
  await moduleTrigger.click();
  await expect(page.getByRole("dialog", { name: "阅读模块" })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth))
    .toBe(false);
});
