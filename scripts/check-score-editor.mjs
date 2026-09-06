import assert from "node:assert/strict";
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)(
  process.env.PLAYWRIGHT_MODULE || "playwright",
);
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH,
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: 1300, height: 1000 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
try {
  await page.goto(process.env.SCORE_URL || "http://127.0.0.1:4180");
  await page.click("#example");
  await page.waitForSelector('#staff [data-note="0"]');
  await page.locator('#staff [data-note="0"]').first().click();
  assert.equal(await page.locator("#pitch-up").isEnabled(), true);
  await page.click("#pitch-up");
  await page.waitForFunction(
    () =>
      document.querySelector("#piano rect title")?.textContent === "MIDI 61",
  );
  await page.click("#undo");
  await page.waitForFunction(
    () =>
      document.querySelector("#piano rect title")?.textContent === "MIDI 60",
  );
  await page.click('[data-view="jianpu"]');
  assert.equal(await page.locator(".jp-measure").count(), 4);
  await page.locator('#jianpu [data-note="1"]').first().click();
  await page.keyboard.press("ArrowUp");
  await page.waitForFunction(
    () =>
      document.querySelector('#piano rect[data-note="1"] title')
        ?.textContent === "MIDI 61",
  );
  await page.click("#shorter");
  await page.click("#split");
  await page.waitForFunction(
    () => document.querySelectorAll("#piano rect").length === 15,
  );
  await page.click("#example");
  await page.waitForFunction(
    () => document.querySelectorAll("#piano rect").length === 14,
  );
  await page.click('[data-view="piano"]');
  const rect = await page.locator("#piano svg").boundingBox();
  await page.mouse.move(rect.x + 200, rect.y + 100);
  await page.keyboard.down("Control");
  await page.mouse.wheel(0, -400);
  await page.keyboard.up("Control");
  await page.waitForFunction(
    () => Number(document.querySelector("#zoom").value) > 1,
  );
  assert.ok(
    (await page.locator("#piano svg").boundingBox()).width > rect.width,
  );
  await page.locator("#zoom").fill("1");
  await page.locator("#zoom").dispatchEvent("input");
  const target = await page.locator('#piano rect[data-note="0"]').boundingBox();
  await page.mouse.move(
    target.x + target.width / 2,
    target.y + target.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    target.x + target.width / 2 + 35,
    target.y + target.height / 2 - 25,
  );
  await page.mouse.up();
  await page.waitForFunction(
    () => document.querySelector("#undo").disabled === false,
  );
  await page.click('[data-view="staff"]');
  await page.screenshot({
    path: `${process.env.SCREENSHOT_DIR || "/tmp"}/score-desktop.png`,
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.click('[data-view="jianpu"]');
  await page.screenshot({
    path: `${process.env.SCREENSHOT_DIR || "/tmp"}/score-mobile.png`,
    fullPage: true,
  });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  assert.deepEqual(errors, []);
  console.log(
    "PASS: staff selection, cross-view pitch editing, undo, numbered bars, split, example reset, Ctrl-wheel zoom, drag, desktop/mobile layout",
  );
} finally {
  await browser.close();
}
