import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const skillsRoot = path.join(repositoryRoot, ".agents", "skills");

const manifest = [
  {
    directory: "frontend-excellence-goal",
    files: ["SKILL.md", "START.md", "goal.md", "context.md", "execution.md", "acceptance.md", "evidence.md"],
  },
  {
    directory: "reader-web-audit",
    files: ["SKILL.md", "references/audit-checklist.md", "evals/evals.json"],
  },
];

const errors = [];

function display(relativePath) {
  return path.relative(repositoryRoot, relativePath) || ".";
}

function requireFile(relativePath) {
  const absolutePath = path.join(skillsRoot, relativePath);
  try {
    if (!fs.statSync(absolutePath).isFile()) {
      errors.push(`${display(absolutePath)} is not a regular file`);
    }
  } catch {
    errors.push(`${display(absolutePath)} is missing`);
  }
  return absolutePath;
}

function unquoteScalar(value) {
  const trimmed = value.trim();
  if (trimmed.length >= 2) {
    const first = trimmed[0];
    const last = trimmed.at(-1);
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return trimmed.slice(1, -1);
    }
  }
  return trimmed;
}

function readFrontmatter(absolutePath) {
  let lines;
  try {
    lines = fs.readFileSync(absolutePath, "utf8").split(/\r?\n/);
  } catch {
    return null;
  }

  if (lines[0]?.trim() !== "---") {
    errors.push(`${display(absolutePath)} must start with YAML frontmatter`);
    return null;
  }

  // This deliberately validates the small scalar contract we rely on instead of
  // pretending to implement every skill runtime's complete YAML parser without a dependency.
  const closingIndex = lines.slice(1, 65).findIndex((line) => line.trim() === "---");
  if (closingIndex === -1) {
    errors.push(`${display(absolutePath)} has no frontmatter closing marker in the first 64 lines`);
    return null;
  }

  const fields = new Map();
  for (const line of lines.slice(1, closingIndex + 1)) {
    const match = /^(name|description|argument-hint|disable-model-invocation):\s*(.*)$/.exec(line);
    if (!match) continue;
    const [, key, value] = match;
    if (fields.has(key)) {
      errors.push(`${display(absolutePath)} repeats frontmatter field ${key}`);
    } else {
      fields.set(key, value);
    }
  }
  return fields;
}

for (const skill of manifest) {
  const skillDirectory = path.join(skillsRoot, skill.directory);
  try {
    if (!fs.statSync(skillDirectory).isDirectory()) {
      errors.push(`${display(skillDirectory)} is not a directory`);
      continue;
    }
  } catch {
    errors.push(`${display(skillDirectory)} is missing`);
    continue;
  }

  for (const relativeFile of skill.files) requireFile(path.join(skill.directory, relativeFile));

  const skillPath = path.join(skillDirectory, "SKILL.md");
  const frontmatter = readFrontmatter(skillPath);
  if (frontmatter == null) continue;

  for (const field of ["name", "description", "argument-hint", "disable-model-invocation"]) {
    if (!frontmatter.has(field)) {
      errors.push(`${display(skillPath)} is missing frontmatter field ${field}`);
    }
  }

  if (unquoteScalar(frontmatter.get("name") ?? "") !== skill.directory) {
    errors.push(`${display(skillPath)} name must equal ${skill.directory}`);
  }
  if (unquoteScalar(frontmatter.get("description") ?? "") === "") {
    errors.push(`${display(skillPath)} description must not be empty`);
  }
  if (unquoteScalar(frontmatter.get("argument-hint") ?? "") === "") {
    errors.push(`${display(skillPath)} argument-hint must not be empty`);
  }
  if ((frontmatter.get("disable-model-invocation") ?? "").trim() !== "true") {
    errors.push(`${display(skillPath)} must set disable-model-invocation: true`);
  }

  if (skill.directory === "reader-web-audit") {
    const evalPath = path.join(skillDirectory, "evals", "evals.json");
    try {
      const evals = JSON.parse(fs.readFileSync(evalPath, "utf8"));
      if (evals?.skill_name !== "reader-web-audit") {
        errors.push(`${display(evalPath)} skill_name must be reader-web-audit`);
      }
    } catch (error) {
      errors.push(`${display(evalPath)} is not valid JSON: ${error.message}`);
    }
  }
}

if (errors.length > 0) {
  console.error(errors.map((error) => `- ${error}`).join("\n"));
  process.exitCode = 1;
} else {
  console.log(`Validated ${manifest.length} native project skills and their required supporting files.`);
}
