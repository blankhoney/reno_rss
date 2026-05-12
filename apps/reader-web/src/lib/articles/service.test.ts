import assert from "node:assert/strict";
import test from "node:test";
import { MODULE_IDS, resolveArticlesListModuleId } from "./service";

test("resolveArticlesListModuleId defaults when module param absent", () => {
  assert.deepEqual(resolveArticlesListModuleId(false, null), { ok: true, moduleId: "unread" });
});

test("resolveArticlesListModuleId accepts every MODULE_IDS value when present", () => {
  for (const moduleId of MODULE_IDS) {
    assert.deepEqual(resolveArticlesListModuleId(true, moduleId), { ok: true, moduleId });
  }
});

test("resolveArticlesListModuleId rejects empty or unknown module", () => {
  assert.deepEqual(resolveArticlesListModuleId(true, ""), { ok: false });
  assert.deepEqual(resolveArticlesListModuleId(true, "nope"), { ok: false });
  assert.deepEqual(resolveArticlesListModuleId(true, "overall"), { ok: false });
});
