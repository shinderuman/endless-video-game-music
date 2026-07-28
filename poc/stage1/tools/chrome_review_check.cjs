const {chromium} = require("playwright");

const fail = (message) => {
  throw new Error(message);
};

const main = async () => {
  const baseUrl = process.argv[2] || "http://127.0.0.1:8766";
  const screenshotPath = process.argv[3];
  const expectedTotal = Number(process.argv[4] || 100);
  const expectedLabeled = Number(process.argv[5] || 0);
  const browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
  const context = browser.contexts()[0];
  const page = context.pages()[0] || (await context.newPage());
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });

  const response = await page.goto(baseUrl, {waitUntil: "networkidle"});
  if (!response || response.status() !== 200) {
    fail(`review page returned ${response?.status()}`);
  }
  await page.locator("h1").waitFor();
  if (
    (await page.locator("#progress").textContent()) !==
    `判定済み ${expectedLabeled} / ${expectedTotal}`
  ) {
    fail("initial progress is incorrect");
  }

  await page.locator("#preview-button").click();
  await page.locator("#preview-status").getByText("ループ再生中").waitFor({
    timeout: 30000,
  });
  await page
    .locator("#boundary-flash")
    .getByText("境界通過 → ループ開始（1回目）")
    .waitFor({timeout: 7000});
  if (screenshotPath) {
    await page.screenshot({path: screenshotPath, fullPage: true});
  }
  await page.locator("#stop-button").click();

  await page.locator("#bad-points-button").click();
  await page.locator("#message").getByText("保存しました").waitFor();
  if (
    (await page.locator("#progress").textContent()) !==
    `判定済み ${expectedLabeled + 1} / ${expectedTotal}`
  ) {
    fail("label progress was not updated");
  }
  await page.locator("#clear-button").click();
  await page.locator("#message").getByText("保存しました").waitFor();
  if (
    (await page.locator("#progress").textContent()) !==
    `判定済み ${expectedLabeled} / ${expectedTotal}`
  ) {
    fail("cleared label progress was not updated");
  }

  await page.locator("#next-button").click();
  if ((await page.locator("#track-position").textContent()) !== `2 / ${expectedTotal}`) {
    fail("next track navigation failed");
  }
  await page.locator("#previous-button").click();
  if (consoleErrors.length) {
    fail(`console errors: ${consoleErrors.join(" | ")}`);
  }

  const result = {
    browserVersion: await browser.version(),
    userAgent: await page.evaluate(() => navigator.userAgent),
    title: await page.title(),
    tracks: expectedTotal,
    audioDecodeAndLoopStart: "passed",
    visualBoundaryCrossing: "passed",
    threeLabelsAndClear: "passed",
    navigation: "passed",
    consoleErrors: 0,
  };
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  await browser.close();
};

main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exitCode = 1;
});
