#!/usr/bin/env node
// Extracts the JSON payload embedded in each ../src/js/vocab-*.js file and
// writes it to public/vocab/*.json so the site can fetch it at runtime.
//
// The vocab_builder.py script wraps its payload in
//   /*__LG_JSON__*/{...}/*__LG_END__*/
// markers so this extractor doesn't need to run a JS parser.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const SRC = path.resolve(ROOT, "..", "src", "js");
const DST = path.resolve(ROOT, "public", "vocab");

const SOURCES = [
  "vocab.js",
  "vocab-c1.js",
  "vocab-c2.js",
  "vocab-pte.js",
  "vocab-fr-basic.js",
];
const MARKER_RE = /\/\*__LG_JSON__\*\/([\s\S]*?)\/\*__LG_END__\*\//;

fs.mkdirSync(DST, { recursive: true });

let ok = 0;
let missing = 0;
for (const file of SOURCES) {
  const src = path.join(SRC, file);
  const out = path.join(DST, file.replace(/\.js$/, ".json"));
  if (!fs.existsSync(src)) {
    console.warn(`[extract-vocab] ${file}: source missing, skipping`);
    missing += 1;
    continue;
  }
  const text = fs.readFileSync(src, "utf8");
  const m = text.match(MARKER_RE);
  if (!m) {
    console.warn(`[extract-vocab] ${file}: no JSON marker, skipping`);
    missing += 1;
    continue;
  }
  const payload = JSON.parse(m[1]);
  fs.writeFileSync(out, JSON.stringify(payload));
  console.log(
    `[extract-vocab] ${file} -> ${path.relative(ROOT, out)} (${payload.items?.length ?? 0} items)`
  );
  ok += 1;
}
console.log(`[extract-vocab] wrote ${ok} file(s), skipped ${missing}.`);
