// LINE Messaging API / LINE Login helpers.

const encoder = new TextEncoder();

/** Constant-time string comparison (also used for the relay key). */
export function timingSafeEqual(a, b) {
  const x = encoder.encode(String(a));
  const y = encoder.encode(String(b));
  let diff = x.length ^ y.length;
  const len = Math.max(x.length, y.length);
  for (let i = 0; i < len; i++) {
    diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  }
  return diff === 0;
}

/** x-line-signature = base64(HMAC-SHA256(channelSecret, rawBody)). */
export async function verifySignature(channelSecret, rawBody, signature) {
  if (!signature || !channelSecret) return false;
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(channelSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", key, encoder.encode(rawBody));
  const expected = btoa(String.fromCharCode(...new Uint8Array(mac)));
  return timingSafeEqual(expected, signature);
}

async function postJson(url, token, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  return { ok: res.ok, status: res.status };
}

/** Reply API (free). The reply token is valid only for a short time. */
export function replyText(env, replyToken, text) {
  return postJson("https://api.line.me/v2/bot/message/reply", env.LINE_CHANNEL_ACCESS_TOKEN, {
    replyToken,
    messages: [{ type: "text", text }],
  });
}

/** Push API (counts toward the monthly message quota). */
export function pushText(env, to, text) {
  return postJson("https://api.line.me/v2/bot/message/push", env.LINE_CHANNEL_ACCESS_TOKEN, {
    to,
    messages: [{ type: "text", text }],
  });
}

/** Verifies a LIFF ID token. Returns the payload (`sub` = LINE user ID) or null. */
export async function verifyIdToken(env, idToken) {
  if (!idToken) return null;
  const res = await fetch("https://api.line.me/oauth2/v2.1/verify", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      id_token: idToken,
      client_id: env.LINE_LOGIN_CHANNEL_ID,
    }).toString(),
  });
  if (!res.ok) return null;
  const payload = await res.json();
  return payload.sub ? payload : null;
}
