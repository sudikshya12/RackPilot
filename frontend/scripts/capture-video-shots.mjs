// Captures high-DPI stills of the real running app for the product video.
// Usage: node scripts/capture-video-shots.mjs <outDir>   (needs backend :8000 and frontend :5173 running)
import { chromium } from "@playwright/test";
import fs from "node:fs";

const OUT = process.argv[2];
const BASE = "http://127.0.0.1:5173";
fs.mkdirSync(OUT, { recursive: true });
const boxes = {};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
const api = (path, method = "GET") => page.request.fetch(`${BASE}/api${path}`, { method }).then((r) => r.json());
// Hide transient UI chrome (demo bar, toasts) so shots are clean.
const CLEAN = `[aria-label="Guided demonstration controls"],[aria-label="Notifications"]{display:none!important}
  *{caret-color:transparent!important}`;

async function go(path) {
  await page.goto(BASE + path);
  await page.addStyleTag({ content: CLEAN });
  await page.waitForLoadState("networkidle").catch(() => {});
  await sleep(1400); // let entrance animations settle
}
async function boxOf(name, selector) {
  const b = await page.evaluate((sel) => {
    const el = typeof sel === "string" ? document.querySelector(sel) : null;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height };
  }, selector);
  if (b) (boxes[name] ??= {})[selector] = b;
  return b;
}
async function panelBox(shot, key, title) {
  const b = await page.evaluate((t) => {
    const h = [...document.querySelectorAll("main h2")].find((x) => x.textContent?.trim().startsWith(t));
    const el = h?.closest("section");
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height };
  }, title);
  if (b) (boxes[shot] ??= {})[key] = b;
}
async function shot(name, fullPage = false) {
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage });
  const size = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }));
  (boxes[name] ??= {}).page = fullPage ? size : { w: 1600, h: 900 };
  console.log("shot", name);
}
async function untilDemo(key, pred, tries = 60) {
  for (let i = 0; i < tries; i++) { const d = await api(`/demos/${key}`); if (pred(d)) return d; await sleep(1000); }
  throw new Error(`timeout waiting on ${key}`);
}
const next = (key) => api(`/demos/${key}/next`, "POST");

// 1) Calm overview
await api("/simulation/reset", "POST");
await go("/");
await shot("01_overview");
await panelBox("01_overview", "rack", "Infrastructure");
await panelBox("01_overview", "attention", "Needs attention");

// 2) Fault detected
await api("/demos/restore-service/start", "POST");
const d1 = await untilDemo("restore-service", (d) => d.run?.incident_id);
await go("/");
await shot("02_overview_incident");
await panelBox("02_overview_incident", "rack", "Infrastructure");
await panelBox("02_overview_incident", "attention", "Needs attention");
await boxOf("02_overview_incident", 'button[aria-label^="lab-srv-02"]');

// 3) Investigation with a wrong hypothesis rejected
await next("restore-service"); await next("restore-service"); await next("restore-service");
const inc = d1.run.incident_id;
await go(`/incidents/${inc}`);
await page.getByRole("button", { name: /systemctl_status/ }).first().click().catch(() => {});
await sleep(600);
await shot("03_incident_investigation", true);
for (const [k, t] of [["timeline", "Investigation timeline"], ["evidence", "Evidence"], ["hypotheses", "Hypotheses"], ["verification", "Verification"], ["metrics", "Metrics"]]) await panelBox("03_incident_investigation", k, t);

// 4) Correct repair, verified recovery
await next("restore-service");
await sleep(7500);
await next("restore-service");
await next("restore-service");
await go(`/incidents/${inc}`);
await shot("04_incident_resolved", true);
for (const [k, t] of [["verification", "Verification"], ["metrics", "Metrics"], ["timeline", "Investigation timeline"]]) await panelBox("04_incident_resolved", k, t);
await api("/demos/restore-service/exit", "POST");

// 5) Acceptance: fail, correct, re-test
await api("/demos/acceptance-retest/start", "POST");
await next("acceptance-retest");
await next("acceptance-retest");
await untilDemo("acceptance-retest", (d) => d.steps[1].done);
const intake = (await api("/acceptance/intakes")).find((x) => x.display_id === "INT-0001");
const run1 = intake.runs[0].id;
await go(`/acceptance/${intake.id}?run=${run1}`);
await shot("05_acceptance_fail", true);
await panelBox("05_acceptance_fail", "run", "Run #1");
await next("acceptance-retest"); await next("acceptance-retest"); await next("acceptance-retest");
await untilDemo("acceptance-retest", (d) => d.steps[4].done);
const intake2 = (await api("/acceptance/intakes")).find((x) => x.display_id === "INT-0001");
await go(`/acceptance/${intake.id}?compare=${run1},${intake2.runs.at(-1).id}`);
await shot("06_acceptance_compare", true);
await panelBox("06_acceptance_compare", "compare", "Run comparison");
await api("/demos/acceptance-retest/exit", "POST");

// 6) Infrastructure: rack + cable trace
await go("/infrastructure");
await shot("07_racks", true);
await panelBox("07_racks", "racks", "North Lab");
const cables = await api("/cables");
const trunk = cables.find((c) => c.label === "CBL-0205");
await go(`/infrastructure?tab=cables&cable=${trunk.id}`);
await sleep(1200);
await shot("08_cable_trace", true);
await panelBox("08_cable_trace", "trace", "Traced path");
await panelBox("08_cable_trace", "defects", "Documentation defects");

// 7) Component replacement with inventory reconciliation
await api("/demos/replace-component/start", "POST");
const d3 = await untilDemo("replace-component", (d) => d.run?.incident_id);
for (let i = 0; i < 5; i++) await next("replace-component"); // open, evidence, spare(viewed), reserve, consume
const dev = await api("/devices/lab-srv-04");
await go(`/spares?device=${dev.id}&incident=${d3.run.incident_id}`);
await shot("09_spares_workflow", true);
await panelBox("09_spares_workflow", "workflow", "Repair workflow");
await next("replace-component");                       // return record
await sleep(7000);
await next("replace-component"); await next("replace-component"); // verify, resolve
await go(`/assets/${dev.asset_id}?tab=audit`);
await shot("10_audit", true);
await go("/returns");
await shot("11_returns", true);
await api("/demos/replace-component/exit", "POST");

// 8) Closing overview
await api("/simulation/reset", "POST");
await go("/");
await shot("12_overview_final");

fs.writeFileSync(`${OUT}/boxes.json`, JSON.stringify(boxes, null, 2));
await browser.close();
console.log("done");
