import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const OUT = path.join(__dirname, "../../../../verification-evidence/ui");
const BASE = process.env.WEB_URL || "http://localhost:3000";

fs.mkdirSync(OUT, { recursive: true });

async function shot(page, name) {
  const file = path.join(OUT, name);
  await page.screenshot({ path: file, fullPage: true });
  console.log("saved", file);
}

async function waitForThumbnails(page, min = 1) {
  await page.waitForFunction(
    (n) => document.querySelectorAll("img[src*='media'], img[src*='renders']").length >= n,
    min,
    { timeout: 120_000 },
  );
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  // /visuals — Recent panel + main preview
  await page.goto(`${BASE}/visuals`, { waitUntil: "domcontentloaded", timeout: 120_000 });
  await page.getByRole("heading", { name: "Recent" }).waitFor({ timeout: 120_000 });
  await waitForThumbnails(page, 1);
  await page.waitForTimeout(1500);
  await shot(page, "visuals-page.png");

  // Recent panel close-up (right column)
  const recentCard = page.locator("text=Recent").locator("xpath=ancestor::div[contains(@class,'rounded')]").first();
  if (await recentCard.count()) {
    await recentCard.screenshot({ path: path.join(OUT, "recent-assets.png") });
    console.log("saved recent-assets.png");
  }

  // /library — unified asset grid
  await page.goto(`${BASE}/library`, { waitUntil: "domcontentloaded", timeout: 120_000 });
  await page.getByRole("button", { name: /Everything/ }).waitFor({ timeout: 120_000 });
  await waitForThumbnails(page, 1);
  await page.waitForTimeout(1500);
  await shot(page, "library-page.png");

  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
