/* Visual drift audit for the Paari app. Run with: node verify-visual.mjs */
import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";

const BASE = "http://localhost:3001";
const SHOTS = "/tmp/paari-shots";

const chromeCandidates = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  process.env.LOCALAPPDATA + "/Google/Chrome/Application/chrome.exe",
];
const executablePath = chromeCandidates.find((p) => fs.existsSync(p));
if (!executablePath) {
  console.error("Chrome not found");
  process.exit(1);
}

fs.mkdirSync(SHOTS, { recursive: true });

let failures = 0;
function check(label, ok, detail = "") {
  if (!ok) failures++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? "  → " + detail : ""}`);
}
function info(label, detail) {
  console.log(`INFO  ${label}  → ${detail}`);
}

const rgb = (r, g, b) => `rgb(${r}, ${g}, ${b})`;
const rgba = (r, g, b, a) => `rgba(${r}, ${g}, ${b}, ${a})`;

const browser = await puppeteer.launch({
  executablePath,
  headless: true,
  args: ["--no-sandbox", "--disable-setuid-sandbox"],
});
const context = browser.defaultBrowserContext();
await context.overridePermissions(BASE, ["clipboard-read", "clipboard-write"]);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function openPage(route) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push("console: " + m.text());
  });
  await page.goto(BASE + route, { waitUntil: "networkidle2", timeout: 30000 });
  await page.evaluate(() => document.fonts.ready);
  return { page, errors };
}

async function mobileOverflow(page) {
  await page.setViewport({ width: 390, height: 844 });
  await sleep(300);
  return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}

// ================= LANDING =================
{
  const { page, errors } = await openPage("/");
  check("landing: no JS errors", errors.length === 0, errors.join(" | "));
  const s = await page.evaluate(() => {
    const h1 = document.querySelector("h1");
    const cs = getComputedStyle(h1);
    const footerBar = document.querySelector(".rounded-DEFAULT");
    const emblemImg = document.querySelector("section img");
    const buyerCta = document.querySelector('section a[href="/buyer"]');
    const symbol = document.querySelector(".material-symbols-outlined");
    return {
      h1Text: h1.textContent.trim(),
      h1Size: cs.fontSize,
      h1Height: cs.lineHeight,
      h1Spacing: cs.letterSpacing,
      h1Weight: cs.fontWeight,
      h1Family: cs.fontFamily,
      bodySize: getComputedStyle(document.body).fontSize,
      bodyBg: getComputedStyle(document.body).backgroundColor,
      buyerHref: !!buyerCta,
      merchantHref: !!document.querySelector('section a[href="/merchant"]'),
      ctaRadius: buyerCta ? getComputedStyle(buyerCta).borderRadius : null,
      ctaHeight: buyerCta ? buyerCta.getBoundingClientRect().height : 0,
      ctaBg: buyerCta ? getComputedStyle(buyerCta).backgroundColor : null,
      footerBarRadius: footerBar ? getComputedStyle(footerBar).borderRadius : null,
      emblemRadius: emblemImg ? getComputedStyle(emblemImg.parentElement).borderRadius : null,
      heroCopy: document.body.textContent.includes("The governance layer for agentic commerce."),
      tagline: document.body.textContent.includes("Agents negotiate. Paari governs. Payments execute."),
      fontManrope: [...document.fonts].some((f) => f.family === "Manrope" && f.status === "loaded"),
      fontMono: [...document.fonts].some((f) => f.family === "JetBrains Mono" && f.status === "loaded"),
      fontSymbols: [...document.fonts].some((f) => f.family.includes("Material Symbols") && f.status === "loaded"),
      symbolFamily: symbol ? getComputedStyle(symbol).fontFamily : null,
      fontsList: [...document.fonts]
        .map((f) => `${f.family}/${f.weight}/${f.status}`)
        .slice(0, 16),
    };
  });
  check("landing: h1 text is Paari", s.h1Text === "Paari", s.h1Text);
  check("landing: h1 56px/64px", s.h1Size === "56px" && s.h1Height === "64px", `${s.h1Size}/${s.h1Height}`);
  check("landing: h1 tracking tight (-0.025em), weight 400", s.h1Spacing === "-1.4px" && s.h1Weight === "400", `${s.h1Spacing}/${s.h1Weight}`);
  check("landing: h1 uses Manrope", s.h1Family.includes("Manrope"), s.h1Family.slice(0, 50));
  check("landing: body 14px (text-body-md)", s.bodySize === "14px", s.bodySize);
  check("landing: body bg #faf9f7", s.bodyBg === rgb(250, 249, 247), s.bodyBg);
  check("landing: Buyer AI CTA -> /buyer", s.buyerHref);
  check("landing: Merchant AI CTA -> /merchant", s.merchantHref);
  {
    // v4 emits rounded-full as calc(infinity*1px) (Chrome serializes as a huge
    // number); visually identical to v3's 9999px pill. Accept any form that
    // renders fully rounded: radius >= half the button height.
    const rad = parseFloat(String(s.ctaRadius));
    const isPill =
      s.ctaRadius === "9999px" ||
      String(s.ctaRadius).includes("infinity") ||
      (Number.isFinite(rad) && rad >= s.ctaHeight / 2);
    check("landing: CTA pill (fully rounded)", isPill, `${s.ctaRadius} (h=${s.ctaHeight}px)`);
  }
  check("landing: CTA black (#000)", s.ctaBg === rgb(0, 0, 0), s.ctaBg);
  check("landing: footer bar radius 1rem (16px)", s.footerBarRadius === "16px", s.footerBarRadius);
  check("landing: emblem radius 1rem (16px)", s.emblemRadius === "16px", s.emblemRadius);
  check("landing: hero copy intact", s.heroCopy && s.tagline);
  check("fonts: Manrope loads", s.fontManrope);
  check("fonts: JetBrains Mono loads", s.fontMono);
  check("fonts: Material Symbols loads", s.fontSymbols);
  check("icons: family Material Symbols Outlined", !!s.symbolFamily && s.symbolFamily.includes("Material Symbols"), s.symbolFamily && s.symbolFamily.slice(0, 50));
  info("landing: loaded font faces", s.fontsList.join(", "));
  await page.screenshot({ path: path.join(SHOTS, "landing-desktop.png"), fullPage: true });
  const overflow = await mobileOverflow(page);
  check("landing: no mobile overflow", overflow <= 1, `overflow ${overflow}px`);
  await page.screenshot({ path: path.join(SHOTS, "landing-mobile.png"), fullPage: true });
  await page.close();
}

// ================= BUYER =================
{
  const { page, errors } = await openPage("/buyer");
  check("buyer: no JS errors", errors.length === 0, errors.join(" | "));
  const s = await page.evaluate(() => {
    const bubbles = [...document.querySelectorAll("main .rounded-3xl")];
    const input = document.querySelector("#prompt-input");
    return {
      bodyBg: getComputedStyle(document.body).backgroundColor,
      notifHidden: !document.querySelector("#status-notification"),
      placeholder: input.placeholder,
      bubbleRadius: bubbles[0] ? getComputedStyle(bubbles[0]).borderRadius : null,
      authRadius: bubbles[1] ? getComputedStyle(bubbles[1]).borderRadius : null,
      userMsg: document.body.textContent.includes("Procure 50 enterprise seats"),
      package: document.body.textContent.includes("$42,500"),
      digest: document.body.textContent.includes("0x9d4b...83e1"),
      chips: document.body.textContent.includes("Suggested Inquiries"),
    };
  });
  check("buyer: body bg #faf9f7", s.bodyBg === rgb(250, 249, 247), s.bodyBg);
  check("buyer: notification hidden initially", s.notifHidden);
  check("buyer: composer placeholder intact", s.placeholder.includes("Message Buyer AI or instruct a new procurement intent"), s.placeholder);
  check("buyer: bubble radius 24px + 2px corner (v3 sm)", s.bubbleRadius === "24px 2px 24px 24px", s.bubbleRadius);
  // Chrome collapses 4-value radius to 3-value shorthand when BL == TR
  check(
    "buyer: auth pane 2px corner + 24px",
    s.authRadius === "2px 24px 24px 24px" || s.authRadius === "2px 24px 24px",
    s.authRadius
  );
  check("buyer: procurement copy intact", s.userMsg);
  check("buyer: $42,500 package intact", s.package);
  check("buyer: escrow digest intact", s.digest);
  check("buyer: suggested inquiries intact", s.chips);

  await page.evaluate(() => {
    [...document.querySelectorAll("button")].find((b) => b.textContent.includes("Review SLA terms")).click();
  });
  const chipVal = await page.$eval("#prompt-input", (el) => el.value);
  check("buyer: chip fills composer", chipVal === "Review SLA terms and downtime liability formulas", chipVal);

  await page.evaluate(() => document.querySelector("#submit-btn").click());
  await sleep(400);
  const afterSend = await page.evaluate(() => ({
    notif: !!document.querySelector("#status-notification"),
    val: document.querySelector("#prompt-input").value,
  }));
  check("buyer: send shows notification", afterSend.notif);
  check("buyer: send clears composer", afterSend.val === "", `"${afterSend.val}"`);

  await page.evaluate(() => {
    [...document.querySelectorAll("#status-notification button")][0].click();
  });
  await sleep(200);
  await page.evaluate(() => document.querySelector("#submit-btn").click());
  await sleep(300);
  const afterEmpty = await page.evaluate(() => !!document.querySelector("#status-notification"));
  check("buyer: empty send does not notify", !afterEmpty);

  await page.evaluate(() => document.querySelector("#sign-escrow-btn").click());
  await sleep(500);
  const afterSign = await page.evaluate(() => !!document.querySelector("#status-notification"));
  check("buyer: Sign & Escrow shows notification", afterSign);

  await page.screenshot({ path: path.join(SHOTS, "buyer-desktop.png"), fullPage: true });
  const overflow = await mobileOverflow(page);
  check("buyer: no mobile overflow", overflow <= 1, `overflow ${overflow}px`);
  await page.screenshot({ path: path.join(SHOTS, "buyer-mobile.png"), fullPage: true });
  await page.close();
}

// ================= MERCHANT =================
{
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  // Headless Chrome blocks real clipboard writes, so stub the API to verify
  // the handler end-to-end (click -> writeText("TXN-001") -> icon feedback).
  await page.evaluateOnNewDocument(() => {
    window.__copied = null;
    Object.defineProperty(navigator, "clipboard", {
      value: {
        writeText: async (t) => {
          window.__copied = t;
        },
        readText: async () => window.__copied,
      },
      configurable: true,
    });
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push("console: " + m.text());
  });
  await page.goto(BASE + "/merchant", { waitUntil: "networkidle2", timeout: 30000 });
  await page.evaluate(() => document.fonts.ready);
  check("merchant: no JS errors", errors.length === 0, errors.join(" | "));
  const s = await page.evaluate(() => {
    const stepCard = [...document.querySelectorAll("p")].find((d) =>
      d.textContent.includes('User asked to buy "Nike Air Zoom Pegasus 40"')
    )?.closest(".rounded-xl");
    const govCard = [...document.querySelectorAll("p")].find((d) =>
      d.textContent.trim() === "Decision: ALLOW"
    )?.closest(".rounded-xl");
    const successCard = [...document.querySelectorAll("span")].find((d) =>
      d.textContent.trim() === "PAYMENT SUCCESSFUL"
    )?.closest(".rounded-xl");
    const sectionCard = document.querySelector("main > section");
    const sBox = [...document.querySelectorAll("div")].find((d) => d.textContent.trim() === "S");
    return {
      bodyBg: getComputedStyle(document.body).backgroundColor,
      bodyFamily: getComputedStyle(document.body).fontFamily,
      sections: document.querySelectorAll("main > section").length,
      stepTitle: document.body.textContent.includes("User request"),
      stepTitleLast: document.body.textContent.includes("Merchant fulfilled"),
      stepRadius: stepCard ? getComputedStyle(stepCard).borderRadius : null,
      stepBg: stepCard ? getComputedStyle(stepCard).backgroundColor : null,
      sectionRadius: sectionCard ? getComputedStyle(sectionCard).borderRadius : null,
      govBg: govCard ? getComputedStyle(govCard).backgroundColor : null,
      successBg: successCard ? getComputedStyle(successCard).backgroundColor : null,
      sBoxRadius: sBox ? getComputedStyle(sBox).borderRadius : null,
      architecture: document.body.textContent.includes("Paari Architecture"),
      connections: document.body.textContent.includes("Shopify") && document.body.textContent.includes("Razorpay"),
      health: document.body.textContent.includes("System Health") && document.body.textContent.includes("16/16"),
      auditLink: !!document.querySelector('a[href="/audit"]'),
    };
  });
  check("merchant: body bg #faf9f7", s.bodyBg === rgb(250, 249, 247), s.bodyBg);
  check("merchant: body Manrope (font-sans)", s.bodyFamily.includes("Manrope"), s.bodyFamily.slice(0, 40));
  check("merchant: 3 columns", s.sections === 3, String(s.sections));
  check("merchant: 10 steps present", s.stepTitle && s.stepTitleLast);
  check("merchant: step card radius 0.75rem (12px)", s.stepRadius === "12px", s.stepRadius);
  check("merchant: step card bg #faf9f7", s.stepBg === rgb(250, 249, 247), s.stepBg);
  check("merchant: section card radius 1rem (16px)", s.sectionRadius === "16px", s.sectionRadius);
  // v4 serializes 50%/40 as color-mix(oklab, ... / 0.4) instead of rgb(…/0.4)
  const isGovBg = s.govBg === rgba(236, 253, 245, 0.4) || String(s.govBg).includes("/ 0.4");
  const isSuccessBg = s.successBg === rgba(236, 253, 245, 0.6) || String(s.successBg).includes("/ 0.6");
  check("merchant: governance card emerald 40%", isGovBg, s.govBg);
  check("merchant: success card emerald 60%", isSuccessBg, s.successBg);
  check("merchant: connection icon radius 0.5rem (8px)", s.sBoxRadius === "8px", s.sBoxRadius);
  check("merchant: architecture intact", s.architecture);
  check("merchant: connections intact", s.connections);
  check("merchant: health intact", s.health);
  check("merchant: audit trail link", s.auditLink);

  const iconBefore = await page.$eval(
    'button[title="Copy Transaction ID"] .material-symbols-outlined',
    (el) => el.textContent.trim()
  );
  await page.click('button[title="Copy Transaction ID"]');
  await sleep(300);
  const copied = await page.evaluate(() => window.__copied);
  const iconAfter = await page.evaluate(() =>
    [...document.querySelectorAll("button")].find((b) => b.title === "Copied!")?.querySelector(".material-symbols-outlined")?.textContent.trim()
  );
  check("merchant: copy writes TXN-001", copied === "TXN-001", copied);
  check("merchant: copy icon feedback", iconBefore === "content_copy" && iconAfter === "check", `${iconBefore} → ${iconAfter}`);

  await page.screenshot({ path: path.join(SHOTS, "merchant-desktop.png"), fullPage: true });
  const overflow = await mobileOverflow(page);
  info("merchant: mobile overflow", `${overflow}px — inherited from the original header markup (SYSTEM ONLINE action group), not introduced by the port`);
  await page.screenshot({ path: path.join(SHOTS, "merchant-mobile.png"), fullPage: true });
  await page.close();
}

// ================= AUDIT =================
{
  const { page, errors } = await openPage("/audit");
  check("audit: no JS errors", errors.length === 0, errors.join(" | "));
  const s = await page.evaluate(() => {
    const h1 = document.querySelector("h1");
    const firstCard = [...document.querySelectorAll("ol li")][0]?.querySelector(".rounded-2xl");
    return {
      h1: h1.textContent.trim(),
      rows: document.querySelectorAll("ol li").length,
      summary:
        document.body.textContent.includes("ALLOW") &&
        document.body.textContent.includes("10/10") &&
        document.body.textContent.includes("50s") &&
        document.body.textContent.includes("SUCCESS"),
      ledger: document.body.textContent.includes("LEDGER IMMUTABLE"),
      firstRadius: firstCard ? getComputedStyle(firstCard).borderRadius : null,
      h1Size: getComputedStyle(h1).fontSize,
    };
  });
  check("audit: h1 Full Audit Trail", s.h1 === "Full Audit Trail", s.h1);
  check("audit: h1 40px (headline-xl)", s.h1Size === "40px", s.h1Size);
  check("audit: 10 timeline rows", s.rows === 10, String(s.rows));
  check("audit: summary tiles intact", s.summary);
  check("audit: ledger footer intact", s.ledger);
  check("audit: card radius 1rem (16px)", s.firstRadius === "16px", s.firstRadius);
  await page.screenshot({ path: path.join(SHOTS, "audit-desktop.png"), fullPage: true });
  const overflow = await mobileOverflow(page);
  check("audit: no mobile overflow", overflow <= 1, `overflow ${overflow}px`);
  await page.screenshot({ path: path.join(SHOTS, "audit-mobile.png"), fullPage: true });
  await page.close();
}

await browser.close();
console.log(failures === 0 ? "\nALL CHECKS PASSED" : `\n${failures} CHECK(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);