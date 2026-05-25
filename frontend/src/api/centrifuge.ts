import { Centrifuge } from "centrifuge";

let _client: Centrifuge | null = null;

async function fetchToken(): Promise<string> {
  const r = await fetch("/api/me/centrifugo-token");
  if (!r.ok) throw new Error("centrifugo token fetch failed");
  const j = (await r.json()) as { token: string };
  return j.token;
}

export async function getCentrifuge(): Promise<Centrifuge> {
  if (_client) return _client;
  const proto = location.protocol === "https:" ? "wss://" : "ws://";
  _client = new Centrifuge(`${proto}${location.host}/connection/websocket`, {
    getToken: fetchToken,
  });
  _client.connect();
  return _client;
}
