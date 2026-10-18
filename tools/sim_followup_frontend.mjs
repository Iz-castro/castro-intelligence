// Usa apenas dependencias ja instaladas por npm ci no frontend.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
const require = createRequire(new URL("../frontend/package.json", import.meta.url));
const { build } = require("esbuild");
async function load(relative) {
  const result = await build({ entryPoints: [fileURLToPath(new URL(relative, import.meta.url))],
    bundle: true, write: false, platform: "node", format: "esm" });
  return import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`);
}
const t = await load("../frontend/src/features/followup/time.ts");
const { normalizeContact } = await load("../frontend/src/utils/normalization.ts");
const settings = { configured: true, timezone: "America/Sao_Paulo", holidays: [], preferred_time: null,
  contact_hours: Object.fromEntries(Array.from({length: 7}, (_,day) => [String(day), day < 5 ? [["08:00", "17:00"]] : []])) };
assert.equal(t.localToIso("2026-10-19T13:00"), "2026-10-19T16:00:00.000Z");
assert.equal(t.localInput("2026-10-19T16:00:00Z"), "2026-10-19T13:00");
assert.throws(() => t.localToIso("2026-02-30T10:00"));
assert.match(t.scheduleProblem("2026-10-19T10:00", null), /configurar/);
assert.equal(t.scheduleProblem("2026-10-19T10:00", settings), "");
assert.match(t.scheduleProblem("2026-10-24T10:00", settings), /sábados/);
assert.match(t.scheduleProblem("2026-10-19T17:00", settings), /fora/);
assert.equal(t.previousContactDate("2026-10-24T10:00", settings), "2026-10-23T10:00");
assert.equal(t.previousContactDate("2026-10-24T10:00", {...settings, holidays: ["2026-10-23"]}), "2026-10-22T10:00");
assert.equal(t.nextContactDate(new Date("2026-10-19T16:01:00Z"), new Date("2026-10-20T10:00:00Z"), settings), "2026-10-19T13:01");
assert.equal(t.nextContactDate(new Date("2026-10-19T20:01:00Z"), new Date("2026-10-20T10:00:00Z"), settings), null);
assert.equal(t.shortcutDate(1, settings, new Date("2026-10-23T13:00:00Z")), "2026-10-24T10:00", "Atalho nao desloca silenciosamente fim de semana");
assert.equal(normalizeContact({id: 1}, "1").commercial_contact_block, undefined);
assert.equal(normalizeContact({id: 1, commercial_contact_block: {active:false,version:1}}, "1").commercial_contact_block.active, false);
for (const malformed of [null, "false", {active:false}, {active:false,version:0}, {active:"false",version:1}]) {
  assert.equal(normalizeContact({id:1,commercial_contact_block:malformed}, "1").commercial_contact_block.active, true);
}
console.log("OK: 19 verificacoes de calendario, fuso e preferencia no frontend, sem rede");
