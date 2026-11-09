import PostalMime from "postal-mime";

const enc = new TextEncoder();
const hex = bytes => Array.from(new Uint8Array(bytes)).map(x => x.toString(16).padStart(2, "0")).join("");
async function hmac(secret, stamp, body) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), {name:"HMAC", hash:"SHA-256"}, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", key, enc.encode(stamp+"."+body)));
}
export default {
  async email(message, env) {
    if (!env.CONCIERGE_INGEST_URL || !env.CONCIERGE_INBOUND_SECRET || env.CONCIERGE_INBOUND_SECRET.length < 32) {
      throw new Error("Inbound delivery is not configured");
    }
    const raw = await new Response(message.raw).arrayBuffer();
    if (raw.byteLength > 256 * 1024) throw new Error("Email exceeds ingestion limit");
    const parsed = await PostalMime.parse(raw);
    const id = hex(await crypto.subtle.digest("SHA-256", raw));
    const payload = {
      message_id: id,
      recipient: message.to.toLowerCase(),
      sender: message.from,
      subject: String(parsed.subject || "").slice(0,250),
      text: String(parsed.text || "").slice(0,20000)
    };
    if (!payload.text.trim()) throw new Error("No plain-text email body");
    const body = JSON.stringify(payload);
    const stamp = String(Math.floor(Date.now()/1000));
    const signature = await hmac(env.CONCIERGE_INBOUND_SECRET, stamp, body);
    const response = await fetch(env.CONCIERGE_INGEST_URL, {
      method: "POST",
      headers: {"Content-Type":"application/json", "X-Concierge-Timestamp":stamp, "X-Concierge-Signature":signature},
      body
    });
    if (!response.ok) throw new Error("Concierge ingress rejected email: "+response.status);
  }
};
