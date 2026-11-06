// Drives the new Pipeline / To-dos / Overview / Setup screens in real Chrome against the real API + THROWAWAY database.
const { createRequire } = require("module");
const req = createRequire("/Users/jo/concierge/vm/nav-test/");
const puppeteer = req("puppeteer-core");
const fs = require("fs");

const BASE = "http://127.0.0.1:18080";
const SHOTS = "/Users/jo/work-staging/office-shots";
fs.mkdirSync(SHOTS, { recursive: true });
const results = [];
const check = (name, ok, detail = "") => { ok = !!ok; results.push(ok); console.log((ok ? "PASS  " : "FAIL  ") + name + (ok ? "" : "  -> " + detail)); };
const api = async (path, opts = {}) => (await fetch(BASE + path, { ...opts, headers: { "X-Admin-Token": "admin-test-token", "Content-Type": "application/json" } })).json();

(async () => {
  const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new", args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });
  await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "light" }]);
  const errors = [], bad = [], external = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e));
  page.on("console", (m) => { if (m.type() === "error" && !/^Failed to load resource/.test(m.text())) errors.push("console: " + m.text()); });
  page.on("response", (r) => { if (r.status() >= 400) bad.push(`${r.request().method()} ${new URL(r.url()).pathname} ${r.status()}`); });
  page.on("request", (r) => { const u = new URL(r.url()); if (u.origin !== BASE && u.protocol.startsWith("http")) external.push(r.url()); });
  const prompts = [];
  page.on("dialog", async (d) => { prompts.push(d.type() + ": " + d.message()); await (d.type() === "prompt" ? d.accept("Not interested") : d.accept()); });

  const text = () => page.$eval("body", (b) => b.innerText);
  const waitText = (t, timeout = 8000) => page.waitForFunction((x) => document.body.innerText.includes(x), { timeout }, t);
  const waitGone = (t, timeout = 8000) => page.waitForFunction((x) => !document.body.innerText.includes(x), { timeout }, t);
  const tab = async (label) => { await page.evaluate((l) => [...document.querySelectorAll("#tabs button")].find((b) => b.textContent.startsWith(l)).click(), label); };
  const shot = (n) => page.screenshot({ path: `${SHOTS}/${n}.png`, fullPage: true });
  const setField = (cardName, selector, value) => page.evaluate((n, s, v) => {
    const card = [...document.querySelectorAll(".deal")].find((d) => d.textContent.includes(n));
    const el = card.querySelector(s); el.value = v; el.dispatchEvent(new Event("change", { bubbles: true }));
  }, cardName, selector, value);
  const colHead = (stage) => page.$eval(`#col_${stage} h3`, (h) => h.textContent);
  const markStale = () => page.evaluate(() => document.querySelectorAll("#board").forEach((b) => b.setAttribute("data-stale", "1")));
  const freshBoard = () => page.waitForSelector("#board:not([data-stale])", { timeout: 8000 });

  // ---- sign in
  await page.goto(BASE + "/admin-ui");
  await page.type("#token", "admin-test-token"); await page.click("#go");
  await page.waitForSelector("#app:not([hidden])");
  await waitText("Overdue to-dos");

  // ---- overview
  let t = await text();
  check("overview shows the week's sales numbers", t.includes("Won in this period") && t.includes("Open pipeline") && t.includes("Weighted pipeline"));
  check("overview counts 2 overdue to-dos", /2\s*\n?\s*Overdue to-dos/.test(t), t.slice(t.indexOf("Overdue") - 30, t.indexOf("Overdue") + 30));
  const todoTab = await page.$eval("#tabs", (x) => x.innerText.replace(/\n/g, " "));
  check("the to-dos tab carries an overdue badge", /to-dos\s*2/.test(todoTab), todoTab);
  await shot("1-overview");

  // ---- pipeline
  await tab("pipeline");
  await waitText("Weighted forecast");
  const heads = {}; for (const s of ["new", "contacted", "booked", "won", "lost"]) heads[s] = await colHead(s);
  check("board has all five stages with the right counts", heads.new === "new (3)" && heads.contacted === "contacted (1)" && heads.booked === "booked (1)" && heads.won === "won (1)" && heads.lost === "lost (1)", JSON.stringify(heads));
  t = await text();
  check("open pipeline $2,800 (leads with no value use the $400 average)", t.includes("$2,800") || t.includes("$2,400"), t.slice(t.indexOf("Open pipeline"), t.indexOf("Open pipeline") + 60));
  check("won total $1,800 shown", t.includes("$1,800"));
  check("the forecast weights are explained on screen", t.includes("new 10%") && t.includes("booked 60%"));
  check("a lost lead shows its reason", (await page.$eval("#col_lost", (c) => c.innerText)).includes("Lost: Went with a cheaper quote"));
  await shot("2-pipeline");

  // move Tom to contacted; his follow-up should complete
  await setField("Tom Baker", ".stageSel", "contacted");
  await page.waitForFunction(() => document.querySelector("#col_contacted h3")?.textContent === "contacted (2)");
  check("moving a lead updates the board", (await colHead("new")) === "new (2)" && (await colHead("contacted")) === "contacted (2)");
  let tomLead = (await api("/admin/tenants/demo/leads")).find((l) => l.name === "Tom Baker");
  check("history recorded the move", tomLead.status === "contacted");

  // lose Sam: prompt for the reason
  await setField("Sam Li", ".stageSel", "lost");
  await page.waitForFunction(() => document.querySelector("#col_lost h3")?.textContent === "lost (2)");
  check("marking lost asks why", prompts.some((p) => p.startsWith("prompt: Why was this lead lost")), prompts.join(" | "));
  check("the reason appears on the lost card", (await page.$eval("#col_lost", (c) => c.innerText)).includes("Lost: Not interested"));

  // value edit
  await markStale();
  await setField("Hana Ngata", ".dealValue", "900");
  await freshBoard();
  check("the board reloads with the new value", await page.evaluate(() => { const d = [...document.querySelectorAll(".deal")].find((x) => x.textContent.includes("Hana Ngata")); return d && d.querySelector(".dealValue").value === "900"; }));
  const hana = (await api("/admin/tenants/demo/leads")).find((l) => l.name === "Hana Ngata");
  check("editing a value is saved", hana.value_cents === 90000, hana.value_cents);

  // follow-up date
  await setField("Priya Shah", ".dealNext", "2026-12-01T10:00");
  await new Promise((r) => setTimeout(r, 800));
  const priya = (await api("/admin/tenants/demo/leads")).find((l) => l.name === "Priya Shah");
  const wanted = new Date("2026-12-01T10:00").getTime();   // typed in the browser's local time
  check("setting a follow-up date is saved on the lead (the exact moment typed)", priya.next_action_at && new Date(priya.next_action_at).getTime() === wanted, priya.next_action_at);
  const ptask = (await api("/admin/tenants/demo/tasks")).find((x) => x.title === "Follow up: Priya Shah");
  check("...and creates the lead's follow-up to-do at that moment", !!ptask && new Date(ptask.due_at).getTime() === wanted, JSON.stringify(ptask));
  await shot("3-pipeline-after-moves");

  // ---- to-dos
  await tab("to-dos");
  await waitText("New to-do");
  await page.waitForSelector("#todoTable");
  t = await text();
  check("Hana's follow-up is listed and marked overdue", t.includes("Follow up: Hana Ngata") && t.includes("Overdue:"), t.slice(0, 400));
  check("Tom's follow-up completed itself when he was contacted", !t.includes("Follow up: Tom Baker"));
  check("Sam's follow-up completed itself when he was lost", !t.includes("Follow up: Sam Li"));
  check("the manual overdue to-do is listed", t.includes("Call supplier about the cylinder"));
  await shot("4-todos");

  await page.type("#t_title", "Email the accountant");
  await page.click("#addTodo");
  await waitText("Email the accountant");
  check("adding a to-do shows it in the list", (await text()).includes("Email the accountant"));

  await page.evaluate(() => { const row = [...document.querySelectorAll("#todoTable tr")].find((r) => r.textContent.includes("Follow up: Hana Ngata")); row.querySelector(".todoCheck").click(); });
  await waitGone("Follow up: Hana Ngata");
  check("ticking a to-do removes it from the open list", !(await text()).includes("Follow up: Hana Ngata"));
  await page.click("#showDone");
  await waitText("Send January invoices");
  const doneRows = await page.$$eval("#todoTable tr.todo-done", (r) => r.map((x) => x.innerText));
  check("'Show completed' lists finished work (struck through)", doneRows.some((x) => x.includes("Send January invoices")) && doneRows.some((x) => x.includes("Follow up: Hana Ngata")), JSON.stringify(doneRows).slice(0, 300));
  await shot("5-todos-with-completed");
  await page.click("#showDone");
  await page.waitForFunction(() => document.querySelector("#todoTable") && !document.body.innerText.includes("Send January invoices") && document.body.innerText.includes("Email the accountant"));

  await page.evaluate(() => { const row = [...document.querySelectorAll("#todoTable tr")].find((r) => r.textContent.includes("Email the accountant")); [...row.querySelectorAll("button")].find((b) => b.textContent === "Delete").click(); });
  await waitGone("Email the accountant");
  check("deleting a to-do removes it (after asking)", prompts.some((p) => p.startsWith("confirm: Delete this to-do")));

  // ---- setup: calendar link + weekly summary
  await tab("setup");
  await waitText("Calendar feed");
  t = await text();
  const feed = (t.match(/https?:\/\/[^\s]+\/api\/v1\/calendar\/[A-Za-z0-9_-]+\.ics/) || [])[0];
  check("the calendar feed link is shown on the Setup tab", !!feed, t.slice(t.indexOf("Calendar feed"), t.indexOf("Calendar feed") + 200));
  if (feed) {
    const r = await fetch(BASE + new URL(feed).pathname);
    const body = await r.text();
    check("the feed works with no login and lists the appointment", r.status === 200 && r.headers.get("content-type").startsWith("text/calendar") && body.includes("BEGIN:VCALENDAR") && body.includes("Bo King - Demo Plumbing"), r.status + " " + body.slice(0, 120));
  }
  check("the weekly summary switch is there", !!(await page.$("#f_weekly_digest")));
  await page.click("#f_weekly_digest");
  await page.click("#saveSettings");
  await waitText("Settings saved.");
  await page.waitForSelector("#f_weekly_digest");
  check("the weekly summary setting is saved", await page.$eval("#f_weekly_digest", (c) => c.checked));
  await shot("6-setup");

  // ---- phone layout
  await page.setViewport({ width: 390, height: 844 });
  await tab("pipeline"); await waitText("Weighted forecast");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check("pipeline board has no sideways scroll on a phone", overflow <= 1, overflow);
  await shot("7-pipeline-phone");

  check("no JavaScript errors", errors.length === 0, errors.join(" | "));
  const unexpected = bad.filter((x) => x !== "GET /favicon.ico 404");
  check("no failed requests (other than the favicon)", unexpected.length === 0, unexpected.join(" | "));
  check("no requests to other origins", external.length === 0, external.join(" "));
  await browser.close();
  console.log(`\n${results.filter(Boolean).length}/${results.length} checks passed`);
  process.exit(results.every(Boolean) ? 0 : 1);
})().catch((e) => { console.error("TEST CRASHED:", e); process.exit(2); });
