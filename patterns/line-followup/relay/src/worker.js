import { handleEvent, pushFromCrm, registerLead } from "./handlers.js";
import { timingSafeEqual, verifyIdToken, verifySignature } from "./line.js";

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    return null;
  }
}

async function lineWebhook(request, env, ctx) {
  const raw = await request.text();
  const ok = await verifySignature(env.LINE_CHANNEL_SECRET, raw, request.headers.get("x-line-signature"));
  if (!ok) return json({ ok: false }, 401);

  let events = [];
  try {
    events = JSON.parse(raw).events ?? [];
  } catch {
    return json({ ok: false }, 400);
  }

  // Answer LINE right away; do the real work after the response.
  ctx.waitUntil(
    Promise.all(
      events.map((event) =>
        handleEvent(event, env).catch((err) => console.log(`event error (${event.type}): ${err.message}`)),
      ),
    ),
  );
  return json({ ok: true });
}

async function liffRegister(request, env) {
  const body = await readJson(request);
  if (!body) return json({ ok: false }, 400);
  try {
    const result = await registerLead(body, env, verifyIdToken);
    return json(result.body, result.status);
  } catch (err) {
    console.log(`register error: ${err.message}`);
    return json({ ok: false }, 502);
  }
}

async function crmPush(request, env) {
  const key = request.headers.get("x-relay-key") ?? "";
  if (!env.RELAY_KEY || !timingSafeEqual(key, env.RELAY_KEY)) return json({ ok: false }, 401);
  const body = await readJson(request);
  const result = await pushFromCrm(body, env);
  return json(result.body, result.status);
}

export default {
  async fetch(request, env, ctx) {
    const { pathname } = new URL(request.url);
    const route = `${request.method} ${pathname}`;

    if (route === "GET /health") return json({ ok: true });
    if (route === "POST /line/webhook") return lineWebhook(request, env, ctx);
    if (route === "POST /liff/register") return liffRegister(request, env);
    if (route === "POST /crm/push") return crmPush(request, env);
    return json({ ok: false, error: "not found" }, 404);
  },
};
