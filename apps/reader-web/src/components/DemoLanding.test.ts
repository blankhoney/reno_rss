import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DemoLanding } from "./DemoLanding";
import type { DemoAccessConfig } from "@/lib/demo/access";

const config: DemoAccessConfig = {
  enabled: true,
  username: "demo",
  password: "demo-reader-2026",
  autheliaBaseUrl: "https://auth.blankhoney.xyz",
  targetUrl: "https://staging-ai-reader.blankhoney.xyz/?module=all&sort=default&lang=zh",
  allowedOrigin: "https://staging-ai-reader.blankhoney.xyz",
};

function render(configOverride: Partial<DemoAccessConfig> = {}) {
  return renderToStaticMarkup(
    React.createElement(DemoLanding, { config: { ...config, ...configOverride } }),
  );
}

test("DemoLanding renders project, GitHub and demo credentials", () => {
  const html = render();

  assert.match(html, /AI Reader/);
  assert.match(html, /RSS 智能阅读工作台/);
  assert.match(html, /https:\/\/github.com\/blankhoney\/reno_rss/);
  assert.match(html, /target="_blank"/);
  assert.match(html, /rel="noreferrer noopener"/);
  assert.match(html, /demo-reader-2026/);
  assert.match(html, /form action="\/api\/demo-login" method="post"/);
  assert.match(html, /以游客身份进入/);
});

test("DemoLanding disables one-click entry when credentials are missing", () => {
  const html = render({ password: undefined });

  assert.match(html, /Demo 暂未配置/);
  assert.match(html, /disabled=""/);
});
