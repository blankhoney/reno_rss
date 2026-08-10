import { lstatSync } from "node:fs";
import { isAbsolute, relative, resolve, sep, win32 } from "node:path";

const DIRECTORY_ERROR_SUFFIX =
  "must be a non-empty relative subdirectory of test-results without traversal or symlinks";

function failDirectory(variableName: string): never {
  throw new Error(`${variableName} ${DIRECTORY_ERROR_SUFFIX}`);
}

function assertNoExistingSymlink(
  variableName: string,
  baseDirectory: string,
  relativeDirectory: string,
): void {
  const components = relativeDirectory === "" ? [] : relativeDirectory.split(sep);
  let current = baseDirectory;

  for (const component of ["", ...components]) {
    if (component !== "") current = resolve(current, component);
    try {
      if (lstatSync(current).isSymbolicLink()) failDirectory(variableName);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
      throw error;
    }
  }
}

export function resolveTestResultsDirectory(options: {
  variableName: "PLAYWRIGHT_OUTPUT_DIR" | "PLAYWRIGHT_EVIDENCE_DIR";
  value: string;
  readerWebRoot?: string;
  allowTestResultsRoot?: boolean;
}): string {
  const {
    variableName,
    value,
    readerWebRoot = process.cwd(),
    allowTestResultsRoot = false,
  } = options;
  const trimmed = value.trim();
  const pathSegments = trimmed.split(/[\\/]/);

  if (
    trimmed === "" ||
    trimmed !== value ||
    isAbsolute(trimmed) ||
    win32.isAbsolute(trimmed) ||
    trimmed.includes("\\") ||
    pathSegments.some((segment) => segment === "." || segment === "..")
  ) {
    failDirectory(variableName);
  }

  const root = resolve(readerWebRoot);
  const testResultsRoot = resolve(root, "test-results");
  const candidate = resolve(root, trimmed);
  const relativeCandidate = relative(testResultsRoot, candidate);
  const isInside =
    relativeCandidate !== "" &&
    relativeCandidate !== ".." &&
    !relativeCandidate.startsWith(`..${sep}`) &&
    !isAbsolute(relativeCandidate);

  if ((!allowTestResultsRoot && !isInside) || (allowTestResultsRoot && relativeCandidate !== "" && !isInside)) {
    failDirectory(variableName);
  }

  assertNoExistingSymlink(variableName, testResultsRoot, relativeCandidate);
  return candidate;
}

export function resolveSafePngPath(directory: string, name: string): string {
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(name) || name === "." || name === "..") {
    throw new Error(
      "Screenshot name must be a safe PNG basename using only letters, numbers, hyphens, or underscores",
    );
  }

  const screenshotPath = resolve(directory, `${name}.png`);
  const relativeScreenshot = relative(directory, screenshotPath);
  if (
    relativeScreenshot === "" ||
    relativeScreenshot === ".." ||
    relativeScreenshot.startsWith(`..${sep}`) ||
    isAbsolute(relativeScreenshot)
  ) {
    throw new Error(
      "Screenshot name must be a safe PNG basename using only letters, numbers, hyphens, or underscores",
    );
  }
  return screenshotPath;
}
