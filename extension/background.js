const WS_URLS = [
  "wss://localhost:8000/ws/cardmarket",
  "ws://localhost:8000/ws/cardmarket",
];
let ws = null;
let reconnectTimer = null;
let wsUrlIndex = 0;

function connect() {
  const url = WS_URLS[wsUrlIndex];
  console.log(`[YugiPy] Trying ${url}...`);
  ws = new WebSocket(url);

  ws.onopen = () => {
    console.log(`[YugiPy] Connected via ${url}`);
    if (reconnectTimer) { clearInterval(reconnectTimer); reconnectTimer = null; }
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.action === "scrape_price") {
      scrapeCard(msg);
    }
  };

  ws.onclose = () => {
    console.log("[YugiPy] Disconnected, retrying in 5s...");
    // Alternate between wss and ws on each retry
    wsUrlIndex = (wsUrlIndex + 1) % WS_URLS.length;
    if (!reconnectTimer) reconnectTimer = setInterval(connect, 5000);
  };

  ws.onerror = () => ws.close();
}

async function scrapeCard(msg) {
  try {
    const tab = await browser.tabs.create({ url: msg.url, active: false });

    // Wait for content script to send back the data
    const listener = (message, sender) => {
      if (sender.tab?.id === tab.id && message.type === "price_data") {
        browser.runtime.onMessage.removeListener(listener);
        browser.tabs.remove(tab.id);
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

    // Timeout: close tab after 15s if no response
    setTimeout(() => {
      browser.runtime.onMessage.removeListener(listener);
      browser.tabs.remove(tab.id).catch(() => {});
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          action: "price_result",
          card_id: msg.card_id,
          error: "timeout",
        }));
      }
    }, 15000);
  } catch (e) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        action: "price_result",
        card_id: msg.card_id,
        error: e.message,
      }));
    }
  }
}

connect();
