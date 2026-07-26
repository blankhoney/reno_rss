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
const supportedPhases = new Set(["cold", "warm-http-cache", "service-worker-controlled"]);

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
    readySelector: ".workbench",
    routes: defaultRoutes,
    phases: ["cold", "warm-http-cache", "service-worker-controlled"],
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
    else if (name === "--ready-selector") options.readySelector = value;
    else if (name === "--routes") options.routes = value.split(",").filter(Boolean);
    else if (name === "--phases") options.phases = value.split(",").filter(Boolean);
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
  if (options.phases.length === 0 || options.phases.some((phase) => !supportedPhases.has(phase))) {
    throw new Error(`--phases must use one or more of: ${[...supportedPhases].join(", ")}`);
  }
  if (!options.readySelector) {
    throw new Error("--ready-selector must be a non-empty selector");
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

async function measureRoute(context, options, route, sampleIndex, phase) {
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

  try {
    await installObservers(page);
    const response = await page.goto(`${options.baseURL}${route}`, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    });
    await page.waitForSelector(options.readySelector, { state: "attached", timeout: 30_000 });
    await page.waitForTimeout(options.settleMs);

    const metrics = await page.evaluate(() => {
    const navigation = performance.getEntriesByType("navigation")[0];
    const paints = Object.fromEntries(
      performance.getEntriesByType("paint").map((entry) => [entry.name, entry.startTime]),
    );
    const resources = performance.getEntriesByType("resource");
    const resourceTransferBytesByInitiatorType = {};
    for (const resource of resources) {
      const type = resource.initiatorType || "other";
      resourceTransferBytesByInitiatorType[type] =
        (resourceTransferBytesByInitiatorType[type] ?? 0) + (resource.transferSize ?? 0);
    }
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
      resourceTransferBytesByInitiatorType,
      responseEndMs: navigation?.responseEnd ?? 0,
      serviceWorkerControlled: navigator.serviceWorker?.controller != null,
    };
    });

    return {
      browserErrors,
      failedResponses,
      httpStatus: response?.status() ?? null,
      metrics,
      phase,
      route,
      sampleIndex,
    };
  } finally {
    await page.close();
  }
}

async function createContext(browser, phase) {
  return browser.newContext({
    serviceWorkers: phase === "service-worker-controlled" ? "allow" : "block",
    viewport: { width: 1440, height: 1_000 },
  });
}

async function ensureServiceWorkerControl(context, options, route) {
  const page = await context.newPage();
  try {
    await page.goto(`${options.baseURL}${route}`, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.evaluate(async () => {
      if (!("serviceWorker" in navigator)) throw new Error("service workers are unavailable");
      await navigator.serviceWorker.ready;
    });
    await page.reload({ waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForFunction(() => navigator.serviceWorker.controller != null, undefined, { timeout: 10_000 });
  } finally {
    await page.close();
  }
}

function assertSampleHealthy(sample) {
  const failures = [
    ...sample.browserErrors.map((error) => error.kind),
    ...sample.failedResponses.map((failure) => `${failure.status} ${failure.url}`),
  ];
  if (failures.length > 0) {
    throw new Error(`baseline warmup failed for ${sample.route}: ${failures.join(", ")}`);
  }
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  const browser = await chromium.launch({ headless: true });
  const samples = [];

  try {
    for (const phase of options.phases) {
      for (const route of options.routes) {
        const runSample = async (sampleIndex, samplePhase) => {
          const context = await createContext(browser, phase);
          try {
            return await measureRoute(context, options, route, sampleIndex, samplePhase);
          } finally {
            await context.close();
          }
        };
        if (phase === "cold") {
          for (let index = 0; index < options.warmups; index += 1) {
            assertSampleHealthy(await runSample(index + 1, `${phase}:warmup`));
          }
          for (let index = 0; index < options.iterations; index += 1) {
            samples.push(await runSample(index + 1, phase));
          }
          continue;
        }
        const context = await createContext(browser, phase);
        try {
          if (phase === "service-worker-controlled") {
            await ensureServiceWorkerControl(context, options, route);
          }
          for (let index = 0; index < options.warmups; index += 1) {
            assertSampleHealthy(await measureRoute(context, options, route, index + 1, `${phase}:warmup`));
          }
          for (let index = 0; index < options.iterations; index += 1) {
            samples.push(await measureRoute(context, options, route, index + 1, phase));
          }
        } finally {
          await context.close();
        }
      }
    }

    const browserVersion = browser.version();
    const routeResults = options.phases.flatMap((phase) => options.routes.map((route) => {
      const routeSamples = samples.filter((sample) => sample.route === route && sample.phase === phase);
      const metricNames = Object.entries(routeSamples[0].metrics)
        .filter(([, value]) => typeof value === "number")
        .map(([name]) => name);
      const serviceWorkerControlled = routeSamples.every((sample) => sample.metrics.serviceWorkerControlled);
      if (phase === "service-worker-controlled" && !serviceWorkerControlled) {
        throw new Error(`service worker did not control every measured sample for ${route}`);
      }
      return {
        route,
        phase,
        samples: routeSamples,
        serviceWorkerControlled,
        summary: Object.fromEntries(metricNames.map((name) => [name, summarize(routeSamples, name)])),
      };
    }));
    const report = {
      schemaVersion: 2,
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
        phases: options.phases,
        readySelector: options.readySelector,
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
