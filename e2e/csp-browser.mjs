#!/usr/bin/env node
/* M1 browser CSP smoke check (Playwright).
 *
 * The dependency-free e2e/csp-smoke.mjs verifies the served header and that
 * each allowlisted host answers 200. This script drives the real map UI after
 * the narrowed CSP (PR #71) and fails on ANY CSP violation across:
 *   - initial map load and several zoom levels in/out;
 *   - panning to Tunis, Sfax and Djerba (different tiles and labels);
 *   - switching the UI language Arabic / French / English;
 *   - drawing a route from a Popular-trip chip, then clearing it.
 *
 * Usage: node e2e/csp-browser.mjs [base url]
 * Requires `playwright` resolvable from this project (CI installs it in the
 * workflow; locally it can be the globally installed package).
 */
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
let chromium;
// ESM's createRequire ignores NODE_PATH, so try explicit paths first (useful
// for local runs against a global install) before the normal resolution.
const candidates = [process.env.PLAYWRIGHT_PATH, "playwright"].filter(Boolean);
for (const spec of candidates) {
  try {
    ({ chromium } = require(spec));
    break;
  } catch (_) { /* try next */ }
}
if (!chromium) {
  console.error(
    "csp-browser: cannot resolve `playwright`. Install it (npm i -D playwright " +
    "&& npx playwright install chromium) or set PLAYWRIGHT_PATH to a playwright install."
  );
  process.exit(2);
}

const BASE = process.argv[2] || "http://127.0.0.1:8080";
const violations = [];
const consoleCspErrors = [];

const CSP_RE = /content security policy|csp\b|refused to (load|connect|execute|apply)/i;
const CITY_STOPS = [
  { name: "Tunis", center: [10.1815, 36.8065], zoom: 12 },
  { name: "Sfax", center: [10.7604, 34.7394], zoom: 12 },
  { name: "Djerba", center: [10.9500, 33.8075], zoom: 11 },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  // Collect CSP violations for the whole session, from the first navigation.
  await context.addInitScript(() => {
    window.__cspViolations = [];
    document.addEventListener("securitypolicyviolation", (ev) => {
      window.__cspViolations.push({
        directive: ev.effectiveDirective,
        blockedURI: ev.blockedURI,
        violatedDirective: ev.violatedDirective,
        sourceFile: ev.sourceFile,
      });
    });
  });
  page.on("console", (msg) => {
    if (msg.type() === "error" && CSP_RE.test(msg.text())) {
      consoleCspErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    if (CSP_RE.test(err.message || "")) consoleCspErrors.push("pageerror: " + err.message);
  });

  const step = (label) => console.log("  - " + label);

  try {
    // 1. Initial map load.
    step("load " + BASE);
    await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForFunction(() => !!window.__map, null, { timeout: 30000 });
    await page.waitForTimeout(1500); // allow style + glyph + sprite requests
    if (!(await page.evaluate(() => window.__map.loaded()))) {
      // loaded() can be false while tiles stream; require at least one tile.
      await page.waitForFunction(() => {
        const m = window.__map;
        return !!m && Object.keys(m.style ? m.style.sources : {}).length > 0;
      }, null, { timeout: 15000 }).catch(() => {});
    }

    // 2. Zoom in/out across several levels.
    step("zoom in/out across several levels");
    const baseZoom = await page.evaluate(() => window.__map.getZoom());
    for (const z of [baseZoom + 1, baseZoom + 2, baseZoom + 1, baseZoom, baseZoom - 1]) {
      await page.evaluate((level) => window.__map.setZoom(level), z);
      await sleep(350);
    }

    // 3. Pan to three cities with distinct tiles/labels.
    for (const city of CITY_STOPS) {
      step("pan to " + city.name);
      await page.evaluate(
        ({ center, zoom }) => window.__map.flyTo({ center, zoom, duration: 400 }),
        city
      );
      await sleep(900);
    }

    // 4. Switch language FR -> AR -> EN using the visible header buttons.
    step("switch language FR / AR / EN");
    for (const label of ["FR", "ع", "EN"]) {
      const btn = page.getByRole("button", { name: label, exact: true });
      await btn.click();
      await sleep(300);
    }

    // 5. Draw a route from a Popular-trip chip, then clear it.
    step("draw a route");
    const chip = page.getByRole("button", { name: /Tunis Marine.*La Marsa/ }).first();
    await chip.click();
    await page.waitForTimeout(1800); // route/plan + geometry load
    // A drawn route exposes a polyline source with data; assert something drew.
    const drewRoute = await page.evaluate(() => {
      const m = window.__map;
      const src = m.getSource("route");
      if (!src) return false;
      // MapLibre keeps live data in `_data`; serialize() is the public form.
      const d = typeof src.serialize === "function" ? src.serialize() : src._data;
      return !!(d && d.features && d.features.length > 0);
    });
    // Route geometry rendering can be delayed by slow upstream style/tiles; the
    // authoritative "a route was drawn" signal for CSP purposes is the route
    // result panel (which applies inline styles exercised by style-src).
    const routePanel = await page.evaluate(() =>
      document.body.innerText.includes("min") && /Bus|Train|Louage|Taxi/.test(document.body.innerText)
    );
    if (!drewRoute && !routePanel) {
      throw new Error("no route appeared after selecting a trip (neither geometry nor result panel)");
    }
    if (!drewRoute) console.log("  (note: route geometry not ready in time; result panel verified)");
    step("clear the route");
    // Emptying the departure input clears `from`, which drops `hasRoute` and
    // therefore the drawn route. Match the label across all three locales.
    const inputs = page.locator('input[aria-label]');
    let cleared = false;
    const nInputs = await inputs.count();
    for (let i = 0; i < nInputs; i++) {
      const el = inputs.nth(i);
      const label = (await el.getAttribute("aria-label")) || "";
      if (/from|départ|انطلاق/i.test(label)) {
        await el.click();
        await page.keyboard.press("Control+A");
        await page.keyboard.press("Backspace");
        // Commit the empty value by pressing Enter (picks no suggestion and
        // restores the welcome state once the field blurs via Escape).
        await page.keyboard.press("Escape");
        cleared = true;
        break;
      }
    }
    if (!cleared) throw new Error("could not find a departure input to clear");
    await sleep(500);
    const routeCleared = await page.evaluate(() => {
      const m = window.__map;
      const src = m.getSource("route");
      const d = typeof src?.serialize === "function" ? src.serialize() : src?._data;
      return !d || !d.features || d.features.length === 0;
    });
    if (drewRoute && !routeCleared) {
      throw new Error("route geometry remained after clearing the departure");
    }

    // 6. Collect CSP events from the entire session.
    const pageViolations = await page.evaluate(() => window.__cspViolations || []);
    violations.push(...pageViolations);
  } finally {
    await browser.close();
  }

  const problems = [];
  for (const v of violations) {
    problems.push(
      `securitypolicyviolation: ${v.effectiveDirective || v.violatedDirective} ` +
      `blocked ${v.blockedURI || "(unknown)"}` +
      (v.sourceFile ? ` @ ${v.sourceFile}` : "")
    );
  }
  for (const msg of consoleCspErrors) problems.push("console CSP error: " + msg);

  if (problems.length) {
    console.error("CSP browser smoke FAILED:\n- " + problems.join("\n- "));
    process.exit(1);
  }
  console.log("CSP browser smoke OK: map/zoom/pan/language/route produced zero CSP violations");
}

main().catch((e) => {
  console.error("CSP browser smoke ERROR: " + (e.stack || e.message));
  process.exit(1);
});
