#!/usr/bin/env node
/* M1 CSP smoke check (dependency-free).
 *
 * Asserts the served CSP allowlists exactly the hosts needed by the Maptoolkit
 * dark style and that each host answers 200. Full browser rendering (map,
 * logo, attribution, route draw, zero console CSP violations) is verified
 * manually with Playwright; this script is the repeatable CI-friendly part.
 */
const BASE = process.argv[2] || "http://127.0.0.1:8080";

const REQUIRED = [
  "https://styles.maptoolkit.org/dark.json",
  "https://tiles.maptoolkit.org/mtk.json",
  "https://icons.maptoolkit.org/sprite.json",
  "https://fonts.maptoolkit.org/Noto%20Sans%20Regular/0-255.pbf",
  "https://tiles.mapterhorn.com/8/135/99.webp",
];

async function main() {
  const res = await fetch(BASE + "/");
  const csp = res.headers.get("content-security-policy") || "";
  const problems = [];
  for (const directive of ["img-src", "connect-src", "font-src", "worker-src"]) {
    if (!csp.includes(directive)) problems.push(`CSP missing ${directive}`);
  }
  if (/\bhttps:\s*;/.test(csp)) problems.push("CSP still allows any https: host");
  for (const host of [
    "styles.maptoolkit.org", "tiles.maptoolkit.org", "icons.maptoolkit.org",
    "fonts.maptoolkit.org", "tiles.mapterhorn.com",
  ]) {
    if (!csp.includes(host)) problems.push(`CSP missing allowlisted host ${host}`);
  }
  for (const url of REQUIRED) {
    try {
      const r = await fetch(url, { method: "GET", signal: AbortSignal.timeout(10000) });
      if (r.status !== 200) problems.push(`${url} -> HTTP ${r.status}`);
    } catch (e) {
      problems.push(`${url} -> ${e.message}`);
    }
  }
  if (problems.length) {
    console.error("CSP smoke FAILED:\n- " + problems.join("\n- "));
    process.exit(1);
  }
  console.log("CSP smoke OK: allowlist and upstream hosts verified");
}
main().catch((e) => { console.error(e); process.exit(1); });
