import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AgentMarkdown } from "./AgentMarkdown";

test("AgentMarkdown renders basic markdown blocks and safe links", () => {
  const html = renderToStaticMarkup(
    React.createElement(AgentMarkdown, {
      text: [
        "## 结论",
        "这是 **重点**，查看 [来源](https://example.com/a?b=1)。",
        "",
        "- 第一条",
        "- 第二条",
        "",
        "1. 一",
        "2. 二",
        "",
        "> 引用内容",
        "",
        "行内 `code`。",
      ].join("\n"),
    }),
  );

  assert.match(html, /<h2>结论<\/h2>/);
  assert.match(html, /<strong>重点<\/strong>/);
  assert.match(html, /href="https:\/\/example.com\/a\?b=1"/);
  assert.match(html, /target="_blank"/);
  assert.match(html, /rel="noreferrer noopener"/);
  assert.match(html, /<ul><li>第一条<\/li><li>第二条<\/li><\/ul>/);
  assert.match(html, /<ol><li>一<\/li><li>二<\/li><\/ol>/);
  assert.match(html, /<blockquote><p>引用内容<\/p><\/blockquote>/);
  assert.match(html, /<code>code<\/code>/);
});

test("AgentMarkdown escapes raw HTML and leaves unsafe markdown links as text", () => {
  const html = renderToStaticMarkup(
    React.createElement(AgentMarkdown, {
      text: "不要执行 <script>alert(1)</script>，也不要打开 [bad](javascript:alert(1))。",
    }),
  );

  assert.equal(html.includes("<script>"), false);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.equal(html.includes('href="javascript:'), false);
  assert.match(html, /\[bad\]\(javascript:alert\(1\)\)/);
});

test("AgentMarkdown drops model meta preamble before required sections", () => {
  const html = renderToStaticMarkup(
    React.createElement(AgentMarkdown, {
      text: [
        "<tags>Let me provide the response following the format requirements.",
        "",
        "## 结论",
        "可以回答。",
      ].join("\n"),
    }),
  );

  assert.equal(html.includes("Let me provide"), false);
  assert.equal(html.includes("&lt;tags&gt;"), false);
  assert.match(html, /<h2>结论<\/h2>/);
  assert.match(html, /可以回答。/);
});
