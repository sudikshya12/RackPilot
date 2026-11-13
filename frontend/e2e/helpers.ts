import { expect, type Page } from "@playwright/test";

/** Drive the guided-demo dock with its own buttons until the demo reports completion. */
export async function driveDemo(page: Page, maxSteps = 60) {
  const dock = page.getByRole("region", { name: "Guided demonstration controls" });
  await expect(dock).toBeVisible();
  for (let i = 0; i < maxSteps; i++) {
    if (await dock.getByText("Demonstration complete").isVisible()) return;
    const btn = dock.getByRole("button", { name: /^(Next step|Mark reviewed)$/ });
    if ((await btn.count()) && (await btn.isEnabled())) {
      await btn.click();
      await page.waitForTimeout(1200);
    } else {
      await page.waitForTimeout(1500); // auto step: the simulator completes it as probes run
    }
  }
  const title = await dock.locator(".text-white").first().textContent().catch(() => "?");
  throw new Error(`demo did not complete; stuck at: ${title}`);
}

export async function resetSimulation(page: Page) {
  const r = await page.request.post("/api/simulation/reset");
  expect(r.ok()).toBeTruthy();
}

export async function noHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page should not scroll horizontally").toBeLessThanOrEqual(1);
}

/** Start a guided demo the way a user does: from the Demonstrations page via the API-backed start, then go to the overview. */
export async function startDemo(page: Page, key: string) {
  const r = await page.request.post(`/api/demos/${key}/start`);
  expect(r.ok()).toBeTruthy();
  await page.goto("/");
}
