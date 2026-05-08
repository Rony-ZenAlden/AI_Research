// Auto-reconnecting WebSocket client for the Realtime Hub.
// Exponential backoff up to 30s; reconnect picks up the latest JWT.
export class RealtimeClient {
  constructor({ url, getToken, onEvent, onStatus }) {
    this.url = url;
    this.getToken = getToken;
    this.onEvent = onEvent || (() => {});
    this.onStatus = onStatus || (() => {});
    this.ws = null;
    this.retryDelay = 1000;
    this.shouldReconnect = true;
    this._reconnectTimer = null;
  }

  connect() {
    const token = this.getToken();
    if (!token) {
      this.onStatus("error");
      return;
    }
    this.onStatus("connecting");
    const url = `${this.url}?token=${encodeURIComponent(token)}`;
    try {
      this.ws = new WebSocket(url);
    } catch (e) {
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.retryDelay = 1000;
      this.onStatus("connected");
    };
    this.ws.onmessage = (e) => {
      try {
        this.onEvent(JSON.parse(e.data));
      } catch {
        /* ignore malformed frames */
      }
    };
    this.ws.onerror = () => this.onStatus("error");
    this.ws.onclose = () => {
      this.onStatus("disconnected");
      this._scheduleReconnect();
    };
  }

  _scheduleReconnect() {
    if (!this.shouldReconnect) return;
    clearTimeout(this._reconnectTimer);
    this._reconnectTimer = setTimeout(() => this.connect(), this.retryDelay);
    this.retryDelay = Math.min(this.retryDelay * 2, 30000);
  }

  close() {
    this.shouldReconnect = false;
    clearTimeout(this._reconnectTimer);
    if (this.ws) {
      try { this.ws.close(); } catch {}
    }
  }
}
