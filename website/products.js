/*
  TRENDI — SITE SETTINGS (prices, checkout links and contact details)
  previewMode: false means buy buttons go directly to checkout.
*/
window.TRENDI = {
  previewMode: false,

  business: {
    name: "Trendi",
    domain: "trendibizz.com",
    email: "admin@trendibizz.com",
    currency: "USD",
    taxNote: "Prices in USD. NZ customers: 15% GST included (not added on top). Outside NZ: 0% GST."
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
      price: 499,
      per: "per month",
      terms: "3-month minimum, then month to month.",
      cta: "Start monthly",
      stripeLink: "https://buy.stripe.com/00wcN70IP4hJdwU8FpcEw06"
    },
    {
      id: "deposit",
      tab: "Deposit",
      price: 499,
      per: "deposit",
      terms: "Secures your start date. Credited against your first invoice.",
      cta: "Pay deposit",
      stripeLink: "https://buy.stripe.com/7sY7sNgHN6pR50obRBcEw05"
    }
  ],

  // Concierge monthly plan (USD 199/month, 3-month minimum). Yearly billing available on request.
  // checkout: false routes buttons back to /concierge-start without removing the checkout link.
  concierge: {
    checkout: true,
    monthly: { price: 199, stripeLink: "https://buy.stripe.com/eVq28s2qj9jfdxugHm04805" }
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
