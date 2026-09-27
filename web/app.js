// keepctx.com routes /v1/* to the API, so the app calls its own origin
const API = "";
const KEY = "ctx.session";

const $ = (id) => document.getElementById(id);
let mode = "login";
let session = null;   // { token, email, orgs: [{org, role}], current }

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
const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body) });

function say(text, good, where = "msg") {
  const m = $(where);
  m.textContent = text;
  m.className = "msg " + (good ? "good" : "bad");
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function setMode(next) {
  mode = next;
  const isReg = mode === "register";
  $("auth-title").textContent = isReg ? "Create your account" : "Sign in";
  $("auth-sub").textContent = isReg
    ? "Free for individuals and small teams. Start an org or get added to one after."
    : "Manage your org's contexts.";
  $("submit").textContent = isReg ? "Create account" : "Sign in";
  $("switch").innerHTML = isReg
    ? 'Already have an account? <button class="link-btn" id="toggle">Sign in</button>'
    : 'No account? <button class="link-btn" id="toggle">Create one</button>';
  $("toggle").onclick = () => setMode(isReg ? "login" : "register");
  $("msg").className = "msg";
}

async function submit() {
  const email = $("email").value.trim();
  const password = $("password").value;
  if (!email || !password) return say("email and password, please");

  $("submit").disabled = true;
  try {
    const out = await post(`/v1/auth/${mode}`, { email, password });
    saveSession({ token: out.token, email: out.email, orgs: out.orgs || [] });
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

const current = () => session.orgs.find((o) => o.org === session.current);

// Orgs come from the server every time: an admin may have added you since you
// signed in, and that should show up without signing out and back in.
async function refreshOrgs() {
  const me = await api("/v1/me");
  const orgs = me.orgs || [];
  const keep = orgs.some((o) => o.org === session.current) ? session.current : null;
  saveSession({ ...session, email: me.email, orgs, current: keep || (orgs[0] && orgs[0].org) });
}

function setTab(which) {
  const create = which === "create";
  $("tab-create").setAttribute("aria-selected", String(create));
  $("tab-join").setAttribute("aria-selected", String(!create));
  $("pane-create").hidden = !create;
  $("pane-join").hidden = create;
  $("no-org-msg").className = "msg";
}

// The create-or-join screen: the only screen until you're in an org, and
// reachable afterwards from "+ create or join an org".
function showOrgChooser() {
  const inOne = session.orgs.length > 0;
  $("app").hidden = true;
  $("no-org").hidden = false;
  $("orgs-title").textContent = inOne ? "Create or join another org" : "Create or join an org";
  $("orgs-back").hidden = !inOne;
  $("no-org-email").textContent = session.email;
  $("no-org-email-2").textContent = session.email;
}

async function recheck() {
  const before = session.orgs.map((o) => o.org);
  await refreshOrgs();
  const added = session.orgs.find((o) => !before.includes(o.org));
  if (added) {
    session.current = added.org;
    saveSession(session);
    return showApp();
  }
  say("Not yet — nobody has added you to a new org so far.", false, "no-org-msg");
}

async function showApp() {
  await refreshOrgs();
  $("auth").hidden = true;
  signedIn(true);

  if (!session.orgs.length) return showOrgChooser();
  $("no-org").hidden = true;
  $("app").hidden = false;
  $("detail").hidden = true;
  $("list").hidden = false;
  $("people").hidden = false;
  $("who").textContent = session.email;
  $("org-name").textContent = session.current;

  const pick = $("org-pick");
  pick.hidden = session.orgs.length < 2;
  $("org-name").hidden = !pick.hidden;
  pick.innerHTML = "";
  session.orgs.forEach((o) => {
    const opt = el("option", "", o.org);
    opt.value = o.org;
    opt.selected = o.org === session.current;
    pick.appendChild(opt);
  });

  await Promise.all([showContexts(), showMembers()]);
}

async function showContexts() {
  const org = session.current;
  const out = await api(`/v1/orgs/${org}/contexts`);
  const list = $("list");
  $("count").textContent =
    out.contexts.length === 1 ? "1 context" : `${out.contexts.length} contexts`;

  list.innerHTML = "";
  if (!out.contexts.length) {
    const empty = el("div", "empty");
    empty.appendChild(el("p", "", "No contexts yet."));
    const how = el("p");
    how.innerHTML = "Run <code>ctx init</code> then <code>ctx remote</code> in a project to create one.";
    empty.appendChild(how);
    list.appendChild(empty);
    return;
  }
  out.contexts.forEach((c) => {
    const row = el("div", "ctx-row");
    row.appendChild(el("span", "nm", `${org}:${c.name}`));
    const open = el("button", "link-btn", "open");
    open.onclick = () => openContext(c.name);
    row.appendChild(open);
    const facts = c.facts === 1 ? "1 fact" : `${c.facts} facts`;
    row.appendChild(el("span", "meta", `${facts} · v${c.version} · ${ago(c.updated)}`));
    list.appendChild(row);
  });
}

async function showMembers() {
  const org = session.current;
  const isAdmin = current() && current().role === "admin";
  const out = await api(`/v1/orgs/${org}/members`);
  const box = $("members");
  box.innerHTML = "";
  out.members.forEach((m) => {
    const row = el("div", "mrow");
    row.appendChild(el("span", "em", m.email));
    row.appendChild(el("span", "tag", m.owner ? "owner" : m.role));
    const right = el("span", "right");
    if (!m.account) right.appendChild(el("span", "", "no account yet"));
    if (isAdmin && !m.owner) {
      const rm = el("button", "link-btn", "remove");
      rm.onclick = async () => {
        if (!confirm(`Remove ${m.email} from ${org}? They lose access right away.`)) return;
        try {
          await post(`/v1/orgs/${org}/members/remove`, { email: m.email });
          if (m.email === session.email) return showApp();
          showMembers();
        } catch (e) { say(e.message, false, "member-msg"); }
      };
      right.appendChild(rm);
    }
    row.appendChild(right);
    box.appendChild(row);
  });
  $("add-member").hidden = !isAdmin;
  $("add-hint").hidden = !isAdmin;
  $("people-sub").textContent = isAdmin
    ? "Everyone here reads and writes every context in this org. As an admin, you choose who's in it."
    : "Everyone here reads and writes every context in this org. An admin adds and removes people.";
}

async function addMember() {
  const email = $("member-email").value.trim();
  if (!email) return say("an email, please", false, "member-msg");
  $("add").disabled = true;
  try {
    await post(`/v1/orgs/${session.current}/members`, { email, role: $("member-role").value });
    $("member-email").value = "";
    $("member-msg").className = "msg";
    await showMembers();
  } catch (e) {
    say(e.message, false, "member-msg");
  } finally {
    $("add").disabled = false;
  }
}

async function createOrg() {
  const org = $("first-org").value.trim().toLowerCase();
  if (!org) return say("pick an org name", false, "no-org-msg");
  $("make-first-org").disabled = true;
  try {
    await post("/v1/orgs", { org });
    $("first-org").value = "";
    session.current = org;
    await showApp();
  } catch (e) {
    say(e.message, false, "no-org-msg");
  } finally {
    $("make-first-org").disabled = false;
  }
}

async function openContext(name) {
  const org = session.current;
  $("list").hidden = true;
  $("people").hidden = true;
  $("detail").hidden = false;
  $("d-name").textContent = `${org}:${name}`;

  const c = await api(`/v1/contexts/${org}/${name}`);
  $("d-version").textContent = `v${c.version} · ${c.count} facts`;
  $("d-facts").textContent = c.facts || "(empty)";

  const v = await api(`/v1/contexts/${org}/${name}/versions`);
  const box = $("d-versions");
  box.innerHTML = "";
  v.versions.forEach((ver, i) => {
    const row = el("div", "vrow");
    row.appendChild(el("span", "v", `v${ver.version}`));
    row.appendChild(el("span", "", `${ver.facts} facts`));
    row.appendChild(el("span", "by", `${ver.by} · ${ago(ver.at)}`));
    if (i > 0) {
      const b = el("button", "link-btn", "revert to this");
      b.onclick = async () => {
        if (!confirm(`Revert ${name} to v${ver.version}? This creates a new version — nothing is lost.`)) return;
        await post(`/v1/contexts/${org}/${name}/revert`, { version: ver.version });
        openContext(name);
      };
      row.appendChild(b);
    }
    box.appendChild(row);
  });
}

// Same menu as the rest of the site. Its last button is "Sign in" or "Console"
// outside; in here, signed in, it's "Sign out".
function signedIn(yes) {
  $("account").textContent = yes ? "Sign out" : "Sign in";
}

function showAuth() {
  $("auth").hidden = false;
  $("app").hidden = true;
  $("no-org").hidden = true;
  signedIn(false);
  setMode(location.hash === "#register" ? "register" : "login");
}

document.addEventListener("DOMContentLoaded", async () => {
  $("submit").onclick = submit;
  $("password").addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
  $("back").onclick = () => {
    $("detail").hidden = true; $("list").hidden = false; $("people").hidden = false;
  };
  $("account").onclick = (e) => {
    if (!session) return;            // signed out: just a link to this page
    e.preventDefault();
    clearSession();
    showAuth();
  };
  $("org-pick").onchange = (e) => { session.current = e.target.value; saveSession(session); showApp(); };
  $("new-org").onclick = () => { setTab("create"); showOrgChooser(); };
  $("back-to-app").onclick = () => showApp();
  $("tab-create").onclick = () => setTab("create");
  $("tab-join").onclick = () => setTab("join");
  $("make-first-org").onclick = createOrg;
  $("first-org").addEventListener("keydown", (e) => { if (e.key === "Enter") createOrg(); });
  $("recheck").onclick = recheck;
  $("add").onclick = addMember;
  $("member-email").addEventListener("keydown", (e) => { if (e.key === "Enter") addMember(); });

  session = loadSession();
  if (session && session.token) {
    try { await showApp(); return; } catch (e) { clearSession(); }
  }
  showAuth();
});
