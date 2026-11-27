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

const BASE = process.argv[2] && process.argv[2] !== "--self-test" ? process.argv[2] : "http://127.0.0.1:8080";
const SELF_TEST = process.argv.includes("--self-test");
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

    // 0. Negative control: prove the violation collector is not vacuous.
    if (SELF_TEST) {
      step("self-test: inject a deliberate CSP violation");
      await page.evaluate(() => {
        const img = new Image();
        img.src = "https://example.com/csp-negative-control.png";
        document.body.appendChild(img);
      });
      await sleep(1500);
      const caught = (await page.evaluate(() => window.__cspViolations || [])).some(
        (v) => (v.blockedURI || "").includes("csp-negative-control")
      );
      if (!caught) throw new Error("self-test FAILED: collector did not catch an injected CSP violation");
      step("self-test passed: collector caught the injected violation");
      // Standalone negative control: we proved detection works, so stop here.
      // (Running the rest would re-report the deliberate violation as a failure.)
      return;
    }

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
    const routeFeatures = () => page.evaluate(() => {
      const src = window.__map.getSource("route");
      if (!src) return 0;
      const ser = typeof src.serialize === "function" ? src.serialize() : null;
      const d = ser?.data || ser || src._data?.geojson || src._data;
      return d && d.features ? d.features.length : 0;
    });
    // Hard assertion: wait up to ~10 s for the route geometry to appear.
    let drewRoute = false;
    for (let i = 0; i < 20; i++) {
      drewRoute = (await routeFeatures()) > 0;
      if (drewRoute) break;
      await sleep(500);
    }
    if (!drewRoute) {
      throw new Error("no route geometry in the 'route' source after selecting a trip");
    }
    // Additionally assert the result panel (inline styles exercised by style-src).
    const routePanel = await page.evaluate(() =>
      document.body.innerText.includes("min") && /Bus|Train|Louage|Taxi/.test(document.body.innerText)
    );
    if (!routePanel) throw new Error("route result panel did not appear after selecting a trip");
    // Snapshot CSP violations now — a navigation below resets window state.
    violations.push(...(await page.evaluate(() => window.__cspViolations || [])));
    await page.evaluate(() => { window.__cspViolations = []; });
    step("clear the route");
    // The planner has no explicit "clear" control: emptying an input only
    // changes its transient query and reverts on blur. A fresh navigation is
    // the supported way to return to the welcome/no-route state.
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => !!window.__map, null, { timeout: 30000 });
    await sleep(500);
    // Hard assertion: the geometry must be gone after clearing.
    if ((await routeFeatures()) > 0) {
      throw new Error("route geometry remained after clearing the departure");
    }
    step("route cleared: geometry gone and welcome state restored");

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
