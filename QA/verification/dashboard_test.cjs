// Drives the real dashboard in Chrome against the real API + THROWAWAY database.
const { createRequire } = require("module");
const req = createRequire("/Users/jo/concierge/vm/nav-test/");
const puppeteer = req("puppeteer-core");
const fs = require("fs");

const BASE = "http://127.0.0.1:18080";
const SHOTS = "/Users/jo/work-staging/dashboard-shots";
fs.mkdirSync(SHOTS, { recursive: true });
const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log((ok ? "PASS  " : "FAIL  ") + name + (ok ? "" : "  -> " + detail)); };

(async () => {
  const browser = await puppeteer.launch({
    executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new", args: ["--no-sandbox"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e));
  page.on("console", (m) => { if (m.type() === "error" && !/^Failed to load resource/.test(m.text())) errors.push("console: " + m.text()); });
  const bad = [];
  page.on("response", (r) => { if (r.status() >= 400) bad.push(`${r.request().method()} ${new URL(r.url()).pathname} ${r.status()}`); });
  const external = [];
  page.on("request", (r) => { const u = new URL(r.url()); if (u.origin !== BASE && u.protocol.startsWith("http")) external.push(r.url()); });
  page.on("dialog", async (d) => {
    if (d.type() === "prompt") await d.accept("Opted in on paper form, May 2026"); else await d.accept();
  });

  const text = () => page.$eval("body", (b) => b.innerText);
  const waitText = (t, timeout = 8000) => page.waitForFunction((x) => document.body.innerText.includes(x), { timeout }, t);
  const clickTab = async (label) => {
    await page.evaluate((l) => { [...document.querySelectorAll("#tabs button")].find((b) => b.textContent.startsWith(l)).click(); }, label);
  };
  const clickButton = async (label) => {
    await page.evaluate((l) => { [...document.querySelectorAll("#view button")].find((b) => b.textContent.trim() === l).click(); }, label);
  };
  const shot = (n) => page.screenshot({ path: `${SHOTS}/${n}.png`, fullPage: true });

  // ---- sign in
  await page.goto(BASE + "/admin-ui");
  await page.type("#token", "wrong-token"); await page.click("#go");
  await waitText("Wrong token");
  check("wrong token is refused", (await text()).includes("Wrong token"));
  await page.$eval("#token", (i) => (i.value = ""));
  await page.type("#token", "admin-test-token"); await page.click("#go");
  await page.waitForSelector("#app:not([hidden])");
  await waitText("Leads waiting for a reply");
  check("signed in, overview shows the waiting-leads stat", (await text()).includes("Leads waiting for a reply"));
  check("overview warns about a waiting lead", (await text()).includes("have been waiting longer than 15 minutes"), (await text()).slice(0, 300));
  await shot("1-overview");

  // ---- needs attention
  const tabLabel = await page.$eval("#tabs", (t) => t.innerText);
  check("tab shows a count badge for waiting leads", /needs attention\s*1/i.test(tabLabel.replace(/\n/g, " ")), tabLabel);
  await clickTab("needs attention");
  await waitText("Waiting for a reply");
  let t = await text();
  check("attention list shows the hot lead with minutes waiting", t.includes("Hana Ngata") && /42 min/.test(t) && t.includes("hot 88"), t.slice(0, 500));
  check("cold / contacted / fresh leads are not listed", !t.includes("Sam Li") && !t.includes("Priya Shah"));
  await shot("2-attention");
  await clickButton("Mark contacted");
  await waitText("Nobody is waiting");
  check("marking contacted clears the list", (await text()).includes("Nobody is waiting"));
  const tabAfter = await page.$eval("#tabs", (x) => x.innerText);
  check("tab badge disappears", !/needs attention\s*1/i.test(tabAfter.replace(/\n/g, " ")), tabAfter);

  // ---- leads
  await clickTab("leads");
  await waitText("Marketing consent");
  t = await text();
  check("leads table shows score badges", t.includes("hot 88") && t.includes("warm 52") && t.includes("cold 15"));
  await page.select("#leadFilter", "70");
  await page.waitForFunction(() => document.body.innerText.includes("Hana Ngata") && !document.body.innerText.includes("Sam Li"));
  t = await text();
  check("'Hot only' filter hides warm and cold leads", t.includes("Hana Ngata") && t.includes("Priya Shah") && !t.includes("Tom Baker"), t.slice(0, 400));
  await page.select("#leadFilter", "0");
  await waitText("Sam Li");
  await page.click("#sortScore");
  await waitText("Sam Li");
  await page.waitForFunction(() => document.querySelectorAll("#view tr").length > 3);
  const firstScore = await page.$eval("#view table tr:nth-child(2) .badge", (b) => b.textContent);
  check("'Highest score first' puts the top score first", firstScore === "hot 88", firstScore);
  const before = (await text()).split("Record consent").length - 1;
  await clickButton("Record consent");
  await page.waitForFunction((n) => (document.body.innerText.split("Record consent").length - 1) === n - 1, {}, before);
  check("recording marketing consent flips the lead to Yes", (await text()).split("Withdraw").length - 1 >= 3);
  await shot("3-leads");

  // ---- campaigns
  await clickTab("campaigns");
  await waitText("New campaign");
  check("campaigns tab warns that sending is switched off", (await text()).includes("switched off for this client"));
  await page.click("#createCampaign");
  await waitText("people would receive this email campaign");
  t = await text();
  const m = t.match(/(\d+)\s*people would receive/);
  check("preview counts only consented leads older than 30 days (the 42-minute-old one is excluded)", m && Number(m[1]) === 2, m && m[0]);
  check("preview explains why sending is blocked", t.includes("switched off for this client (campaigns_enabled)"));
  check("Send button is disabled while blocked", await page.$eval("#sendCampaign", (b) => b.disabled));
  check("sample message is personalised", /Hi (Old|Hana|Priya)/.test(t));
  await shot("4-campaign-preview");

  // ---- setup: switch campaigns on, SLA, scoring
  await clickTab("setup");
  await waitText("Lead scoring");
  await page.click("#f_campaigns_enabled");
  await page.click("#saveSettings");
  await waitText("Settings saved.");
  check("settings saved with campaigns switched on", true);
  await page.waitForSelector("#w_phone");
  await page.$eval("#w_phone", (i) => (i.value = "40"));
  await page.click("#saveScoring");
  await waitText("Saved. Existing leads keep");
  check("scoring weights saved", true);
  await page.click("#rescoreLeads");
  await waitText("Re-scored");
  t = await text();
  check("re-score reports counts", /Re-scored \d+ leads: \d+ hot, \d+ warm, \d+ cold/.test(t), t.slice(t.indexOf("Re-scored"), t.indexOf("Re-scored") + 80));
  await page.$eval("#w_hot_at", (i) => (i.value = "30")); await page.$eval("#w_warm_at", (i) => (i.value = "40"));
  await page.click("#saveScoring");
  await waitText("Error:");
  check("invalid weights (warm >= hot) show a clear error", (await text()).includes("warm_at must be lower than hot_at"), (await text()).slice(-300));
  await shot("5-setup");
  await page.click("#resetScoring");
  let resetOk = true;
  await page.waitForFunction(() => { const i = document.querySelector("#w_phone"); return i && i.value === "25"; }, { timeout: 8000 }).catch(() => { resetOk = false; });
  check("reset restores default weights (phone back to 25 after reload)", resetOk);

  // ---- campaign now sendable
  await clickTab("campaigns");
  await waitText("New campaign");
  let stalePreviewRefreshed = true;
  await page.waitForFunction(() => { const b = document.querySelector("#sendCampaign"); return b && !b.disabled; }, { timeout: 8000 }).catch(() => { stalePreviewRefreshed = false; });
  check("the preview left open is refreshed (no longer says 'switched off') when campaigns are turned on", stalePreviewRefreshed);
  await page.click("#createCampaign");
  await page.waitForFunction(() => document.querySelectorAll("#previewPanel").length === 1 && document.body.innerText.includes("Preview: Win-back"));
  let enabled = true;
  await page.waitForFunction(() => { const b = document.querySelector("#sendCampaign"); return b && !b.disabled; }, { timeout: 8000 }).catch(() => { enabled = false; });
  check("Send button enabled for a new draft once campaigns are on", enabled);
  await page.evaluate(() => document.querySelector("#sendCampaign").click());
  await waitText("Delivery");
  await page.waitForFunction(() => document.body.innerText.includes("queued"), { timeout: 8000 });
  t = await text();
  check("campaign sent: listed as queued with delivery counts", /queued/.test(t) && /pending/.test(t), t.slice(-400));
  await shot("6-campaign-sent");

  // ---- mobile layout
  await page.setViewport({ width: 390, height: 800 });
  await clickTab("overview");
  await waitText("Leads waiting for a reply");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check("no page-level horizontal scroll at 390px", overflow <= 1, overflow);
  await shot("7-mobile-overview");

  check("no JavaScript or page errors", errors.length === 0, errors.join(" | "));
  const expected = ["GET /admin/tenants 401", "PATCH /admin/tenants/demo 422", "GET /favicon.ico 404"];
  const unexpected = bad.filter((x) => !expected.includes(x));
  check("the only failed requests are the ones this test causes on purpose (wrong token, invalid weights, favicon)", unexpected.length === 0, unexpected.join(" | ") + "  [all: " + bad.join(", ") + "]");
  check("no requests to other origins", external.length === 0, external.join(" "));
  await browser.close();
  console.log(`\n${results.filter(Boolean).length}/${results.length} checks passed`);
  process.exit(results.every(Boolean) ? 0 : 1);
})().catch((e) => { console.error("TEST CRASHED:", e); process.exit(2); });
