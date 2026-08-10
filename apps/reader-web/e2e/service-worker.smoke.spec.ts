import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { compositeCssLayers, contrastRatio } from "./support/color";

async function resetFixtures(page: import("@playwright/test").Page) {
  await page.request.post("/__e2e/reset");
}

async function waitForSettledArticleList(page: import("@playwright/test").Page) {
  await expect(page.locator(".articleList")).not.toHaveClass(/articleListPaging/);
  await expect
    .poll(() =>
      page.locator(".articleList > li").evaluateAll((elements) =>
        elements.every((element) => Number(getComputedStyle(element).opacity) >= 0.99),
      ),
    )
    .toBe(true);
}

async function waitForSettledFocusReader(page: import("@playwright/test").Page) {
  await expect
    .poll(() =>
      page.locator("main.focusReader").evaluate((element) => Number(getComputedStyle(element).opacity) >= 0.99),
    )
    .toBe(true);
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

test("invalid read route waits for the auth gate before showing its error", async ({ page }) => {
  await resetFixtures(page);
  let authRequests = 0;
  let articleRequests = 0;
  await page.route("**/api/auth/me", async (route) => {
    authRequests += 1;
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "unauthorized", message: "Authentication required" } }),
    });
  });
  await page.route("**/api/articles/**", async (route) => {
    articleRequests += 1;
    await route.abort();
  });

  await page.goto("/read/abc?module=all&sort=default&lang=zh");

  await expect(page.getByRole("heading", { name: "登录 AI Reader" })).toBeVisible();
  await expect(page.getByText("文章不存在", { exact: true })).toHaveCount(0);
  expect(authRequests).toBeGreaterThan(0);
  expect(articleRequests).toBe(0);
});

test("authenticated invalid read route keeps session chrome without fetching an article", async ({ page }) => {
  await resetFixtures(page);
  let articleRequests = 0;
  await page.route("**/api/articles/**", async (route) => {
    articleRequests += 1;
    await route.abort();
  });

  await page.goto("/read/7.9?module=all&sort=default&lang=zh");

  await expect(page.getByLabel("当前会话")).toBeVisible();
  await expect(page.getByText("文章不存在", { exact: true })).toBeVisible();
  expect(articleRequests).toBe(0);
});

test("article 404 envelope renders not-found copy instead of generic load failure", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/read/999?module=all&sort=default&lang=zh");

  await expect(page.getByText("文章不存在", { exact: true })).toBeVisible();
  await expect(page.getByText("文章加载失败", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Article not found", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "重试加载" })).toBeVisible();
});

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

async function selectReaderParagraphWithMouse(page: import("@playwright/test").Page, text: string) {
  const paragraph = page.locator(".focusContent p").nth(1);
  await expect(paragraph).toHaveText(text, { exact: true });
  await paragraph.scrollIntoViewIfNeeded();
  const box = await paragraph.boundingBox();
  if (box == null) throw new Error("E2E article fixture has no second paragraph bounds");
  const y = box.y + box.height / 2;
  await page.mouse.move(box.x + 1, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width - 1, y, { steps: 4 });
  await page.mouse.up();
}

async function pressTabUntilFocused(
  page: import("@playwright/test").Page,
  target: import("@playwright/test").Locator,
  options: { reverse?: boolean; attempts?: number } = {},
) {
  const key = options.reverse ? "Shift+Tab" : "Tab";
  for (let index = 0; index < (options.attempts ?? 60); index += 1) {
    await page.keyboard.press(key);
    if (await target.evaluate((element) => element === document.activeElement).catch(() => false)) return;
  }
  throw new Error(`Keyboard focus did not reach ${await target.evaluate((element) => element.outerHTML)}`);
}

async function expectVisibleFocusContrast(
  target: import("@playwright/test").Locator,
  expectedTheme: "light" | "dark",
) {
  const focus = await target.evaluate(async (element, expectedTheme) => {
    const root = document.documentElement;
    const probe = document.createElement("span");
    probe.style.cssText =
      "position:fixed;pointer-events:none;visibility:hidden;background-color:var(--bg);width:0;height:0";
    document.body.append(probe);

    const readSurface = () => {
      const backgroundColors: string[] = [];
      const surfaces: Element[] = [];
      let surface = element.parentElement;
      while (surface != null) {
        const backgroundColor = getComputedStyle(surface).backgroundColor;
        surfaces.push(surface);
        if (backgroundColor !== "transparent") backgroundColors.push(backgroundColor);
        surface = surface.parentElement;
      }
      return {
        backgroundColors,
        surfaces,
        signature: JSON.stringify({
          theme: root.dataset.theme || "light",
          backgroundToken: getComputedStyle(root).getPropertyValue("--bg").trim(),
          resolvedBackgroundToken: getComputedStyle(probe).backgroundColor,
          bodyBackground: getComputedStyle(document.body).backgroundColor,
          backgroundColors,
        }),
      };
    };

    try {
      await new Promise<void>((resolve, reject) => {
        const startedAt = performance.now();
        let previousSignature = "";
        let stableFrames = 0;
        const check = () => {
          const sample = readSurface();
          const themeMatches = (root.dataset.theme || "light") === expectedTheme;
          const backgroundsMatch = sample.resolvedBackgroundToken === sample.bodyBackground;
          const backgroundsAnimating = sample.surfaces.some((surface) =>
            surface.getAnimations().some((animation) => animation.playState === "pending" || animation.playState === "running"),
          );
          stableFrames =
            themeMatches && backgroundsMatch && !backgroundsAnimating && sample.signature === previousSignature
              ? stableFrames + 1
              : 0;
          previousSignature = sample.signature;
          if (stableFrames >= 2) {
            resolve();
            return;
          }
          if (performance.now() - startedAt >= 5_000) {
            reject(new Error(`Theme surfaces did not settle: ${sample.signature}`));
            return;
          }
          requestAnimationFrame(check);
        };
        requestAnimationFrame(check);
      });

      const style = getComputedStyle(element);
      const surface = readSurface();
      const matchedFocusRules = Array.from(document.styleSheets).flatMap((sheet) => {
        try {
          return Array.from(sheet.cssRules)
            .filter((rule): rule is CSSStyleRule => rule instanceof CSSStyleRule)
            .filter((rule) => rule.selectorText?.includes(":focus-visible") && element.matches(rule.selectorText))
            .map((rule) => rule.cssText);
        } catch {
          return [];
        }
      });
      return {
        className: element.className,
        focusVisible: element.matches(":focus-visible"),
        matchedFocusRules,
        outlineStyle: style.outlineStyle,
        outlineWidth: Number.parseFloat(style.outlineWidth),
        outlineOffset: Number.parseFloat(style.outlineOffset),
        outlineColor: style.outlineColor,
        backgroundColors: surface.backgroundColors,
        settledSignature: surface.signature,
      };
    } finally {
      probe.remove();
    }
  }, expectedTheme);
  const background = compositeCssLayers(focus.backgroundColors);
  const backgroundColor = background[3] === 1 ? `rgb(${background[0]}, ${background[1]}, ${background[2]})` : "";
  const evidence = JSON.stringify({ ...focus, backgroundColor });

  expect(focus.focusVisible, evidence).toBe(true);
  expect(focus.matchedFocusRules.some((rule) => /outline-offset:\s*[1-9]/.test(rule)), evidence).toBe(true);
  expect(focus.outlineStyle, evidence).toBe("solid");
  expect(focus.outlineWidth, evidence).toBeGreaterThanOrEqual(2);
  expect(backgroundColor, evidence).not.toBe("");
  expect(contrastRatio(focus.outlineColor, backgroundColor), evidence).toBeGreaterThanOrEqual(3);
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

test("normal accent and warning text meet AA contrast in both themes", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=all&sort=default&lang=zh");

  const tokens = await page.evaluate(() => {
    const values = () => {
      const styles = getComputedStyle(document.documentElement);
      return {
        accent: styles.getPropertyValue("--accent").trim(),
        muted: styles.getPropertyValue("--muted").trim(),
        warning: styles.getPropertyValue("--warning").trim(),
        surfaces: ["--bg", "--bg-sunken", "--panel", "--panel2"].map((name) =>
          styles.getPropertyValue(name).trim(),
        ),
      };
    };
    const light = values();
    document.documentElement.dataset.theme = "dark";
    const dark = values();
    return { light, dark };
  });

  for (const theme of [tokens.light, tokens.dark]) {
    expect(contrastRatio(theme.accent, theme.surfaces[0])).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(theme.warning, theme.surfaces[0])).toBeGreaterThanOrEqual(4.5);
    for (const surface of theme.surfaces) {
      expect(contrastRatio(theme.muted, surface)).toBeGreaterThanOrEqual(4.5);
    }
  }
});

test("settled ArticleList text meets AA contrast in both themes", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await waitForSettledArticleList(page);

  const selectors = [
    ".articleListKbdHint kbd",
    ".articleCardMeta",
    ".articleCardTitle",
    ".articleCardSummary",
    ".articleCardTier",
    ".articleReadLink",
  ];
  for (const theme of ["light", "dark"] as const) {
    await page.evaluate((nextTheme) => {
      document.documentElement.dataset.theme = nextTheme;
    }, theme);
    const results = await new AxeBuilder({ page })
      .include(selectors)
      .withRules(["color-contrast"])
      .analyze();
    const contrastViolations = results.violations.filter(
      (violation) => violation.impact === "critical" || violation.impact === "serious",
    );
    expect(
      contrastViolations,
      `${theme} ArticleList contrast: ${JSON.stringify(contrastViolations.map((item) => item.id))}`,
    ).toEqual([]);
  }
});

test("auth and command palette inputs keep a visible keyboard focus indicator", async ({ page }) => {
  await resetFixtures(page);
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "unauthorized", message: "Authentication required" } }),
    });
  });
  await page.goto("/?module=all&sort=default&lang=zh");
  const authInput = page.locator(".authTextInput");
  await expect(authInput).toBeVisible();
  await authInput.focus();
  const authFocus = await authInput.evaluate((element) => {
    const style = getComputedStyle(element);
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, outlineColor: style.outlineColor };
  });
  expect(authFocus.outlineStyle).not.toBe("none");
  expect(authFocus.outlineWidth).not.toBe("0px");
  expect(authFocus.outlineColor.startsWith("rgba(")).toBe(false);

  await page.unroute("**/api/auth/me");
  await page.goto("/?module=all&sort=default&lang=zh");
  const sortButton = page.getByRole("button", { name: /排序/ });
  await sortButton.focus();
  await page.keyboard.press("Meta+k");
  const paletteInput = page.getByRole("dialog", { name: "命令面板" }).getByRole("textbox");
  await expect(paletteInput).toBeFocused();
  const paletteFocus = await paletteInput.evaluate((element) => {
    const style = getComputedStyle(element);
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
  });
  expect(paletteFocus.outlineStyle).not.toBe("none");
  expect(paletteFocus.outlineWidth).not.toBe("0px");
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

test("@reader-a11y @focus shared controls expose keyboard focus with measured contrast", async ({ page }) => {
  await resetFixtures(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();

  const workbenchArticle = page.getByRole("link", { name: /Keyboard article one/ }).first();
  await pressTabUntilFocused(page, workbenchArticle);
  await expect(workbenchArticle).toBeFocused();
  await expectVisibleFocusContrast(workbenchArticle, "light");

  const sortButton = page.getByRole("button", { name: /排序/ });
  await pressTabUntilFocused(page, sortButton);
  await page.keyboard.press("Control+k");
  const paletteInput = page.getByRole("dialog", { name: "命令面板" }).getByRole("textbox");
  await expect(paletteInput).toBeFocused();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Shift+Tab");
  await expect(paletteInput).toBeFocused();
  await expectVisibleFocusContrast(paletteInput, "light");
  await page.keyboard.press("Escape");
  await expect(sortButton).toBeFocused();

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });

  const returnLink = page.getByRole("link", { name: "返回工作台" });
  await pressTabUntilFocused(page, returnLink);
  await expectVisibleFocusContrast(returnLink, "dark");

  const feedbackButton = page.getByRole("button", { name: "反馈校准" });
  await pressTabUntilFocused(page, feedbackButton);
  await expectVisibleFocusContrast(feedbackButton, "dark");

  const overflowTrigger = page.getByRole("button", { name: "更多文章操作" });
  await pressTabUntilFocused(page, overflowTrigger, { reverse: true });
  await expectVisibleFocusContrast(overflowTrigger, "dark");
  await page.keyboard.press("ArrowDown");
  const overflowOption = page.getByRole("menuitem", { name: "刷新全文" });
  await expect(overflowOption).toBeFocused();
  await expectVisibleFocusContrast(overflowOption, "dark");
  await page.keyboard.press("Escape");
  await expect(overflowTrigger).toBeFocused();

  const drawerTrigger = page.getByRole("button", { name: "文章助手" });
  await pressTabUntilFocused(page, drawerTrigger);
  await expectVisibleFocusContrast(drawerTrigger, "dark");
  await page.keyboard.press("Enter");
  const quickAction = page.getByRole("button", { name: "总结", exact: true });
  await pressTabUntilFocused(page, quickAction);
  await expectVisibleFocusContrast(quickAction, "dark");
  const agentQuestion = page.locator(".agentDrawer textarea");
  await pressTabUntilFocused(page, agentQuestion);
  await expectVisibleFocusContrast(agentQuestion, "dark");

  await pressTabUntilFocused(page, drawerTrigger, { reverse: true });
  await page.keyboard.press("Enter");
  await selectReaderText(page);
  const selectionToolbar = page.getByRole("toolbar", { name: "选中文字操作" });
  await expect(selectionToolbar).toBeVisible();
  const selectionColor = selectionToolbar.getByRole("combobox", { name: "划线颜色" });
  await pressTabUntilFocused(page, selectionColor);
  await expectVisibleFocusContrast(selectionColor, "dark");
});

test("@reader-a11y @focus Workbench remains Axe-clean without horizontal overflow", async ({ page }) => {
  await resetFixtures(page);
  await page.emulateMedia({ reducedMotion: "reduce" });

  for (const setup of [
    { width: 1440, height: 1000, theme: "light" },
    { width: 390, height: 844, theme: "dark" },
  ] as const) {
    await page.setViewportSize({ width: setup.width, height: setup.height });
    await page.goto("/?module=all&sort=default&lang=zh");
    await page.evaluate((theme) => {
      document.documentElement.dataset.theme = theme;
    }, setup.theme);
    await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
    await waitForSettledArticleList(page);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth))
      .toBe(true);

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const serious = results.violations.filter(
      (violation) => violation.impact === "critical" || violation.impact === "serious",
    );
    expect(
      serious,
      `${setup.theme} ${setup.width}px Workbench a11y: ${JSON.stringify(serious.map((item) => item.id))}`,
    ).toEqual([]);
  }
});

test("axe scan finds no critical accessibility violations on core pages", async ({ page }) => {
  await resetFixtures(page);

  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await waitForSettledArticleList(page);
  const workbenchResults = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const workbenchCritical = workbenchResults.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(workbenchCritical, `Workbench a11y: ${JSON.stringify(workbenchCritical.map((v) => v.id))}`).toEqual([]);

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await waitForSettledFocusReader(page);
  const readerResults = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const readerCritical = readerResults.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(readerCritical, `Reader a11y: ${JSON.stringify(readerCritical.map((v) => v.id))}`).toEqual([]);
});

test("dark theme axe scan finds no critical accessibility violations on core pages", async ({ page }) => {
  await resetFixtures(page);
  await page.addInitScript(() => {
    window.localStorage.setItem("ai-reader.theme", "dark");
  });

  await page.goto("/?module=all&sort=default&lang=zh");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe("dark");
  await waitForSettledArticleList(page);
  const workbenchResults = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const workbenchCritical = workbenchResults.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(
    workbenchCritical,
    `Dark Workbench a11y: ${JSON.stringify(workbenchCritical.map((v) => v.id))}`,
  ).toEqual([]);

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe("dark");
  await waitForSettledFocusReader(page);
  const readerResults = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const readerCritical = readerResults.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(
    readerCritical,
    `Dark Reader a11y: ${JSON.stringify(readerCritical.map((v) => v.id))}`,
  ).toEqual([]);
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

test("never serves the previous user's cached article when the authenticated user changes", async ({ browserName, context, page }) => {
  test.skip(browserName === "firefox", "Playwright Firefox registers the worker but does not attach a controller in an isolated context");
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

test("desktop selection toolbar stays inside the viewport near the article top", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await resetFixtures(page);
  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await expect(page.locator('mark[data-annotation-id="41"]')).toBeVisible();

  await selectReaderText(page);

  const toolbar = page.getByRole("toolbar", { name: "选中文字操作" });
  await expect(toolbar).toBeVisible();
  const bounds = await toolbar.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.y).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(1280);
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(720);
});

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

test("annotation edit retry submits the latest draft and metadata", async ({ page }) => {
  await resetFixtures(page);
  await enableNotesDualPane(page);
  let putCount = 0;
  let submitted: Record<string, unknown> | null = null;
  await page.route("**/api/annotations/41", async (route) => {
    if (route.request().method() !== "PUT") {
      await route.fallback();
      return;
    }
    putCount += 1;
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    if (putCount === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "annotation_unavailable", message: "标注更新暂不可用，请重试。" } }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        annotation: {
          id: 41,
          article_id: 7,
          type: "annotation",
          selected_text: "A durable note returns when it matters.",
          content: submitted?.content,
          color: submitted?.color,
          tags: submitted?.tags,
          anchor: null,
          created_at: "2026-07-24T08:00:00Z",
          updated_at: "2026-07-27T00:00:00Z",
          next_review_at: null,
          interval_days: 3,
          review_count: 1,
        },
      }),
    });
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  const manager = page.locator('section[aria-label="已保存标注"]');
  await expect(manager).toBeVisible();
  await manager.getByRole("button", { name: "编辑标注" }).click();
  await manager.getByLabel("笔记内容").fill("旧正文");
  await manager.getByLabel("颜色").selectOption("blue");
  await manager.getByLabel("标签").fill("old");
  await manager.getByRole("button", { name: "保存修改" }).click();

  await expect(page.getByRole("button", { name: "重试标注操作" })).toBeVisible();
  await manager.getByLabel("笔记内容").fill("最新正文");
  await manager.getByLabel("颜色").selectOption("green");
  await manager.getByLabel("标签").fill("latest, retry");
  await page.getByRole("button", { name: "重试标注操作" }).click();

  await expect(page.getByText("标注已更新", { exact: true })).toBeVisible();
  expect(putCount).toBe(2);
  expect(submitted).toEqual({
    content: "最新正文",
    color: "green",
    tags: ["latest", "retry"],
  });
  await expect(manager).toContainText("最新正文");
  await expect(manager).toContainText("颜色：green");
  await expect(manager).toContainText("标签：latest, retry");
});

test("annotation delete response loss retries without a second confirmation", async ({ page }) => {
  await resetFixtures(page);
  await enableNotesDualPane(page);
  let deleteCount = 0;
  let dialogCount = 0;
  const unexpectedDialogs: string[] = [];
  let serverDeleted = false;

  page.on("dialog", async (dialog) => {
    dialogCount += 1;
    if (dialogCount === 1) {
      await dialog.accept();
      return;
    }
    unexpectedDialogs.push(dialog.message());
    await dialog.dismiss();
  });
  await page.route("**/api/annotations/41", async (route) => {
    if (route.request().method() !== "DELETE") {
      await route.fallback();
      return;
    }
    deleteCount += 1;
    if (deleteCount === 1) {
      serverDeleted = true;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          error: { code: "response_lost", message: "删除已提交，但响应未送达。" },
        }),
      });
      return;
    }
    expect(serverDeleted).toBe(true);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ deleted: true, id: 41 }),
    });
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  const manager = page.locator('section[aria-label="已保存标注"]');
  await expect(manager).toBeVisible();
  await manager.getByRole("button", { name: "删除标注" }).click();

  await expect(manager.getByRole("alert")).toContainText("删除已提交，但响应未送达。");
  await expect(manager.getByRole("button", { name: "重试标注操作" })).toBeVisible();
  await expect(manager).toContainText("A durable note returns when it matters.");

  await manager.getByRole("button", { name: "重试标注操作" }).click();
  await expect(page.getByText("标注已删除", { exact: true })).toBeVisible();
  await expect(manager).toHaveCount(0);
  expect(deleteCount).toBe(2);
  expect(dialogCount).toBe(1);
  expect(unexpectedDialogs).toEqual([]);
});

test("annotation selection retry uses current color and tags without changing its quote", async ({ page }) => {
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
          id: 65,
          article_id: 7,
          type: "annotation",
          selected_text: submitted?.selected_text,
          content: submitted?.content,
          color: submitted?.color,
          tags: submitted?.tags,
          anchor: submitted?.anchor,
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
  await toolbar.locator("select").selectOption("yellow");
  await expect(toolbar).toBeVisible();
  await toolbar.getByPlaceholder("标签,逗号分隔").fill("old");
  await expect(toolbar).toBeVisible();
  await toolbar.getByRole("button", { name: "保存划线" }).click();
  await expect(toolbar.getByRole("button", { name: "重试保存" })).toBeVisible();

  await toolbar.locator("select").selectOption("green");
  await toolbar.getByPlaceholder("标签,逗号分隔").fill("latest, retry");
  await toolbar.getByRole("button", { name: "重试保存" }).click();

  await expect(page.getByText("已保存划线", { exact: true })).toBeVisible();
  expect(postCount).toBe(2);
  expect(submitted?.content).toBe("Evidence persists.");
  expect(submitted?.selected_text).toBe("Evidence persists.");
  expect(submitted?.color).toBe("green");
  expect(submitted?.tags).toEqual(["latest", "retry"]);
  expect((submitted?.anchor as Record<string, unknown>).exact).toBe("Evidence persists.");
  await expect(page.locator('mark[data-annotation-id="65"]')).toBeVisible();
});

test("dual-pane note submission prevents duplicate POST and preserves an ABA-edited draft", async ({ page }) => {
  await resetFixtures(page);
  await enableNotesDualPane(page);
  let postCount = 0;
  const submitted: Record<string, unknown>[] = [];
  let releaseFirst!: () => void;
  const firstResponseHeld = new Promise<void>((resolve) => {
    releaseFirst = resolve;
  });
  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    postCount += 1;
    submitted.push(route.request().postDataJSON() as Record<string, unknown>);
    if (postCount === 1) await firstResponseHeld;
    await route.fallback();
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  const notes = page.locator('aside[aria-label="笔记双栏"]');
  const textarea = notes.getByPlaceholder("边读边记…");
  const saveButton = notes.getByRole("button", { name: "保存笔记" });
  await textarea.fill("ABA 笔记");
  await saveButton.evaluate((button) => {
    (button as HTMLButtonElement).click();
    (button as HTMLButtonElement).click();
  });

  await expect.poll(() => postCount).toBe(1);
  await expect(notes.getByRole("button", { name: "保存中…" })).toBeDisabled();
  await page.waitForTimeout(100);
  expect(postCount).toBe(1);

  await textarea.fill("中间草稿");
  await textarea.fill("ABA 笔记");
  releaseFirst();

  await expect(page.getByText("笔记已保存", { exact: true })).toBeVisible();
  await expect(textarea).toHaveValue("ABA 笔记");
  await expect(notes.getByRole("button", { name: "保存笔记" })).toBeEnabled();
  expect(submitted[0]?.content).toBe("ABA 笔记");

  await notes.getByRole("button", { name: "保存笔记" }).click();
  await expect.poll(() => postCount).toBe(2);
  await expect(textarea).toHaveValue("");
  expect(submitted[1]?.content).toBe("ABA 笔记");

  const persistedResponse = await page.request.get("/api/articles/7/annotations");
  expect(persistedResponse.ok()).toBe(true);
  const persisted = (await persistedResponse.json()) as {
    items: Array<{ id: number; content: string }>;
  };
  expect(
    persisted.items
      .filter((item) => item.content === "ABA 笔记")
      .map((item) => item.id),
  ).toEqual([60, 61]);
});

test("dual-pane note retry resubmits the immutable failed snapshot", async ({ page }) => {
  await resetFixtures(page);
  await enableNotesDualPane(page);
  const submitted: Record<string, unknown>[] = [];
  let releaseRetry!: () => void;
  const retryResponseHeld = new Promise<void>((resolve) => {
    releaseRetry = resolve;
  });
  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    submitted.push(route.request().postDataJSON() as Record<string, unknown>);
    if (submitted.length === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "annotation_unavailable", message: "标注保存暂不可用，请重试。" } }),
      });
      return;
    }
    await retryResponseHeld;
    await route.fallback();
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.locator('mark[data-annotation-id="41"]')).toBeVisible();
  await selectReaderText(page);
  const toolbar = page.getByRole("toolbar", { name: "选中文字操作" });
  const notes = page.locator('aside[aria-label="笔记双栏"]');
  const textarea = notes.getByPlaceholder("边读边记…");
  await expect(toolbar).toBeVisible();
  await textarea.fill("原提交笔记");
  await toolbar.locator("select").selectOption("yellow");
  await toolbar.getByPlaceholder("标签,逗号分隔").fill("original, snapshot");
  await notes.getByRole("button", { name: "保存笔记" }).click();
  await expect(notes.getByRole("button", { name: "重试原提交" })).toBeVisible();

  await textarea.fill("失败后新笔记");
  await toolbar.locator("select").selectOption("blue");
  await toolbar.getByPlaceholder("标签,逗号分隔").fill("latest, draft");
  await notes.getByRole("button", { name: "重试原提交" }).click();

  await expect.poll(() => submitted.length).toBe(2);
  const retryAlert = notes.getByRole("alert");
  const pendingRetryButton = retryAlert.getByRole("button", { name: "保存中…" });
  await expect(pendingRetryButton).toBeVisible();
  await expect(pendingRetryButton).toBeDisabled();
  await expect(retryAlert).toContainText("标注保存暂不可用，请重试。");
  expect(submitted[1]).toEqual(submitted[0]);
  expect(submitted[0]?.content).toBe("原提交笔记");
  expect(submitted[0]?.selected_text).toBe("Evidence persists.");
  expect(submitted[0]?.color).toBe("yellow");
  expect(submitted[0]?.tags).toEqual(["original", "snapshot"]);
  expect((submitted[0]?.anchor as Record<string, unknown>).exact).toBe("Evidence persists.");
  await expect(textarea).toHaveValue("失败后新笔记");

  releaseRetry();
  await expect(page.getByText("笔记已保存", { exact: true })).toBeVisible();
  await expect(notes.getByRole("alert")).toHaveCount(0);
  await expect(notes.getByRole("button", { name: "重试原提交" })).toHaveCount(0);

  const persistedResponse = await page.request.get("/api/articles/7/annotations");
  expect(persistedResponse.ok()).toBe(true);
  const persisted = (await persistedResponse.json()) as {
    items: Array<{ id: number; content: string }>;
  };
  expect(
    persisted.items
      .filter((item) => item.content === "原提交笔记")
      .map((item) => item.id),
  ).toEqual([60]);
});

test("new selection reactively removes a failed dual-pane note retry but keeps its error", async ({ page }) => {
  await resetFixtures(page);
  await enableNotesDualPane(page);
  let postCount = 0;
  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    postCount += 1;
    if (postCount === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "annotation_unavailable", message: "标注保存暂不可用，请重试。" } }),
      });
      return;
    }
    await route.fallback();
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.locator('mark[data-annotation-id="41"]')).toBeVisible();
  await waitForSettledFocusReader(page);
  await selectReaderText(page);
  const notes = page.locator('aside[aria-label="笔记双栏"]');
  const textarea = notes.getByPlaceholder("边读边记…");
  await textarea.fill("selection-bound retry");
  await notes.getByRole("button", { name: "保存笔记" }).click();
  await expect(notes.getByRole("button", { name: "重试原提交" })).toBeVisible();
  const error = notes.getByRole("alert");
  await expect(error).toContainText("标注保存暂不可用，请重试。");

  await page.keyboard.press("Escape");
  await selectReaderParagraphWithMouse(page, "Evidence should survive navigation.");
  await expect(notes.getByRole("button", { name: "重试原提交" })).toHaveCount(0);
  await expect(error).toContainText("标注保存暂不可用，请重试。");
  expect(postCount).toBe(1);
  await expect(textarea).toHaveValue("selection-bound retry");

  await notes.getByRole("button", { name: "保存笔记" }).click();
  await expect.poll(() => postCount).toBe(2);
  await expect(textarea).toHaveValue("");
});

test("a delayed dual-pane note failure cannot install retry after selection revision changes", async ({ page }) => {
  await resetFixtures(page);
  await enableNotesDualPane(page);
  let postCount = 0;
  let releaseFailure!: () => void;
  const failureHeld = new Promise<void>((resolve) => {
    releaseFailure = resolve;
  });
  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    postCount += 1;
    await failureHeld;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "annotation_unavailable", message: "延迟失败" } }),
    });
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.locator('mark[data-annotation-id="41"]')).toBeVisible();
  await waitForSettledFocusReader(page);
  await selectReaderText(page);
  const notes = page.locator('aside[aria-label="笔记双栏"]');
  const textarea = notes.getByPlaceholder("边读边记…");
  await textarea.fill("delayed failure note");
  await notes.getByRole("button", { name: "保存笔记" }).click();
  await expect.poll(() => postCount).toBe(1);

  await page.keyboard.press("Escape");
  await selectReaderParagraphWithMouse(page, "Evidence should survive navigation.");
  releaseFailure();

  await expect(notes.getByRole("alert")).toContainText("延迟失败");
  await expect(notes.getByRole("button", { name: "重试原提交" })).toHaveCount(0);
  await expect(textarea).toHaveValue("delayed failure note");
  expect(postCount).toBe(1);
});

test("client navigation unmounts the old note owner without hiding its persisted server result", async ({ page }) => {
  await resetFixtures(page);
  await enableNotesDualPane(page);
  let postCount = 0;
  let firstPostCompleted = false;
  let releaseArticleSeven!: () => void;
  const articleSevenPostHeld = new Promise<void>((resolve) => {
    releaseArticleSeven = resolve;
  });

  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    postCount += 1;
    await articleSevenPostHeld;
    await route.fallback();
    firstPostCompleted = true;
  });

  await page.goto("/read/7?module=search&filter=all&sort=default&lang=zh&q=fast");
  const articleSevenNotes = page.locator('aside[aria-label="笔记双栏"]');
  await articleSevenNotes.getByPlaceholder("边读边记…").fill("held A7 note");
  await articleSevenNotes.getByRole("button", { name: "保存笔记" }).click();
  await expect.poll(() => postCount).toBe(1);

  await page.getByRole("link", { name: "返回工作台" }).click();
  await expect(page).toHaveURL(/module=search.*q=fast/);
  await expect(page.locator('aside[aria-label="笔记双栏"]')).toHaveCount(0);
  await page.evaluate(() => {
    const state = window as Window & { __sawFocusArticleSkeleton?: boolean };
    state.__sawFocusArticleSkeleton = document.querySelector(".focusArticleSkeleton") != null;
    const observer = new MutationObserver(() => {
      if (document.querySelector(".focusArticleSkeleton") != null) {
        state.__sawFocusArticleSkeleton = true;
        observer.disconnect();
      }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  });
  const fastResult = page.getByRole("link", { name: "Fast search result" }).first();
  await expect(fastResult).toBeVisible();
  await fastResult.click();
  await expect(page).toHaveURL(/\/read\/9\?/);
  await expect(page.getByRole("heading", { name: "Fast search result" })).toBeVisible();
  await expect.poll(() =>
    page.evaluate(() =>
      Boolean((window as Window & { __sawFocusArticleSkeleton?: boolean }).__sawFocusArticleSkeleton),
    ),
  ).toBe(true);
  const articleNineNotes = page.locator('aside[aria-label="笔记双栏"]');
  const articleNineDraft = articleNineNotes.getByPlaceholder("边读边记…");
  await expect(articleNineDraft).toHaveValue("");
  await articleNineDraft.fill("article 9 local draft");

  releaseArticleSeven();
  await expect.poll(() => firstPostCompleted).toBe(true);
  await expect(articleNineDraft).toHaveValue("article 9 local draft");
  await expect(articleNineNotes.getByText("held A7 note", { exact: true })).toHaveCount(0);
  await expect(page.getByText("笔记已保存", { exact: true })).toHaveCount(0);
  await expect(articleNineNotes.getByRole("alert")).toHaveCount(0);
  await expect(articleNineNotes.getByRole("button", { name: "重试原提交" })).toHaveCount(0);

  await page.getByRole("link", { name: "返回工作台" }).click();
  await page.getByRole("link", { name: "最新", exact: true }).click();
  const articleSevenLink = page.getByRole("link", { name: /Keyboard article one/ }).first();
  await expect(articleSevenLink).toBeVisible();
  await articleSevenLink.click();
  const returnedNotes = page.locator('aside[aria-label="笔记双栏"]');
  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await expect(returnedNotes.getByPlaceholder("边读边记…")).toHaveValue("");

  const persistedResponse = await page.request.get("/api/articles/7/annotations");
  expect(persistedResponse.ok()).toBe(true);
  const persisted = (await persistedResponse.json()) as {
    items: Array<{ id: number; content: string }>;
  };
  expect(
    persisted.items
      .filter((item) => item.content === "held A7 note")
      .map((item) => item.id),
  ).toEqual([60]);
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
  await selectReaderParagraphWithMouse(page, "Evidence should survive navigation.");
  await expect(toolbar).toBeVisible();
  await expect(page.getByRole("button", { name: "保存划线" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重试保存" })).toHaveCount(0);

  expect(postCount).toBe(1);
  expect(submitted?.selected_text).toBe("Evidence persists.");
});

test("selection callbacks from an unmounted article cannot contaminate the next article", async ({ page }) => {
  await resetFixtures(page);
  let postStarted = false;
  let getStarted = false;
  let releaseOldPost!: () => void;
  let releaseOldGet!: () => void;
  const oldPostHeld = new Promise<void>((resolve) => {
    releaseOldPost = resolve;
  });
  const oldGetHeld = new Promise<void>((resolve) => {
    releaseOldGet = resolve;
  });

  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() === "POST") {
      postStarted = true;
      await oldPostHeld;
      await route.fallback();
      return;
    }
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    const response = await route.fetch();
    const body = await response.body();
    getStarted = true;
    await oldGetHeld;
    await route.fulfill({ response, body });
  });

  await page.goto("/read/7?module=search&filter=all&sort=default&lang=zh&q=fast");
  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await expect.poll(() => getStarted).toBe(true);
  await selectReaderText(page);
  await page.getByRole("button", { name: "保存划线" }).click();
  await expect.poll(() => postStarted).toBe(true);

  await page.getByRole("link", { name: "返回工作台" }).click();
  await expect(page).toHaveURL(/module=search.*q=fast/);
  const fastResult = page.getByRole("link", { name: "Fast search result" }).first();
  await expect(fastResult).toBeVisible();
  await fastResult.click();
  await expect(page).toHaveURL(/\/read\/9\?/);
  await expect(page.getByRole("heading", { name: "Fast search result" })).toBeVisible();

  releaseOldPost();
  releaseOldGet();
  await page.waitForTimeout(150);
  await expect(page.locator('mark[data-annotation-id="60"]')).toHaveCount(0);
  await expect(page.getByText("已保存划线", { exact: true })).toHaveCount(0);
});

test("annotation create success is not overwritten by a delayed mutation-before GET snapshot", async ({ page }) => {
  await resetFixtures(page);
  let releaseInitialGet!: () => void;
  let markSnapshotReady!: () => void;
  const initialGetHeld = new Promise<void>((resolve) => {
    releaseInitialGet = resolve;
  });
  const snapshotReady = new Promise<void>((resolve) => {
    markSnapshotReady = resolve;
  });
  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    const snapshot = await route.fetch();
    const body = await snapshot.body();
    markSnapshotReady();
    await initialGetHeld;
    await route.fulfill({ response: snapshot, body });
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await snapshotReady;
  await waitForSettledFocusReader(page);
  await selectReaderText(page);
  await page.getByRole("button", { name: "保存划线" }).click();
  await expect(page.getByText("已保存划线", { exact: true })).toBeVisible();
  await expect(page.locator('mark[data-annotation-id="60"]')).toBeVisible();

  releaseInitialGet();
  await page.waitForTimeout(150);
  await expect(page.locator('mark[data-annotation-id="60"]')).toBeVisible();
});

test("selection pending blocks synchronous duplicate POST and old success cannot clear a newer attempt", async ({ page }) => {
  await resetFixtures(page);
  let postCount = 0;
  let releaseFirst: (() => void) | null = null;
  let releaseSecond: (() => void) | null = null;
  const firstResponseHeld = new Promise<void>((resolve) => {
    releaseFirst = resolve;
  });
  const secondResponseHeld = new Promise<void>((resolve) => {
    releaseSecond = resolve;
  });

  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    postCount += 1;
    const requestNumber = postCount;
    const body = route.request().postDataJSON() as Record<string, unknown>;
    if (requestNumber === 1) await firstResponseHeld;
    if (requestNumber === 2) await secondResponseHeld;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        annotation: {
          id: requestNumber === 1 ? 62 : 63,
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
  const firstSave = page.getByRole("button", { name: "保存划线" });
  await firstSave.evaluate((button) => {
    (button as HTMLButtonElement).click();
    (button as HTMLButtonElement).click();
  });
  await expect.poll(() => postCount).toBe(1);
  await expect(page.getByRole("button", { name: "保存中…" })).toBeDisabled();
  await page.waitForTimeout(100);
  expect(postCount).toBe(1);

  await page.keyboard.press("Escape");
  await selectReaderParagraphWithMouse(page, "Evidence should survive navigation.");
  await expect(toolbar).toBeVisible();
  const secondSave = page.getByRole("button", { name: "保存划线" });
  await expect(secondSave).toBeEnabled();
  await secondSave.click();
  await expect.poll(() => postCount).toBe(2);
  await expect(page.getByRole("button", { name: "保存中…" })).toBeDisabled();

  releaseFirst?.();
  releaseFirst = null;
  await expect(page.getByRole("button", { name: "保存中…" })).toBeDisabled();
  await expect(page.getByText("已保存划线", { exact: true })).toHaveCount(0);

  releaseSecond?.();
  releaseSecond = null;
  await expect(page.getByText("已保存划线", { exact: true })).toBeVisible();
  await expect(toolbar).toBeHidden();
});

test("in-flight annotation save failure cannot install stale retry on a newer selection", async ({ page }) => {
  await resetFixtures(page);
  let postCount = 0;
  let releaseFirst: (() => void) | null = null;
  const firstResponseHeld = new Promise<void>((resolve) => {
    releaseFirst = resolve;
  });

  await page.route("**/api/articles/7/annotations", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    postCount += 1;
    const body = route.request().postDataJSON() as Record<string, unknown>;
    if (postCount === 1) {
      await firstResponseHeld;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "annotation_unavailable", message: "旧请求失败" } }),
      });
      return;
    }
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        annotation: {
          id: 64,
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
  await expect.poll(() => postCount).toBe(1);

  await page.keyboard.press("Escape");
  await selectReaderParagraphWithMouse(page, "Evidence should survive navigation.");
  await expect(toolbar).toBeVisible();
  releaseFirst?.();
  releaseFirst = null;

  await expect(page.getByText("划线保存失败", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "重试保存" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "保存划线" })).toBeVisible();
  await page.getByRole("button", { name: "保存划线" }).click();
  await expect.poll(() => postCount).toBe(2);
  await expect(page.getByText("已保存划线", { exact: true })).toBeVisible();
  await expect(toolbar).toBeHidden();
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

test("oversized cursor trails canonicalize back to the first page", async ({ page }) => {
  await resetFixtures(page);
  const oversizedTrail = JSON.stringify([null, ...Array(3).fill("x".repeat(2600))]);

  await page.goto(`/?module=all&sort=default&lang=zh&trail=${encodeURIComponent(oversizedTrail)}`);

  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await expect(page).not.toHaveURL(/trail=/);
  await expect(page.getByText("第 1 页", { exact: true })).toBeVisible();
});

async function assertSuccessfulLaterEmptyPageEscape(
  page: import("@playwright/test").Page,
  url: string,
) {
  await resetFixtures(page);
  await page.goto(url);
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "下一页 ›" }).click();

  await expect(page.getByText("暂无文章", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "‹ 上一页" })).toBeEnabled();
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  await expect(page.getByText("Keyboard article one", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "‹ 上一页" }).click();

  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await expect(page.getByText("第 1 页", { exact: true })).toBeVisible();
  await expect(page).not.toHaveURL(/trail=/);
}

test("scan mode successful later empty page offers a previous-page escape", async ({ page }) => {
  await setCraftPreferences(page, { mode: "scan" });
  await assertSuccessfulLaterEmptyPageEscape(page, "/?module=all&sort=default&lang=zh&q=empty-page");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.readerMode)).toBe("scan");
});

test("focus mode successful later empty page offers a previous-page escape", async ({ page }) => {
  await setCraftPreferences(page, { mode: "focus" });
  await assertSuccessfulLaterEmptyPageEscape(page, "/?module=all&sort=score&lang=original&q=empty-page");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.readerMode)).toBe("focus");
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
  await page.getByRole("button", { name: "刷新队列" }).click();
  await expect(page.getByText("A durable note returns when it matters.", { exact: true })).toBeVisible();
  await expect(page.getByText(/复习队列暂不可用/)).toHaveCount(0);
});

test("review refresh and review pending block synchronous duplicates and reject stale queue snapshots", async ({ page }) => {
  await resetFixtures(page);
  let getCount = 0;
  let postCount = 0;
  let releaseRefresh!: () => void;
  let releaseReview!: () => void;
  const refreshHeld = new Promise<void>((resolve) => {
    releaseRefresh = resolve;
  });
  const reviewHeld = new Promise<void>((resolve) => {
    releaseReview = resolve;
  });
  const reviewItem = {
    id: 41,
    article_id: 7,
    type: "annotation",
    selected_text: "A durable note returns when it matters.",
    content: "A durable note returns when it matters.",
    color: "yellow",
    tags: ["evidence"],
    created_at: "2026-07-24T08:00:00Z",
    next_review_at: "2026-07-26T08:00:00Z",
    interval_days: 3,
    review_count: 1,
    article_title: "Durable research workflows",
    article_url: "https://example.com/durable-research",
  };
  await page.route("**/api/annotations/review?**", async (route) => {
    getCount += 1;
    if (getCount === 2) await refreshHeld;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [reviewItem] }),
    });
  });
  await page.route("**/api/annotations/41/review", async (route) => {
    postCount += 1;
    await reviewHeld;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ annotation: { ...reviewItem, review_count: 2, interval_days: 7 } }),
    });
  });

  await page.goto("/?module=review&sort=default&lang=zh");
  await expect(page.getByText(reviewItem.content, { exact: true })).toBeVisible();
  expect(getCount).toBe(1);
  const refresh = page.getByRole("button", { name: "刷新队列" });
  await refresh.focus();
  await refresh.evaluate((button) => {
    (button as HTMLButtonElement).click();
    (button as HTMLButtonElement).click();
  });
  await expect.poll(() => getCount).toBe(2);
  await expect(refresh).toBeDisabled();
  await expect(refresh).toHaveText("刷新中…");
  await expect(page.getByText(reviewItem.content, { exact: true })).toBeVisible();
  await page.waitForTimeout(100);
  expect(getCount).toBe(2);

  const remember = page.getByRole("button", { name: "记得" });
  await remember.evaluate((button) => {
    (button as HTMLButtonElement).click();
    (button as HTMLButtonElement).click();
  });
  await expect.poll(() => postCount).toBe(1);
  await expect(page.getByRole("button", { name: "提交中…" }).first()).toBeDisabled();
  await page.waitForTimeout(100);
  expect(postCount).toBe(1);
  releaseReview();
  await expect(page.getByText(reviewItem.content, { exact: true })).toHaveCount(0);

  releaseRefresh();
  await expect(refresh).toBeEnabled();
  await expect(refresh).toHaveAccessibleName("刷新队列");
  await expect(page.getByText(reviewItem.content, { exact: true })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("aria-label"))).toBe("刷新队列");
});

test("review refresh failure preserves items and same-mount retry issues the third GET", async ({ page }) => {
  await resetFixtures(page);
  let getCount = 0;
  const item = {
    id: 41,
    article_id: 7,
    type: "annotation",
    selected_text: "A durable note returns when it matters.",
    content: "A durable note returns when it matters.",
    color: "yellow",
    tags: ["evidence"],
    created_at: "2026-07-24T08:00:00Z",
    next_review_at: "2026-07-26T08:00:00Z",
    interval_days: 3,
    review_count: 1,
    article_title: "Durable research workflows",
    article_url: "https://example.com/durable-research",
  };
  await page.route("**/api/annotations/review?**", async (route) => {
    getCount += 1;
    if (getCount === 2) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "review_unavailable", message: "刷新队列失败" } }),
      });
      return;
    }
    const nextItems = getCount === 3 ? [{ ...item, id: 42, selected_text: "Recovered queue item", content: "Recovered queue item" }] : [item];
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: nextItems }),
    });
  });

  await page.goto("/?module=review&sort=default&lang=zh");
  await expect(page.getByText(item.content, { exact: true })).toBeVisible();
  const refresh = page.getByRole("button", { name: "刷新队列" });
  await refresh.focus();
  await refresh.evaluate((button) => {
    (button as HTMLButtonElement).click();
    (button as HTMLButtonElement).click();
  });
  await expect.poll(() => getCount).toBe(2);
  await expect(page.locator(".reviewQueuePane .adminConsoleError")).toContainText("刷新队列失败");
  await expect(page.getByText(item.content, { exact: true })).toBeVisible();
  await expect(refresh).toBeEnabled();
  await expect(refresh).toHaveAccessibleName("刷新队列");
  await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("aria-label"))).toBe("刷新队列");

  await refresh.click();
  await expect.poll(() => getCount).toBe(3);
  await expect(page.locator(".reviewQueuePane .adminConsoleError")).toHaveCount(0);
  await expect(page.getByText("Recovered queue item", { exact: true })).toBeVisible();
  await expect(page.getByText(item.content, { exact: true })).toHaveCount(0);
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
  await page.goto("/read/998?module=all&sort=default&lang=zh");

  await expect(page.getByText("文章加载失败", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "重试加载" })).toBeVisible();
});

test("Reader keeps related links while labeling a failed related source", async ({ page }) => {
  await resetFixtures(page);
  await page.route("**/api/clusters/latest?**", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "cluster_unavailable", message: "cluster fixture failure" } }),
    });
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");

  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await expect(page.getByRole("link", { name: "theme Evidence continuity", exact: true })).toBeVisible();
  await expect(page.getByText(/故事线加载失败：/)).toBeVisible();
  await expect(page.getByRole("button", { name: "重试故事线" })).toBeVisible();
});

test("Reader retries only the failed related source", async ({ page }) => {
  await resetFixtures(page);
  let clusterRequests = 0;
  let themeRequests = 0;
  await page.route("**/api/clusters/latest?**", async (route) => {
    clusterRequests += 1;
    if (clusterRequests === 1) {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "cluster_unavailable", message: "cluster fixture failure" } }),
      });
      return;
    }
    await route.fallback();
  });
  await page.route("**/api/themes/latest?**", async (route) => {
    themeRequests += 1;
    await route.fallback();
  });

  await page.goto("/read/7?module=all&sort=default&lang=zh");
  await expect(page.getByRole("button", { name: "重试故事线" })).toBeVisible();
  await page.getByRole("button", { name: "重试故事线" }).click();

  await expect(page.getByRole("link", { name: "cluster 可恢复研究工作流 (2)", exact: true })).toBeVisible();
  await expect(page.getByText(/故事线加载失败：/)).toHaveCount(0);
  expect(themeRequests).toBe(1);
  expect(clusterRequests).toBe(2);
});

test("Daily Intelligence labels failed sources instead of false empty states", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=home&sort=default&lang=zh&fixture=daily-error");

  await expect(page.getByRole("button", { name: "刷新情报" })).toBeVisible();
  await expect(page.getByText(/加载失败：/).first()).toBeVisible();
  await expect(page.getByText("暂无条目", { exact: true })).toHaveCount(0);
});

test("Daily Intelligence preserves canonical brief metadata in its cards", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=home&sort=default&lang=zh");

  await expect(page.getByRole("heading", { name: "今日研究简报" })).toBeVisible();
  await expect(page.getByText("风险 reposted", { exact: true })).toBeVisible();
  await expect(page.getByText("源可信 88", { exact: true })).toBeVisible();
  await expect(page.getByText("full", { exact: true })).toBeVisible();
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
