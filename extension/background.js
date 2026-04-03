const WS_URL = "ws://127.0.0.1:8001";
const RECONNECT_DELAY = 3000;
const CONNECT_TIMEOUT = 5000;
const SCRAPE_TIMEOUT = 20000;
const PING_INTERVAL = 10000; // heartbeat every 10s to detect dead connections

let ws = null;
let reconnectTimer = null;
let pingTimer = null;

// Persistent scraping tab — reused across requests to keep cookies/session
let scrapeTabId = null;

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, RECONNECT_DELAY);
}

function connect() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return;
  }

  console.log(`[YugiPy] Connecting to ${WS_URL}...`);
  ws = new WebSocket(WS_URL);

  const timeout = setTimeout(() => {
    if (ws && ws.readyState === WebSocket.CONNECTING) {
      console.log("[YugiPy] Connection timeout, retrying...");
      ws.close();
    }
  }, CONNECT_TIMEOUT);

  ws.onopen = () => {
    clearTimeout(timeout);
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    console.log("[YugiPy] Connected");
    // Start heartbeat to detect dead connections
    if (pingTimer) clearInterval(pingTimer);
    pingTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        try { ws.send('{"action":"ping"}'); } catch { ws.close(); }
      }
    }, PING_INTERVAL);
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.action === "scrape_price") {
      scrapeCard(msg);
    }
  };

  ws.onclose = () => {
    clearTimeout(timeout);
    if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
    ws = null;
    console.log("[YugiPy] Disconnected, retrying in 3s...");
    scheduleReconnect();
  };

  ws.onerror = () => {};
}

async function ensureScrapeTab() {
  // Check if our persistent tab still exists
  if (scrapeTabId != null) {
    try {
      await browser.tabs.get(scrapeTabId);
      return scrapeTabId;
    } catch {
      scrapeTabId = null;
    }
  }
  // Create a new tab (only once)
  const tab = await browser.tabs.create({ url: "about:blank", active: true });
  scrapeTabId = tab.id;
  return scrapeTabId;
}

async function scrapeCard(msg) {
  try {
    const tabId = await ensureScrapeTab();

    // Navigate the existing tab to the new URL (keeps cookies!)
    await browser.tabs.update(tabId, { url: msg.url });

    let resolved = false;

    const listener = (message, sender) => {
      if (resolved) return;
      if (sender.tab?.id === tabId && message.type === "price_data") {
        resolved = true;
        browser.runtime.onMessage.removeListener(listener);
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            action: "price_result",
            card_id: msg.card_id,
            ...message.data,
          }));
        }
      }
    };
    browser.runtime.onMessage.addListener(listener);

    setTimeout(() => {
      if (resolved) return;
      resolved = true;
      browser.runtime.onMessage.removeListener(listener);
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          action: "price_result",
          card_id: msg.card_id,
          error: "timeout",
        }));
      }
    }, SCRAPE_TIMEOUT);
  } catch (e) {
    // Tab might have been closed by user — reset and report error
    scrapeTabId = null;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        action: "price_result",
        card_id: msg.card_id,
        error: e.message,
      }));
    }
  }
}

// Clean up scrape tab when extension unloads
browser.runtime.onSuspend?.addListener(() => {
  if (scrapeTabId != null) {
    browser.tabs.remove(scrapeTabId).catch(() => {});
  }
});

connect();
