import { Centrifuge } from "centrifuge";

let _client: Centrifuge | null = null;

export async function getCentrifuge(): Promise<Centrifuge> {
  if (_client && _client.state === "connected") return _client;
  if (_client) {
    return _client;
  }
  const tokenResp = await fetch("/api/me/centrifugo-token");
  if (!tokenResp.ok) throw new Error("centrifugo token fetch failed");
  const { token } = (await tokenResp.json()) as { token: string };
  _client = new Centrifuge("ws://" + location.host + "/connection/websocket", {
    token,
    getToken: async () => {
      const r = await fetch("/api/me/centrifugo-token");
      const j = (await r.json()) as { token: string };
      return j.token;
    },
  });
  _client.connect();
  return _client;
}
