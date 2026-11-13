import { expect, test } from "@playwright/test";
import { driveDemo, resetSimulation, startDemo } from "./helpers";

test.beforeEach(async ({ page }) => { await page.goto("/"); await resetSimulation(page); });

test("Demo 1: restore a failed service — wrong hypothesis rejected, verified recovery", async ({ page }) => {
  await startDemo(page, "restore-service");
  await driveDemo(page);
  // Back on the incident: resolved, with a FAILED verification in history and a passing final one
  const demo = await (await page.request.get("/api/demos/restore-service")).json();
  await page.goto(`/incidents/${demo.run.incident_id}`);
  await expect(page.getByText("resolved").first()).toBeVisible();
  const inc = await (await page.request.get(`/api/incidents/${demo.run.incident_id}`)).json();
  expect(inc.verifications.some((v: { passed: boolean }) => !v.passed)).toBeTruthy();
  expect(inc.verifications.at(-1).passed).toBeTruthy();
  expect(inc.metrics.detection_latency_s).toBe(3);
  await page.getByRole("tab", { name: "Summary" }).click();
  await expect(page.getByRole("heading", { name: /Post-incident summary/ }).first()).toBeVisible();
});

test("Demo 2: reject and re-test a misconfigured server — FAIL then PASS, runs immutable", async ({ page }) => {
  await startDemo(page, "acceptance-retest");
  await driveDemo(page);
  const intake = (await (await page.request.get("/api/acceptance/intakes")).json()).find((x: { display_id: string }) => x.display_id === "INT-0001");
  expect(intake.runs.map((r: { disposition: string }) => r.disposition)).toEqual(["FAIL", "PASS"]);
  await page.goto(`/acceptance/${intake.id}?compare=${intake.runs[0].id},${intake.runs[1].id}`);
  await expect(page.getByText("Run comparison")).toBeVisible();
  await expect(page.getByText("changed").first()).toBeVisible();
  const report = await page.request.get(`/api/acceptance/runs/${intake.runs[0].id}/report.json`);
  const rj = await report.json();
  expect(rj.disposition).toBe("FAIL");
  expect(rj.source_type).toBe("SIMULATED");
});

test("Demo 3: replace a failed PSU — reserve, consume, return, audit", async ({ page }) => {
  await page.goto("/");
  const before = (await (await page.request.get("/api/spares")).json()).stock.find((s: { part_number: string }) => s.part_number === "NL-PSU-800P");
  await startDemo(page, "replace-component");
  await driveDemo(page);
  const after = (await (await page.request.get("/api/spares")).json()).stock.find((s: { part_number: string }) => s.part_number === "NL-PSU-800P");
  expect(after.on_hand).toBe(before.on_hand - 1);
  expect(after.reserved).toBe(0);
  await page.goto("/returns");
  await expect(page.getByText("NL-AST-P04B").first()).toBeVisible();
  const dev = await (await page.request.get("/api/devices/lab-srv-04")).json();
  const actions = dev.audit.map((a: { action: string }) => a.action);
  for (const a of ["reservation.create", "reservation.consume", "return.create", "incident.resolved"]) expect(actions).toContain(a);
});

test("Reset removes simulation records but keeps imported samples", async ({ page }) => {
  await page.goto("/");
  await page.request.post("/api/integrations/alertmanager/sample");
  await page.request.post("/api/scenarios/svc-stopped/start");
  await resetSimulation(page);
  const incs = (await (await page.request.get("/api/incidents?limit=200")).json()).items;
  expect(incs.filter((i: { source_type: string }) => i.source_type === "SIMULATED")).toHaveLength(0);
  expect(incs.filter((i: { source_type: string }) => i.source_type === "IMPORTED_SAMPLE")).toHaveLength(1);
});

test("Completed demo collapses to a dismissible card that does not cover the dashboard", async ({ page }) => {
  await startDemo(page, "acceptance-retest");
  await driveDemo(page);
  const dock = page.getByRole("region", { name: "Guided demonstration controls" });
  const box = await dock.boundingBox();
  expect(box!.height).toBeLessThan(140);
  expect(box!.width).toBeLessThan(400);
  await dock.getByRole("button", { name: "Close", exact: true }).click();
  await expect(dock).toBeHidden();
});
