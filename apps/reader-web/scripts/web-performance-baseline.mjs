import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const readerRoot = resolve(scriptDir, "..");
const repositoryRoot = resolve(readerRoot, "../..");
const defaultRoutes = [
  "/?module=home&sort=default&lang=zh",
  "/?module=all&sort=default&lang=zh",
];

function parsePositiveInteger(value, option) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isSafeInteger(parsed) || parsed < 1) {
    throw new Error(`${option} must be a positive integer`);
  }
  return parsed;
}

function parseArguments(argv) {
  const options = {
    baseURL: process.env.WEB_BASE_URL ?? "http://127.0.0.1:3010",
    iterations: 5,
    output: null,
    routes: defaultRoutes,
    settleMs: 1_000,
    warmups: 1,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    const [name, inlineValue] = argument.split("=", 2);
    const value = inlineValue ?? argv[index + 1];
    if (inlineValue == null && name.startsWith("--")) index += 1;

    if (name === "--base-url") options.baseURL = value;
    else if (name === "--iterations") options.iterations = parsePositiveInteger(value, name);
    else if (name === "--output") options.output = value;
    else if (name === "--routes") options.routes = value.split(",").filter(Boolean);
    else if (name === "--settle-ms") options.settleMs = parsePositiveInteger(value, name);
    else if (name === "--warmups") options.warmups = parsePositiveInteger(value, name);
    else throw new Error(`Unknown option: ${name}`);
  }

  const parsedBaseURL = new URL(options.baseURL);
  if (!["http:", "https:"].includes(parsedBaseURL.protocol)) {
    throw new Error("--base-url must use http or https");
  }
  if (parsedBaseURL.username || parsedBaseURL.password) {
    throw new Error("--base-url must not contain credentials");
  }
  if (options.routes.length === 0 || options.routes.some((route) => !route.startsWith("/"))) {
    throw new Error("--routes must be a non-empty comma-separated list of same-origin paths");
  }
  options.baseURL = parsedBaseURL.href.replace(/\/$/, "");
  return options;
}

function percentile(values, quantile) {
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.max(0, Math.ceil(quantile * sorted.length) - 1);
  return sorted[index];
}

function summarize(samples, field) {
  const values = samples.map((sample) => sample.metrics[field]);
  return {
    median: percentile(values, 0.5),
    p95: percentile(values, 0.95),
    min: Math.min(...values),
    max: Math.max(...values),
  };
}

function currentRevision() {
  try {
    return execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: repositoryRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "UNKNOWN";
  }
}

async function installObservers(page) {
  await page.addInitScript(() => {
    const state = {
      cls: 0,
      lcpMs: 0,
      longTaskCount: 0,
      longTaskTotalMs: 0,
    };
    globalThis.__AI_READER_WEB_BASELINE__ = state;

    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (!entry.hadRecentInput) state.cls += entry.value;
        }
      }).observe({ type: "layout-shift", buffered: true });
    } catch {}

    try {
      new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const last = entries.at(-1);
        if (last) state.lcpMs = last.startTime;
      }).observe({ type: "largest-contentful-paint", buffered: true });
    } catch {}

    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          state.longTaskCount += 1;
          state.longTaskTotalMs += entry.duration;
        }
      }).observe({ type: "longtask", buffered: true });
    } catch {}
  });
}

async function measureRoute(browser, options, route, sampleIndex, phase) {
  const context = await browser.newContext({
    serviceWorkers: "block",
    viewport: { width: 1440, height: 1_000 },
  });
  const page = await context.newPage();
  const browserErrors = [];
  const failedResponses = [];

  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const location = message.location();
    let sourcePath = "unknown";
    try {
      sourcePath = location.url ? new URL(location.url).pathname : "unknown";
    } catch {}
    browserErrors.push({
      kind: "console.error",
      line: location.lineNumber ?? null,
      sourcePath,
    });
  });
  page.on("pageerror", (error) => browserErrors.push({ kind: "pageerror", name: error.name }));
  page.on("response", (response) => {
    if (response.status() >= 400) {
      failedResponses.push({ status: response.status(), url: new URL(response.url()).pathname });
    }
  });

  await installObservers(page);
  const response = await page.goto(`${options.baseURL}${route}`, {
    waitUntil: "domcontentloaded",
    timeout: 30_000,
  });
  await page.waitForTimeout(options.settleMs);

  const metrics = await page.evaluate(() => {
    const navigation = performance.getEntriesByType("navigation")[0];
    const paints = Object.fromEntries(
      performance.getEntriesByType("paint").map((entry) => [entry.name, entry.startTime]),
    );
    const resources = performance.getEntriesByType("resource");
    const state = globalThis.__AI_READER_WEB_BASELINE__ ?? {};
    return {
      cls: state.cls ?? 0,
      domContentLoadedMs: navigation?.domContentLoadedEventEnd ?? 0,
      firstContentfulPaintMs: paints["first-contentful-paint"] ?? 0,
      firstPaintMs: paints["first-paint"] ?? 0,
      lcpMs: state.lcpMs ?? 0,
      loadEventMs: navigation?.loadEventEnd ?? 0,
      longTaskCount: state.longTaskCount ?? 0,
      longTaskTotalMs: state.longTaskTotalMs ?? 0,
      navigationTransferBytes: navigation?.transferSize ?? 0,
      resourceCount: resources.length,
      resourceTransferBytes: resources.reduce((total, entry) => total + (entry.transferSize ?? 0), 0),
      responseEndMs: navigation?.responseEnd ?? 0,
    };
  });

  await context.close();
  return {
    browserErrors,
    failedResponses,
    httpStatus: response?.status() ?? null,
    metrics,
    phase,
    route,
    sampleIndex,
  };
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  const browser = await chromium.launch({ headless: true });
  const samples = [];

  try {
    for (const route of options.routes) {
      for (let index = 0; index < options.warmups; index += 1) {
        await measureRoute(browser, options, route, index + 1, "warmup");
      }
      for (let index = 0; index < options.iterations; index += 1) {
        samples.push(await measureRoute(browser, options, route, index + 1, "measured"));
      }
    }

    const browserVersion = browser.version();
    const routeResults = options.routes.map((route) => {
      const routeSamples = samples.filter((sample) => sample.route === route);
      const metricNames = Object.keys(routeSamples[0].metrics);
      return {
        route,
        samples: routeSamples,
        summary: Object.fromEntries(metricNames.map((name) => [name, summarize(routeSamples, name)])),
      };
    });
    const report = {
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      candidate: {
        localGitRevision: currentRevision(),
        measuredBaseURL: options.baseURL,
        remoteRevision: process.env.WEB_REMOTE_REVISION ?? "UNKNOWN",
      },
      environment: {
        architecture: process.arch,
        browser: `chromium ${browserVersion}`,
        iterations: options.iterations,
        node: process.version,
        platform: process.platform,
        serviceWorkers: "blocked",
        settleMs: options.settleMs,
        viewport: { width: 1440, height: 1_000 },
        warmups: options.warmups,
      },
      routes: routeResults,
    };
    const serialized = `${JSON.stringify(report, null, 2)}\n`;

    if (options.output) {
      const outputPath = resolve(process.cwd(), options.output);
      await mkdir(dirname(outputPath), { recursive: true });
      await writeFile(outputPath, serialized, "utf8");
      process.stderr.write(`Web performance baseline written to ${outputPath}\n`);
    } else {
      process.stdout.write(serialized);
    }

    const unexpectedFailures = samples.flatMap((sample) => [
      ...sample.browserErrors.map((error) => error.kind),
      ...sample.failedResponses.map((failure) => `${failure.status} ${failure.url}`),
    ]);
    if (unexpectedFailures.length > 0) {
      process.stderr.write(`Baseline captured ${unexpectedFailures.length} browser/network errors\n`);
      process.exitCode = 2;
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
