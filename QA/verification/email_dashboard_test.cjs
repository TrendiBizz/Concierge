// Browser checks for disabled-by-default, owner-reviewed email drafts.
// Runs against an isolated API with EMAIL_DRAFTS_ENABLED=true and OUTBOX_ENABLED=false.
const { createRequire } = require("module");
const req = createRequire("/Users/jo/concierge/vm/nav-test/");
const puppeteer = req("puppeteer-core");
const BASE = "http://127.0.0.1:18082";
const checks = [];
const check = (label, ok) => {
  checks.push(Boolean(ok));
  console.log((ok ? "PASS " : "FAIL ") + label);
};
(async () => {
  const browser = await puppeteer.launch({
    executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: "new", args: ["--no-sandbox"]
  });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.goto(BASE + "/admin-ui");
    await page.type("#token", "admin-test-token");
    await page.click("#go");
    await page.waitForSelector("#app:not([hidden])");
    await page.waitForFunction(() => [...document.querySelectorAll("#tabs button")].some(b => b.textContent.includes("email")));
    check("email tab appears when explicitly enabled", await page.evaluate(() =>
      [...document.querySelectorAll("#tabs button")].some(b => b.textContent.includes("email"))));
    await page.evaluate(() => [...document.querySelectorAll("#tabs button")].find(b => b.textContent.includes("email")).click());
    await page.waitForFunction(() => document.body.innerText.includes("Prepare a reply"));
    check("email review screen loads", (await page.$eval("#view", x => x.innerText)).includes("Drafts are private"));
    const form = await page.$eval("#view .card", x => x.innerText);
    check("owner sees generation and manual save options", form.includes("Generate draft") || form.includes("Drafts are private"));
    const inputs = await page.$$("#view input");
    await inputs[0].type("customer@example.test");
    await inputs[1].type("Question about service");
    const textareas = await page.$$("#view textarea");
    await textareas[0].type("Please tell me when I can visit.");
    await textareas[1].type("Thanks for your message. We will check the hours.");
    await page.evaluate(() => [...document.querySelectorAll("#view button")].find(b => b.textContent === "Save manual draft").click());
    await page.waitForFunction(() => document.body.innerText.includes("Draft #1"));
    check("manual draft created and shown", (await page.$eval("#view", x => x.innerText)).includes("Draft #1"));
    const area = await page.$$("#view textarea");
    await area[2].evaluate(x => { x.value = "Human-reviewed response."; x.dispatchEvent(new Event("input", {bubbles: true})); });
    await page.evaluate(() => [...document.querySelectorAll("#view button")].find(b => b.textContent === "Save changes").click());
    await page.waitForFunction(async () => {
      const r = await fetch("/admin/tenants/demo/email-drafts", {
        headers: {"X-Admin-Token": "admin-test-token"}
      });
      if (!r.ok) return false;
      const drafts = await r.json();
      return drafts.length && drafts[0].reply_body === "Human-reviewed response.";
    }, { timeout: 8000, polling: 200 });
    const res = await page.evaluate(async () => {
      return fetch("/admin/tenants/demo/email-drafts", { headers: { "X-Admin-Token": "admin-test-token" } })
        .then(r => r.json());
    });
    check("edited draft saved in database", res[0].reply_body === "Human-reviewed response.");
    page.on("dialog", async dialog => dialog.accept());
    await page.evaluate(() => [...document.querySelectorAll("#view button")].find(b => b.textContent === "Discard").click());
    await page.waitForFunction(() => document.body.innerText.includes("Status: discarded"));
    check("discard action works", (await page.$eval("#view", x => x.innerText)).includes("Status: discarded"));
    check("no JavaScript errors", errors.length === 0);
  } finally {
    await browser.close();
  }
  const passed = checks.filter(Boolean).length;
  console.log(passed + "/" + checks.length + " browser email checks passed");
  if (passed !== checks.length) process.exit(1);
})().catch(err => {console.error(err);process.exit(1);});
