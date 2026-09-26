const API = "https://lrtkepaox4.execute-api.us-east-1.amazonaws.com";
const KEY = "ctx.session";

const $ = (id) => document.getElementById(id);
let mode = "login";
let session = null;

function saveSession(s) {
  session = s;
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* private mode */ }
}
function loadSession() {
  try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; }
}
function clearSession() {
  session = null;
  try { localStorage.removeItem(KEY); } catch (e) { /* ignore */ }
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  if (session && session.token) headers.Authorization = "Bearer " + session.token;
  const res = await fetch(API + path, { ...opts, headers });
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) throw new Error(data.error || `request failed (${res.status})`);
  return data;
}

function say(text, good) {
  const m = $("msg");
  m.textContent = text;
  m.className = "msg " + (good ? "good" : "bad");
}

function setMode(next) {
  mode = next;
  const isReg = mode === "register";
  $("auth-title").textContent = isReg ? "Create your org" : "Sign in";
  $("auth-sub").textContent = isReg
    ? "Free for individuals and small teams."
    : "Manage your org's contexts.";
  $("submit").textContent = isReg ? "Create org" : "Sign in";
  $("org-field").hidden = !isReg;
  $("switch").innerHTML = isReg
    ? 'Already have an account? <button class="link-btn" id="toggle">Sign in</button>'
    : 'No account? <button class="link-btn" id="toggle">Create one</button>';
  $("toggle").onclick = () => setMode(isReg ? "login" : "register");
  $("msg").className = "msg";
}

async function submit() {
  const email = $("email").value.trim();
  const password = $("password").value;
  const org = $("org").value.trim().toLowerCase();
  if (!email || !password) return say("email and password, please");
  if (mode === "register" && !org) return say("pick an org name");

  $("submit").disabled = true;
  try {
    const body = mode === "register" ? { email, password, org } : { email, password };
    const out = await api(`/v1/auth/${mode}`, { method: "POST", body: JSON.stringify(body) });
    saveSession(out);
    await showApp();
  } catch (e) {
    say(e.message);
  } finally {
    $("submit").disabled = false;
  }
}

function ago(ts) {
  if (!ts) return "—";
  const s = Math.floor(Date.now() / 1000) - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

async function showApp() {
  $("auth").hidden = true;
  $("app").hidden = false;
  $("signout").hidden = false;
  $("org-name").textContent = session.org;
  $("who").textContent = session.email;

  const out = await api(`/v1/orgs/${session.org}/contexts`);
  const list = $("list");
  $("count").textContent =
    out.contexts.length === 1 ? "1 context" : `${out.contexts.length} contexts`;

  if (!out.contexts.length) {
    list.innerHTML = `<div class="empty">
      <p>No contexts yet.</p>
      <p>Run <code>ctx init</code> then <code>ctx remote</code> in a project to create one.</p>
    </div>`;
    return;
  }

  list.innerHTML = "";
  out.contexts.forEach((c) => {
    const row = document.createElement("div");
    row.className = "ctx-row";
    const facts = c.facts === 1 ? "1 fact" : `${c.facts} facts`;
    row.innerHTML = `<span class="nm">${session.org}:${c.name}</span>
      <button class="link-btn">open</button>
      <span class="meta">${facts} · v${c.version} · ${ago(c.updated)}</span>`;
    row.querySelector("button").onclick = () => openContext(c.name);
    list.appendChild(row);
  });
}

async function openContext(name) {
  $("list").hidden = true;
  $("detail").hidden = false;
  $("d-name").textContent = `${session.org}:${name}`;

  const c = await api(`/v1/contexts/${session.org}/${name}`);
  $("d-version").textContent = `v${c.version} · ${c.count} facts`;
  $("d-facts").textContent = c.facts || "(empty)";

  const v = await api(`/v1/contexts/${session.org}/${name}/versions`);
  const box = $("d-versions");
  box.innerHTML = "";
  v.versions.forEach((ver, i) => {
    const row = document.createElement("div");
    row.className = "vrow";
    row.innerHTML = `<span class="v">v${ver.version}</span>
      <span>${ver.facts} facts</span>
      <span class="by">${ver.by} · ${ago(ver.at)}</span>`;
    if (i > 0) {
      const b = document.createElement("button");
      b.className = "link-btn";
      b.textContent = "revert to this";
      b.onclick = async () => {
        if (!confirm(`Revert ${name} to v${ver.version}? This creates a new version — nothing is lost.`)) return;
        await api(`/v1/contexts/${session.org}/${name}/revert`,
          { method: "POST", body: JSON.stringify({ version: ver.version }) });
        openContext(name);
      };
      row.appendChild(b);
    }
    box.appendChild(row);
  });
}

function showAuth() {
  $("auth").hidden = false;
  $("app").hidden = true;
  $("signout").hidden = true;
  setMode("login");
}

document.addEventListener("DOMContentLoaded", async () => {
  $("submit").onclick = submit;
  $("password").addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
  $("back").onclick = () => { $("detail").hidden = true; $("list").hidden = false; };
  $("signout").onclick = (e) => { e.preventDefault(); clearSession(); showAuth(); };

  session = loadSession();
  if (session && session.token) {
    try { await showApp(); return; } catch (e) { clearSession(); }
  }
  showAuth();
});
