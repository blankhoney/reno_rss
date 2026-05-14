import type { ReactNode } from "react";

type Block =
  | { type: "heading"; level: 1 | 2 | 3; text: string }
  | { type: "paragraph"; text: string }
  | { type: "unordered-list"; items: string[] }
  | { type: "ordered-list"; items: string[] }
  | { type: "quote"; text: string };

const INLINE_TOKEN = /(`[^`]+`|\*\*[^*]+\*\*|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))/g;

function isSafeHttpUrl(rawUrl: string): boolean {
  try {
    const url = new URL(rawUrl);
    return (
      (url.protocol === "http:" || url.protocol === "https:") &&
      !/[<>"']/.test(rawUrl)
    );
  } catch {
    return false;
  }
}

function isBlockStart(line: string): boolean {
  return (
    /^#{1,3}\s+/.test(line) ||
    /^[-*]\s+/.test(line) ||
    /^\d+[.)]\s+/.test(line) ||
    /^>\s?/.test(line)
  );
}

function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? "";
    const trimmed = line.trim();
    if (trimmed.length === 0) {
      index += 1;
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading != null) {
      blocks.push({
        type: "heading",
        level: heading[1].length as 1 | 2 | 3,
        text: heading[2],
      });
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length) {
        const item = /^[-*]\s+(.+)$/.exec(lines[index]?.trim() ?? "");
        if (item == null) break;
        items.push(item[1]);
        index += 1;
      }
      blocks.push({ type: "unordered-list", items });
      continue;
    }

    if (/^\d+[.)]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length) {
        const item = /^\d+[.)]\s+(.+)$/.exec(lines[index]?.trim() ?? "");
        if (item == null) break;
        items.push(item[1]);
        index += 1;
      }
      blocks.push({ type: "ordered-list", items });
      continue;
    }

    if (/^>\s?/.test(trimmed)) {
      const parts: string[] = [];
      while (index < lines.length) {
        const quote = /^>\s?(.*)$/.exec(lines[index]?.trim() ?? "");
        if (quote == null) break;
        parts.push(quote[1]);
        index += 1;
      }
      blocks.push({ type: "quote", text: parts.join(" ").trim() });
      continue;
    }

    const parts: string[] = [];
    while (index < lines.length) {
      const paragraphLine = lines[index]?.trim() ?? "";
      if (paragraphLine.length === 0 || isBlockStart(paragraphLine)) break;
      parts.push(paragraphLine);
      index += 1;
    }
    blocks.push({ type: "paragraph", text: parts.join(" ") });
  }

  return blocks;
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;

  for (const match of text.matchAll(INLINE_TOKEN)) {
    const start = match.index ?? 0;
    if (start > cursor) nodes.push(text.slice(cursor, start));

    const token = match[0];
    if (token.startsWith("`")) {
      nodes.push(<code key={start}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      nodes.push(<strong key={start}>{renderInline(token.slice(2, -2))}</strong>);
    } else {
      const label = match[2] ?? "";
      const href = match[3] ?? "";
      if (isSafeHttpUrl(href)) {
        nodes.push(
          <a key={start} href={href} target="_blank" rel="noreferrer noopener">
            {label}
          </a>,
        );
      } else {
        nodes.push(token);
      }
    }

    cursor = start + token.length;
  }

  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

export function AgentMarkdown({ text }: { text: string }) {
  const blocks = parseBlocks(text.trim());

  return (
    <div className="agentMarkdown">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const Heading = `h${block.level}` as "h1" | "h2" | "h3";
          return <Heading key={index}>{renderInline(block.text)}</Heading>;
        }
        if (block.type === "unordered-list") {
          return (
            <ul key={index}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInline(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.type === "ordered-list") {
          return (
            <ol key={index}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInline(item)}</li>
              ))}
            </ol>
          );
        }
        if (block.type === "quote") {
          return (
            <blockquote key={index}>
              <p>{renderInline(block.text)}</p>
            </blockquote>
          );
        }
        return <p key={index}>{renderInline(block.text)}</p>;
      })}
    </div>
  );
}
