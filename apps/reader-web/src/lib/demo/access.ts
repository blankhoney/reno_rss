export type DemoAccessConfig = {
  enabled: boolean;
  username?: string;
  password?: string;
  autheliaBaseUrl: string;
  targetUrl: string;
  allowedOrigin: string;
};

export type DemoLoginResult =
  | { ok: true; status: 303; location: string; cookies: string[] }
  | { ok: false; status: 403 | 503 | 502; error: string };

const DEFAULT_AUTHELIA_BASE_URL = "https://auth.blankhoney.xyz";
const DEFAULT_TARGET_URL = "https://staging-ai-reader.blankhoney.xyz/?module=all&sort=default&lang=zh";
const DEFAULT_ALLOWED_ORIGIN = "https://staging-ai-reader.blankhoney.xyz";

export function getDemoAccessConfig(env: NodeJS.ProcessEnv = process.env): DemoAccessConfig {
  return {
    enabled: env.DEMO_LANDING_ENABLED === "true",
    username: env.DEMO_USERNAME,
    password: env.DEMO_PASSWORD,
    autheliaBaseUrl: env.DEMO_AUTHELIA_BASE_URL || DEFAULT_AUTHELIA_BASE_URL,
    targetUrl: env.DEMO_TARGET_URL || DEFAULT_TARGET_URL,
    allowedOrigin: env.DEMO_ALLOWED_ORIGIN || DEFAULT_ALLOWED_ORIGIN,
  };
}

export function shouldRenderDemoLanding(
  searchParams: Record<string, string | string[] | undefined>,
  config: Pick<DemoAccessConfig, "enabled">,
): boolean {
  return config.enabled && Object.keys(searchParams).length === 0;
}

export function demoConfigReady(config: DemoAccessConfig): config is DemoAccessConfig & {
  username: string;
  password: string;
} {
  return config.enabled && Boolean(config.username) && Boolean(config.password);
}

function sameOrigin(value: string | null, allowedOrigin: string): boolean {
  if (!value) return false;
  try {
    return new URL(value).origin === allowedOrigin;
  } catch {
    return false;
  }
}

export function requestAllowedByOrigin(request: Request, allowedOrigin: string): boolean {
  const origin = request.headers.get("origin");
  if (origin != null) {
    return sameOrigin(origin, allowedOrigin);
  }
  return sameOrigin(request.headers.get("referer"), allowedOrigin);
}

function autheliaFirstFactorUrl(baseUrl: string): string {
  return new URL("/api/firstfactor", baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`).toString();
}

function getSetCookies(headers: Headers): string[] {
  const withGetSetCookie = headers as Headers & { getSetCookie?: () => string[] };
  if (typeof withGetSetCookie.getSetCookie === "function") {
    return withGetSetCookie.getSetCookie();
  }
  const singleCookie = headers.get("set-cookie");
  return singleCookie ? [singleCookie] : [];
}

export async function performDemoLogin(
  request: Request,
  config: DemoAccessConfig,
  fetcher: typeof fetch = fetch,
): Promise<DemoLoginResult> {
  if (!demoConfigReady(config)) {
    return { ok: false, status: 503, error: "demo_not_configured" };
  }
  if (!requestAllowedByOrigin(request, config.allowedOrigin)) {
    return { ok: false, status: 403, error: "invalid_origin" };
  }

  const response = await fetcher(autheliaFirstFactorUrl(config.autheliaBaseUrl), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      username: config.username,
      password: config.password,
      keepMeLoggedIn: true,
      targetURL: config.targetUrl,
      requestMethod: "GET",
    }),
  });

  const cookies = getSetCookies(response.headers);
  if (!response.ok || cookies.length === 0) {
    return { ok: false, status: 502, error: "demo_login_failed" };
  }

  return { ok: true, status: 303, location: config.targetUrl, cookies };
}
