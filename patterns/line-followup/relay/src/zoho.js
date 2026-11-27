// Zoho CRM helpers: OAuth refresh-token flow and the few API calls the relay needs.

let cached = { token: null, expiresAt: 0 };

/** Test helper: forget the cached access token. */
export function resetTokenCache() {
  cached = { token: null, expiresAt: 0 };
}

export async function getAccessToken(env) {
  if (cached.token && Date.now() < cached.expiresAt) return cached.token;

  const res = await fetch(`${env.ZOHO_ACCOUNTS_URL}/oauth/v2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: env.ZOHO_CLIENT_ID,
      client_secret: env.ZOHO_CLIENT_SECRET,
      refresh_token: env.ZOHO_REFRESH_TOKEN,
    }).toString(),
  });
  const json = await res.json();
  if (!res.ok || !json.access_token) {
    throw new Error(`Zoho token request failed (status ${res.status})`);
  }
  const ttlSeconds = json.expires_in ?? 3600;
  // Renew 60 seconds before the real expiry.
  cached = { token: json.access_token, expiresAt: Date.now() + (ttlSeconds - 60) * 1000 };
  return cached.token;
}

async function crm(env, method, path, body) {
  const token = await getAccessToken(env);
  const res = await fetch(`${env.ZOHO_API_DOMAIN}/crm/v8${path}`, {
    method,
    headers: {
      Authorization: `Zoho-oauthtoken ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  // Search returns 204 with an empty body when nothing matches.
  const json = res.status === 204 ? null : await res.json();
  return { ok: res.ok, status: res.status, json };
}

/** Insert or update a lead, matching on LINE_User_ID. Returns the lead id. */
export async function upsertLead(env, fields) {
  const { ok, status, json } = await crm(env, "POST", "/Leads/upsert", {
    data: [fields],
    duplicate_check_fields: ["LINE_User_ID"],
  });
  const row = json?.data?.[0];
  if (!ok || !row || row.status !== "success") {
    throw new Error(`Lead upsert failed (status ${status})`);
  }
  return row.details.id;
}

/** Returns the lead id, or null when no lead has this LINE user ID. */
export async function findLeadByLineUserId(env, lineUserId) {
  const criteria = encodeURIComponent(`(LINE_User_ID:equals:${lineUserId})`);
  const { ok, json } = await crm(env, "GET", `/Leads/search?criteria=${criteria}`);
  if (!ok) return null;
  return json?.data?.[0]?.id ?? null;
}

/** Adds a Note to a lead via POST /Notes with Parent_Id. */
export async function addNote(env, leadId, title, content) {
  const { ok, status } = await crm(env, "POST", "/Notes", {
    data: [
      {
        Note_Title: title,
        Note_Content: content,
        Parent_Id: { module: { api_name: "Leads" }, id: leadId },
      },
    ],
  });
  if (!ok) throw new Error(`Note creation failed (status ${status})`);
}

export async function updateLead(env, leadId, fields) {
  const { ok, status } = await crm(env, "PUT", `/Leads/${leadId}`, { data: [fields] });
  if (!ok) throw new Error(`Lead update failed (status ${status})`);
}
