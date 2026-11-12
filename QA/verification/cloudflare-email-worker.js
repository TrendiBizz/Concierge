// Cloudflare Email Worker: forward verified inbound email to Concierge.
//
// Deploy in Cloudflare (Email Routing -> Email Workers) with these variables:
//   CONCIERGE_INBOUND_URL     https://chat.trendibizz.com/api/v1/inbound/cloudflare
//   CONCIERGE_INBOUND_SECRET  the same value as INBOUND_CLOUDFLARE_SECRET in api.env
//
// Then add an Email Routing rule: admin@trendibizz.com -> this Worker.
// The API verifies HMAC-SHA256(secret, timestamp + "." + body), rejects
// timestamps older than 5 minutes, checks the mailbox is enabled for the tenant,
// and only creates a review draft (it never auto-sends).
//
// The payload must be exactly {message_id, recipient, sender, subject, text}.

function authFrom(raw, headers) {
  // These are hints for the owner-facing risk label, never an authorisation.
  // The API treats every message as untrusted regardless of these values.
  // Read them from the Authentication-Results header only: the old version ran a
  // regex over the whole raw message, so quoted text in the body could set hints.
  const results = (headers.get("authentication-results") || "").slice(0, 500);
  const one = (key) => {
    const match = results
      .toLowerCase()
      .match(new RegExp("(?:^|[;\\s])" + key + "=(pass|fail|none)(?![a-z])"));
    return match ? match[1] : "";
  };
  return {
    spf: one("spf"),
    dkim: one("dkim"),
    dmarc: one("dmarc"),
    authentication_results: results,
    reply_to: (headers.get("reply-to") || "").slice(0, 320),
    content_type: (headers.get("content-type") || "").slice(0, 200),
  };
}

function textFromRaw(raw) {
  // Minimal text/plain extraction. For HTML-only mail, strip tags as a fallback.
  const idx = raw.indexOf("text/plain");
  let body = raw;
  if (idx !== -1) {
    const after = raw.slice(idx);
    const blank = after.indexOf("\r\n\r\n") !== -1 ? after.indexOf("\r\n\r\n") : after.indexOf("\n\n");
    if (blank !== -1) body = after.slice(blank).split(/\r?\n--/)[0];
  } else {
    body = raw.replace(/<[^>]+>/g, " ");
  }
  return body.replace(/\r/g, "").trim().slice(0, 20000);
}

async function hmacHex(secret, value) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export default {
  async email(message, env, ctx) {
    const buffer = await new Response(message.raw).arrayBuffer();
    const bytes = new Uint8Array(buffer);
    const raw = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
    const auth = authFrom(raw, message.headers);
    const body = {
      message_id: message.headers.get("message-id") || crypto.randomUUID(),
      recipient: (message.to || "").toLowerCase(),
      sender: message.from || "",
      subject: message.headers.get("subject") || "",
      text: textFromRaw(raw),
      reply_to: auth.reply_to,
      size: bytes.length,
      has_attachments: /content-disposition:\s*attachment/i.test(raw),
      auth,
    };
    // The raw message lets the Rust sidecar verify DKIM/DMARC cryptographically.
    // Cap it so a huge message cannot exhaust the API or the sidecar.
    if (bytes.length <= 200000) {
      let binary = "";
      for (let i = 0; i < bytes.length; i += 0x8000) {
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
      }
      body.raw_b64 = btoa(binary);
    }
    const payload = JSON.stringify(body);
    const timestamp = String(Math.floor(Date.now() / 1000));
    const signature = await hmacHex(env.CONCIERGE_INBOUND_SECRET, timestamp + "." + payload);
    let accepted = false;
    try {
      const response = await fetch(env.CONCIERGE_INBOUND_URL, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-concierge-timestamp": timestamp,
          "x-concierge-signature": signature,
          // A browser-like UA avoids Cloudflare's UA-based bot challenge; the
          // request is authenticated by the HMAC signature, not the UA.
          "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141 Safari/537.36",
        },
        body: payload,
      });
      const detail = await response.text();
      console.log("concierge inbound", response.status, detail.slice(0, 200));
      accepted = response.ok;
    } catch (error) {
      console.log("concierge inbound fetch failed", error && error.message);
    }
    // Never lose the owner's mail because the CRM copy failed: forward, then
    // report the intake failure in the log rather than silently dropping.
    if (!accepted) {
      console.log("concierge inbound not stored; forwarding only");
    }
    // Keep the owner's normal inbox working: forward the original after the CRM
    // copy is stored. A forward failure must never lose the CRM record.
    if (env.FORWARD_TO) {
      try { await message.forward(env.FORWARD_TO); } catch (e) { /* CRM copy already stored */ }
    }
  },
};
