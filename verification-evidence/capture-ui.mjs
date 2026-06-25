import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, "ui");
const BASE = process.env.WEB_URL || "http://localhost:3000";

const ORG_ID = "077a08b1-f115-4c41-8696-8db127c40f8a";
const BRAND_ID = "7269dbb5-a01f-4981-90f2-78fccef9f20f";
const STORAGE_KEY = "aicmo.tenant.selection.v1";

fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

// Clerk session refresh loops in headless — block it; demo /me works without JWT.
await page.route(/clerk\.accounts/, (route) => route.abort());

await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 60000 });
await page.evaluate(
  ({ key, orgId, brandId }) => {
    localStorage.setItem(key, JSON.stringify({ organization_id: orgId, brand_id: brandId }));
  },
  { key: STORAGE_KEY, orgId: ORG_ID, brandId: BRAND_ID },
);

await page.goto(`${BASE}/visuals`, { waitUntil: "domcontentloaded", timeout: 180000 });
await page.getByRole("heading", { name: "Visual studio" }).waitFor({ timeout: 180000 });
await page.getByText("Recent", { exact: true }).waitFor({ timeout: 180000 });
await page.waitForFunction(
  () => document.querySelectorAll("img[src*='media'], img[src*='renders']").length >= 1,
  null,
  { timeout: 120000 },
);
await page.waitForTimeout(2000);
await page.screenshot({ path: path.join(OUT, "visuals-page.png"), fullPage: true });
console.log("saved visuals-page.png");

const recent = page.locator("text=Recent").locator("xpath=ancestor::div[contains(@class,'rounded')]").first();
if (await recent.count()) {
  await recent.screenshot({ path: path.join(OUT, "recent-assets.png") });
  console.log("saved recent-assets.png");
}

await page.goto(`${BASE}/library`, { waitUntil: "domcontentloaded", timeout: 180000 });
await page.getByRole("button", { name: /Everything/ }).waitFor({ timeout: 180000 });
await page.waitForFunction(
  () => document.querySelectorAll("img[src*='media'], img[src*='renders']").length >= 1,
  null,
  { timeout: 120000 },
);
await page.waitForTimeout(2000);
await page.screenshot({ path: path.join(OUT, "library-page.png"), fullPage: true });
console.log("saved library-page.png");

await browser.close();
