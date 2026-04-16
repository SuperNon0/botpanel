// Helpers fetch API REST BotPanel
const API = {
  async get(path) {
    const r = await fetch(`/api${path}`);
    if (!r.ok) throw new Error(await r.text());
    return r.status === 204 ? null : r.json();
  },
  async post(path, body) {
    const r = await fetch(`/api${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : null,
    });
    if (!r.ok) throw new Error((await safeJson(r))?.detail || r.statusText);
    return r.status === 204 ? null : r.json();
  },
  async put(path, body) {
    const r = await fetch(`/api${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await safeJson(r))?.detail || r.statusText);
    return r.json();
  },
  async del(path) {
    const r = await fetch(`/api${path}`, { method: "DELETE" });
    if (!r.ok) throw new Error((await safeJson(r))?.detail || r.statusText);
    return true;
  },
};

async function safeJson(r) {
  try { return await r.json(); } catch { return null; }
}
