import { expect, test } from "@playwright/test";
import { noHorizontalOverflow } from "./helpers";

const VIEWPORTS = { desktop: { width: 1440, height: 900 }, tablet: { width: 834, height: 1112 }, mobile: { width: 390, height: 844 } };
const PAGES: [string, string, string][] = [
  ["overview", "/", "Operations Overview"],
  ["about", "/about", "About & Documentation"],
  ["incidents", "/incidents", "Critical unresolved first"],
  ["acceptance", "/acceptance/1", "Expected configuration"],
  ["infrastructure", "/infrastructure", "Racks, cabling and power"],
  ["spares", "/spares", "Inventory ledger"],
  ["assets", "/assets", "Serialized equipment"],
  ["asset-detail", "/assets/4", "lab-srv-04"],
  ["returns", "/returns", "Failed components"],
  ["case-study", "/projects/incident-recovery", "Reproduction"],
  ["demo", "/demo", "Restore a failed service"],
  ["runbooks", "/runbooks", "Standard procedures"],
  ["settings", "/settings", "Candidate profile"],
];

for (const [vp, size] of Object.entries(VIEWPORTS)) {
  test.describe(`${vp} ${size.width}x${size.height}`, () => {
    test.use({ viewport: size });
    for (const [name, path, text] of PAGES) {
      test(`${name} renders without horizontal overflow`, async ({ page }) => {
        await page.goto(path);
        await expect(page.locator("main").getByText(text).first()).toBeVisible();
        await page.waitForTimeout(700); // let entrance animations settle
        await noHorizontalOverflow(page);
        await page.screenshot({ path: `../docs/screenshots/${vp}-${name}.png`, fullPage: true });
      });
    }
  });
}

test("keyboard: skip link and global search are reachable", async ({ page }) => {
  await page.goto("/operations"); // legacy route redirects to the overview
  await expect(page).toHaveURL(/127\.0\.0\.1:5174\/$/);
  await expect(page.getByRole("heading", { name: "Operations Overview" })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog", { name: "Global search" })).toBeVisible();
  await page.getByLabel("Search query").fill("lab-srv-04");
  await expect(page.getByRole("option").first()).toBeVisible();
  await page.keyboard.press("Escape");
});

test("overview metrics match records and link to filtered views", async ({ page }) => {
  await page.goto("/");
  const ov = await (await page.request.get("/api/overview")).json();
  const healthy = page.getByRole("link", { name: /Healthy devices/ });
  await expect(healthy).toContainText(`${ov.devices.healthy}`);
  await expect(healthy).toContainText(`/ ${ov.devices.total}`);
  await expect(page.getByRole("link", { name: /Low-stock parts/ })).toContainText(`${ov.low_stock.total}`);
  await page.getByRole("link", { name: /Open incidents/ }).click();
  await expect(page).toHaveURL(/\/incidents\?open=1/);
  await page.goto("/");
  await page.getByRole("link", { name: /Low-stock parts/ }).click();
  await expect(page).toHaveURL(/\/spares\?low=1/);
  await expect(page.getByRole("navigation", { name: "Inventory" })).toBeVisible();
});

test("candidate and interview text is absent from the operational interface", async ({ page }) => {
  for (const path of ["/", "/incidents", "/infrastructure", "/assets"]) {
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
    const text = await page.locator("body").innerText();
    for (const banned of ["[Candidate Name]", "interview portfolio", "Independent interview lab", "Three projects, one lab"]) expect(text).not.toContain(banned);
  }
});

test("product tour: strip plays the film in a lightbox and can be dismissed", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => localStorage.removeItem("rackops-tour-dismissed"));
  await page.reload();
  const strip = page.getByRole("region", { name: "Product tour" });
  await expect(strip).toBeVisible();
  await expect(strip.locator("video")).toHaveAttribute("src", "/media/rackops-teaser.mp4");
  await strip.getByRole("button", { name: "Watch the film" }).click();
  const dialog = page.getByRole("dialog", { name: "RackOps Lab · Product tour" });
  await expect(dialog).toBeVisible();
  const video = dialog.locator("video");
  await expect(video).toHaveAttribute("poster", "/media/rackops-tour-poster.jpg");
  await expect(dialog.locator("track[kind=captions]")).toHaveCount(1);
  const head = await page.request.get("/media/rackops-tour.mp4", { headers: { Range: "bytes=0-1023" } });
  expect([200, 206]).toContain(head.status());
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await strip.getByRole("button", { name: "Dismiss product tour" }).click();
  await expect(strip).toBeHidden();
  await page.reload();
  await expect(page.getByRole("region", { name: "Product tour" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Watch tour" })).toBeVisible();
});
