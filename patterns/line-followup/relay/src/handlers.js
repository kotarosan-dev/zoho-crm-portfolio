// Event handling: what the relay does for each kind of request.

import { pushText, replyText } from "./line.js";
import { addNote, findLeadByLineUserId, updateLead, upsertLead } from "./zoho.js";

// In-memory dedupe only lives as long as this isolate.
// Production should keep webhookEventId in KV or D1 instead.
const seenEventIds = new Set();

export function resetSeenEvents() {
  seenEventIds.clear();
}

/** ISO datetime with a +09:00 offset, as Zoho CRM expects. */
export function nowWithOffset(date = new Date()) {
  const jst = new Date(date.getTime() + 9 * 60 * 60 * 1000);
  return jst.toISOString().replace(/\.\d{3}Z$/, "+09:00");
}

export async function handleEvent(event, env) {
  const id = event.webhookEventId;
  if (event.deliveryContext?.isRedelivery && id && seenEventIds.has(id)) {
    console.log(`skip redelivery: ${event.type}`);
    return;
  }
  if (id) seenEventIds.add(id);

  const userId = event.source?.userId;

  if (event.type === "follow") {
    await replyText(
      env,
      event.replyToken,
      `友だち追加ありがとうございます。\nこちらからお問い合わせ情報をご登録ください。\n${env.LIFF_URL}`,
    );
    console.log("event: follow");
    return;
  }

  if (event.type === "message" && event.message?.type === "text") {
    const leadId = await findLeadByLineUserId(env, userId);
    if (!leadId) {
      console.log("event: message, no matching lead");
      return;
    }
    await addNote(env, leadId, "LINE message received", event.message.text);
    await updateLead(env, leadId, { Last_LINE_Inbound: nowWithOffset() });
    console.log(`event: message, lead ${leadId}`);
    return;
  }

  if (event.type === "unfollow") {
    const leadId = await findLeadByLineUserId(env, userId);
    if (!leadId) {
      console.log("event: unfollow, no matching lead");
      return;
    }
    await updateLead(env, leadId, { LINE_Status: "Blocked" });
    console.log(`event: unfollow, lead ${leadId}`);
  }
}

/** Body: { idToken, lastName, phone, inquiry } */
export async function registerLead(body, env, verifyIdToken) {
  const payload = await verifyIdToken(env, body?.idToken);
  if (!payload) return { status: 401, body: { ok: false, error: "invalid id token" } };

  const leadId = await upsertLead(env, {
    Last_Name: body.lastName,
    Phone: body.phone,
    Description: body.inquiry,
    Lead_Source: "LINE",
    LINE_User_ID: payload.sub,
    LINE_Status: "Friend",
  });
  console.log(`liff register: lead ${leadId}`);
  return { status: 200, body: { ok: true } };
}

/** Body: { lineUserId, text } */
export async function pushFromCrm(body, env) {
  if (!body?.lineUserId || !body?.text) {
    return { status: 400, body: { ok: false, status: 400 } };
  }
  const result = await pushText(env, body.lineUserId, body.text);
  console.log(`crm push: line status ${result.status}`);
  return {
    status: result.ok ? 200 : 502,
    body: { ok: result.ok, status: result.status },
  };
}
