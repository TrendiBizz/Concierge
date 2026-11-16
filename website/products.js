/* deploy: audit this-week fixes 2026-10-27 */
/*
  TRENDI — SITE SETTINGS (edit this file for prices, payment links and contact details)

  How to change things:
    - Price:            change "price" on a plan
    - Stripe checkout:  paste your Stripe Payment Link into "stripeLink" on a plan
    - Contact email:    change business.email
    - What is included: edit the "includes" list

  Live Stripe Payment Links (acct_1UUZfyRoqx25tip0), USD prices since 2026-10-31. previewMode false = buy buttons go to Stripe.
*/
window.TRENDI = {
  previewMode: false,

  business: {
    name: "Trendi",
    domain: "trendibizz.com",
    email: "admin@trendibizz.com",
    currency: "USD",
    taxNote: "Prices in USD, tax included."
  },

  // Real proof only. Leave enabled: false until you have genuine numbers and permission to show them.
  proof: {
    enabled: false,
    title: "What changed for one client",
    caption: "Replace with a real client result.",
    stats: [
      { label: "Daily clicks", from: "0", to: "0", period: "90 days" },
      { label: "Daily impressions", from: "0", to: "0", period: "90 days" }
    ]
  },

  // The one service, sold two ways. Each plan points at its own Stripe Payment Link.
  plans: [
    {
      id: "monthly",
      tab: "Monthly",
      price: 500,
      per: "per month",
      terms: "3-month minimum, then month to month.",
      cta: "Start monthly",
      stripeLink: "https://buy.stripe.com/00wcN70IP4hJdwU8FpcEw06"
    },
    {
      id: "deposit",
      tab: "Deposit",
      price: 500,
      per: "deposit",
      terms: "Secures your start date. Credited against your first invoice.",
      cta: "Pay deposit",
      stripeLink: "https://buy.stripe.com/7sY7sNgHN6pR50obRBcEw05"
    }
  ],

  // Concierge (USD 250 a month, 3-month minimum; yearly USD 2,700 = 10% off). Paste each Stripe Payment Link
  // below, for example "https://buy.stripe.com/abc123". While a link is empty the /concierge button stays
  // "Email to start" (it opens an email). Once a link is here the button goes to Stripe and says "Start ...".
  // 2026-11-15 (Jo: "add the buy button where required"): monthly Concierge link is
  // plink_1Ube9yJVm2iwIxUdbzwHgJhD on the Concierge Stripe account (price_1Ube9aJVm2iwIxUd0IcWNhGm, USD 250/month),
  // checked live that day. Every Concierge monthly buy button carries data-concierge-plan="monthly" and goes there.
  // 2026-11-15 (Jo: "so this should be on stripe its on the website"): yearly is buyable from day one.
  // Yearly link plink_1UbraFJVm2iwIxUd3gVPERTY (price_1UbnwwJVm2iwIxUdMoJ9g2Ve, USD 2,700/year = 12 x 250 less 10%),
  // automatic tax on, same settings as monthly. Buttons carry data-concierge-plan="yearly".
  // checkout is the one switch: false sends every button back to /concierge-start (the setup request form)
  // without deleting the link, e.g. if Stripe pauses the link again.
  concierge: {
    checkout: true,
    monthly: { price: 250, stripeLink: "https://buy.stripe.com/dRm7sM6GzeDz9he3UA04802" },
    yearly: { price: 2700, stripeLink: "https://buy.stripe.com/6oU28s8OH7b76528aQ04804" }
  },

  // Shown under whichever plan is selected.
  includes: [
    "AI mention tracking across ChatGPT, Perplexity, Gemini and Claude — mentions and links logged separately",
    "Third-party corroboration: directories, listicles, reviews and press targets (authentic only)",
    "Keyword research and a search map for every page",
    "In-depth articles each month",
    "Comparison and alternatives pages",
    "Page fixes: titles, copy, speed and internal links",
    "Index checks so search engines and AI crawlers can read your site",
    "Fact checks so your prices and features are right everywhere",
    "A short report every week"
  ],

  notIncluded: [
    "No ranking or AI-mention guarantees",
    "Not a penetration test or security audit",
    "Not unlimited articles or unlimited page builds",
    "Not paid ads management",
    "Not website redesign or custom software development"
  ]
};
