// Scrapes price data from a Cardmarket card page and sends it to background script.
(function () {
  // Detect Cloudflare challenge
  if (document.title.includes("Just a moment") ||
      document.querySelector("#challenge-running, #challenge-form, .cf-browser-verification")) {
    browser.runtime.sendMessage({ type: "price_data", data: { cloudflare: true } });
    return;
  }

  // Detect search page with no results or multiple results (not a card detail page)
  if (document.querySelector(".page-title-container h1")?.textContent?.includes("Search") ||
      !document.querySelector(".info-list-container")) {
    browser.runtime.sendMessage({ type: "price_data", data: { not_found: true } });
    return;
  }

  // Cardmarket condition codes → our condition names
  const COND_MAP = {
    mt: "Mint",
    nm: "Near Mint",
    ex: "Excellent",
    gd: "Good",
    lp: "Light Played",
    pl: "Played",
    po: "Poor",
  };

  // Cardmarket language labels → our lang codes
  const LANG_MAP = {
    English: "EN",
    French: "FR",
    German: "DE",
    Spanish: "ES",
    Italian: "IT",
    Portuguese: "PT",
    Japanese: "JA",
    Korean: "KO",
  };

  function scrape() {
    const data = {};

    // Extract from the info-list dl (dt/dd pairs)
    const dts = document.querySelectorAll(".info-list-container dt");
    dts.forEach((dt) => {
      const label = dt.textContent.trim();
      const dd = dt.nextElementSibling;
      if (!dd) return;
      const value = dd.textContent.trim();

      if (label === "Price Trend") data.trend = parsePrice(value);
      else if (label === "30-days average price") data.avg30 = parsePrice(value);
      else if (label === "7-days average price") data.avg7 = parsePrice(value);
      else if (label === "1-day average price") data.avg1 = parsePrice(value);
      else if (label.startsWith("From")) data.from = parsePrice(value);
    });

    // Extract offers with condition, language, and price
    const offers = [];
    document.querySelectorAll(".article-row").forEach((row) => {
      const condEl = row.querySelector("[class*='article-condition condition-']");
      if (!condEl) return;

      const condClass = [...condEl.classList].find((c) => c.startsWith("condition-"));
      if (!condClass) return;
      const condCode = condClass.replace("condition-", "");
      const condName = COND_MAP[condCode];
      if (!condName) return;

      // Get price: look for the bold price element specifically
      let price = null;
      for (const el of row.querySelectorAll(".color-primary.fw-bold")) {
        price = parsePrice(el.textContent);
        if (price != null) break;
      }
      if (price == null) return;

      // Find language: check aria-label, data-original-title, data-bs-original-title, title
      let lang = null;
      row.querySelectorAll(".product-attributes [aria-label], .product-attributes [data-original-title], .product-attributes [data-bs-original-title]").forEach((el) => {
        for (const attr of ["aria-label", "data-original-title", "data-bs-original-title", "title"]) {
          const val = el.getAttribute(attr);
          if (val && LANG_MAP[val]) { lang = LANG_MAP[val]; return; }
        }
      });

      offers.push({ condition: condName, lang, price });
    });

    data.offers = offers;
    return data;
  }

  function parsePrice(text) {
    // "26,94 €" -> 26.94
    const cleaned = text.replace(/[^\d,\.]/g, "").replace(",", ".");
    const num = parseFloat(cleaned);
    return isNaN(num) ? null : num;
  }

  const data = scrape();
  browser.runtime.sendMessage({ type: "price_data", data });
})();
