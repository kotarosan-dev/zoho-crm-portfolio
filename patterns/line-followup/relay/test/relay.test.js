import { afterEach, beforeEach, describe, test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import worker from "../src/worker.js";
import { resetSeenEvents } from "../src/handlers.js";
import { resetTokenCache } from "../src/zoho.js";

const env = {
  LINE_CHANNEL_SECRET: "test-secret",
  LINE_CHANNEL_ACCESS_TOKEN: "test-access-token",
  LINE_LOGIN_CHANNEL_ID: "1234567890",
  ZOHO_CLIENT_ID: "cid",
  ZOHO_CLIENT_SECRET: "csecret",
  ZOHO_REFRESH_TOKEN: "rtoken",
  RELAY_KEY: "test-relay-key",
  ZOHO_ACCOUNTS_URL: "https://accounts.example.test",
  ZOHO_API_DOMAIN: "https://crm.example.test",
  LIFF_URL: "https://liff.line.me/test-liff",
};

const realFetch = globalThis.fetch;
let calls;
let routes;

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function mockFetch() {
  calls = [];
  routes = {
    "oauth/v2/token": () => jsonResponse({ access_token: "zoho-token", expires_in: 3600 }),
    "/Leads/search": () => jsonResponse({ data: [{ id: "L1" }] }),
    "/Leads/upsert": () => jsonResponse({ data: [{ status: "success", details: { id: "L1" } }] }),
    "/Notes": () => jsonResponse({ data: [{ status: "success" }] }),
    "/Leads/L1": () => jsonResponse({ data: [{ status: "success" }] }),
    "bot/message/reply": () => jsonResponse({}),
    "bot/message/push": () => jsonResponse({}),
    "oauth2/v2.1/verify": () => jsonResponse({ sub: "U123", aud: "1234567890" }),
  };
  globalThis.fetch = async (url, init = {}) => {
    const u = String(url);
    calls.push({ url: u, method: init.method, headers: init.headers, body: init.body });
    const key = Object.keys(routes).find((k) => u.includes(k));
    if (!key) throw new Error(`unmocked fetch: ${u}`);
    return routes[key]();
  };
}

function callsTo(part) {
  return calls.filter((c) => c.url.includes(part));
}

function sign(body, secret = env.LINE_CHANNEL_SECRET) {
  return createHmac("sha256", secret).update(body).digest("base64");
}

async function send(request) {
  const pending = [];
  const ctx = { waitUntil: (p) => pending.push(p) };
  const res = await worker.fetch(request, env, ctx);
  await Promise.all(pending);
  return res;
}

function webhook(events, { signature } = {}) {
  const body = JSON.stringify({ destination: "Uxxx", events });
  const headers = { "Content-Type": "application/json" };
  const sig = signature === undefined ? sign(body) : signature;
  if (sig !== null) headers["x-line-signature"] = sig;
  return new Request("https://relay.test/line/webhook", { method: "POST", headers, body });
}

beforeEach(() => {
  mockFetch();
  resetTokenCache();
  resetSeenEvents();
});
afterEach(() => {
  globalThis.fetch = realFetch;
});

describe("webhook signature", () => {
  test("valid signature passes", async () => {
    const res = await send(webhook([]));
    assert.equal(res.status, 200);
  });

  test("tampered body fails", async () => {
    const original = JSON.stringify({ events: [] });
    const req = new Request("https://relay.test/line/webhook", {
      method: "POST",
      headers: { "x-line-signature": sign(original) },
      body: JSON.stringify({ events: [{ type: "follow" }] }),
    });
    assert.equal((await send(req)).status, 401);
  });

  test("missing header returns 401", async () => {
    const res = await send(webhook([], { signature: null }));
    assert.equal(res.status, 401);
  });
});

describe("webhook events", () => {
  test("follow replies with the LIFF URL", async () => {
    await send(webhook([{ type: "follow", replyToken: "rt1", source: { userId: "U123" }, webhookEventId: "e1" }]));
    const reply = callsTo("bot/message/reply");
    assert.equal(reply.length, 1);
    const body = JSON.parse(reply[0].body);
    assert.equal(body.replyToken, "rt1");
    assert.match(body.messages[0].text, /https:\/\/liff\.line\.me\/test-liff/);
  });

  test("unfollow sets LINE_Status to Blocked", async () => {
    await send(webhook([{ type: "unfollow", source: { userId: "U123" }, webhookEventId: "e2" }]));
    const update = callsTo("/Leads/L1");
    assert.equal(update.length, 1);
    assert.equal(update[0].method, "PUT");
    assert.equal(JSON.parse(update[0].body).data[0].LINE_Status, "Blocked");
  });

  test("message searches, then adds a note and updates Last_LINE_Inbound", async () => {
    await send(
      webhook([{ type: "message", message: { type: "text", text: "hello" }, source: { userId: "U123" }, webhookEventId: "e3" }]),
    );
    const search = callsTo("/Leads/search");
    assert.equal(search.length, 1);
    assert.match(decodeURIComponent(search[0].url), /\(LINE_User_ID:equals:U123\)/);

    const note = callsTo("/Notes");
    assert.equal(note.length, 1);
    const noteData = JSON.parse(note[0].body).data[0];
    assert.equal(noteData.Note_Content, "hello");
    assert.deepEqual(noteData.Parent_Id, { module: { api_name: "Leads" }, id: "L1" });

    const update = JSON.parse(callsTo("/Leads/L1")[0].body).data[0];
    assert.match(update.Last_LINE_Inbound, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00$/);
  });

  test("message with no matching lead creates no note", async () => {
    routes["/Leads/search"] = () => new Response(null, { status: 204 });
    await send(
      webhook([{ type: "message", message: { type: "text", text: "hi" }, source: { userId: "U999" }, webhookEventId: "e4" }]),
    );
    assert.equal(callsTo("/Notes").length, 0);
    assert.equal(callsTo("/Leads/L1").length, 0);
  });

  test("redelivered event already seen is skipped", async () => {
    const event = { type: "follow", replyToken: "rt", source: { userId: "U123" }, webhookEventId: "dup" };
    await send(webhook([event]));
    await send(webhook([{ ...event, deliveryContext: { isRedelivery: true } }]));
    assert.equal(callsTo("bot/message/reply").length, 1);
  });
});

describe("POST /liff/register", () => {
  function register(idToken) {
    return new Request("https://relay.test/liff/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idToken, lastName: "Sample", phone: "000-0000-0000", inquiry: "Question" }),
    });
  }

  test("bad token returns 401", async () => {
    routes["oauth2/v2.1/verify"] = () => jsonResponse({ error: "invalid_request" }, 400);
    const res = await send(register("bad"));
    assert.equal(res.status, 401);
    assert.equal(callsTo("/Leads/upsert").length, 0);
  });

  test("good token upserts with LINE_User_ID = sub", async () => {
    const res = await send(register("good"));
    assert.equal(res.status, 200);

    const verify = callsTo("oauth2/v2.1/verify")[0];
    const form = new URLSearchParams(verify.body);
    assert.equal(form.get("id_token"), "good");
    assert.equal(form.get("client_id"), "1234567890");

    const upsert = callsTo("/Leads/upsert")[0];
    const body = JSON.parse(upsert.body);
    assert.deepEqual(body.duplicate_check_fields, ["LINE_User_ID"]);
    assert.equal(body.data[0].LINE_User_ID, "U123");
    assert.equal(body.data[0].Lead_Source, "LINE");
    assert.equal(body.data[0].LINE_Status, "Friend");
    assert.equal(upsert.headers.Authorization, "Zoho-oauthtoken zoho-token");
  });
});

describe("POST /crm/push", () => {
  function push(key) {
    const headers = { "Content-Type": "application/json" };
    if (key) headers["X-Relay-Key"] = key;
    return new Request("https://relay.test/crm/push", {
      method: "POST",
      headers,
      body: JSON.stringify({ lineUserId: "U123", text: "follow-up" }),
    });
  }

  test("wrong key returns 401", async () => {
    const res = await send(push("wrong"));
    assert.equal(res.status, 401);
    assert.equal(callsTo("bot/message/push").length, 0);
  });

  test("right key pushes with the Bearer token", async () => {
    const res = await send(push(env.RELAY_KEY));
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { ok: true, status: 200 });
    const call = callsTo("bot/message/push")[0];
    assert.equal(call.headers.Authorization, "Bearer test-access-token");
    assert.deepEqual(JSON.parse(call.body), {
      to: "U123",
      messages: [{ type: "text", text: "follow-up" }],
    });
  });
});

describe("Zoho token cache", () => {
  test("two CRM calls use one token request", async () => {
    const ev = (id) => ({ type: "unfollow", source: { userId: "U123" }, webhookEventId: id });
    await send(webhook([ev("c1")]));
    await send(webhook([ev("c2")]));
    assert.equal(callsTo("oauth/v2/token").length, 1);
    assert.ok(callsTo("/Leads/search").length >= 2);
  });
});

describe("routing", () => {
  test("unknown route returns 404", async () => {
    const res = await send(new Request("https://relay.test/nope", { method: "GET" }));
    assert.equal(res.status, 404);
  });

  test("health returns 200", async () => {
    const res = await send(new Request("https://relay.test/health"));
    assert.equal(res.status, 200);
  });
});
