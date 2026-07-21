import { expect, test } from "@playwright/test";

async function resetFixtures(page: import("@playwright/test").Page) {
  await page.request.post("/__e2e/reset");
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
  const paragraph = page.locator(".focusContent p");
  await paragraph.scrollIntoViewIfNeeded();
  const box = await paragraph.boundingBox();
  if (box == null) throw new Error("E2E article fixture has no selectable text");
  const y = box.y + box.height / 2;
  await page.mouse.move(box.x + 1, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width - 1, y, { steps: 4 });
  await page.mouse.up();
}

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

test("clears cached article details when the authenticated user changes", async ({ context, page }) => {
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
    const response = await fetch("/api/articles/7");
    return { status: response.status, body: await response.json() };
  });
  await context.setOffline(false);

  expect(articleForBOffline).toMatchObject({ status: 503, body: { error: { code: "offline" } } });
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
  await expect(page.getByText(/已选中：user-a/)).toBeVisible();
  const agentGeometry = await page.evaluate(() => {
    const toast = document.querySelector<HTMLElement>(".toastCard")!.getBoundingClientRect();
    const agent = document.querySelector<HTMLElement>(".agentDrawer")!.getBoundingClientRect();
    return { toastBottom: toast.bottom, agentTop: agent.top };
  });
  expect(agentGeometry.toastBottom).toBeLessThanOrEqual(agentGeometry.agentTop + 0.1);
  });
}

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
  { width: 375, height: 812 },
  { width: 768, height: 1024 },
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
