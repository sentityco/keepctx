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
    const who = c.can_write ? "" : ` · read-only, by ${c.owner}`;
    row.appendChild(el("span", "meta", `${facts} · v${c.version} · ${ago(c.updated)}${who}`));
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
    ? "Everyone here can read every context in this org. Each context is written by whoever created it and by admins. As an admin, you choose who's in the org."
    : "Everyone here can read every context in this org. Each context is written by whoever created it and by admins, who also add and remove people.";
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

// ------------------------------------------------------------- human view
// A section per category, drawn in the browser from the facts. A person who can
// write the context can add, change and remove facts here; each change is
// stamped now on the server, so the next pull brings it into every copy.

// the same categories, in the same order, as the CLI
const CATEGORIES = [
  ["overview", "Overview", "What this is, why it exists, who it's for, and what success looks like."],
  ["requirements", "Requirements", "What it must and must not do, and what is in and out of scope."],
  ["architecture", "Architecture", "Services, components, dependencies and data flows: what connects to what."],
  ["environments", "Environments", "Hosts, deployment environments, service names, versions and access. Never secrets."],
  ["decisions", "Decisions", "What was chosen and why, and what was considered and rejected."],
  ["questions", "Questions", "What is still undecided."],
  ["conventions", "Conventions", "Patterns future developers and agents should follow, and what not to touch."],
  ["operations", "Operations", "Build, deploy, runbooks, troubleshooting and recurring operational details."],
  ["testing", "Testing", "How to test, what passing means, and what is not covered."],
  ["knowledge", "Knowledge", "Gotchas, domain facts and vocabulary nobody outside would know."],
  ["people", "People", "Who owns what, who to ask, and how they like to work."],
];

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// The small part of markdown a fact uses. Escaped first, so nothing in a
// context can put markup on the page.
function inline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" rel="noopener">$1</a>');
}

let viewing = null;   // { org, name, canWrite }

async function editFact(body) {
  try {
    await post(`/v1/contexts/${viewing.org}/${viewing.name}/facts`, body);
    openContext(viewing.name);
  } catch (e) { alert(e.message); }
}

function factRow(full, f) {
  const li = el("li");
  const key = full.slice(full.indexOf(".") + 1);
  const text = el("span");
  text.innerHTML = `<span class="fk">${esc(key)}</span><span class="fr">—</span> ${inline(f.value)}`;
  li.appendChild(text);
  if (viewing.canWrite) {
    const tools = el("span", "ftools");
    const edit = el("button", "link-btn", "edit");
    edit.onclick = () => {
      const input = el("input", "finput");
      input.value = f.value;
      const save = el("button", "link-btn", "save");
      const go = () => input.value.trim() && input.value.trim() !== f.value
        ? editFact({ key: full, value: input.value.trim() }) : openContext(viewing.name);
      save.onclick = go;
      input.onkeydown = (e) => { if (e.key === "Enter") go(); if (e.key === "Escape") openContext(viewing.name); };
      li.replaceChildren(el("span", "fk", key), input, save);
      input.focus();
    };
    const rm = el("button", "link-btn", "remove");
    rm.onclick = () => confirm(`Remove ${full}? It's removed from every copy on their next pull.`)
      && editFact({ key: full, removed: true });
    tools.append(edit, rm);
    li.appendChild(tools);
  }
  return li;
}

function renderView(facts) {
  const box = $("d-view");
  box.innerHTML = "";
  const live = Object.entries(facts).filter(([, f]) => !f.removed).sort(([a], [b]) => a.localeCompare(b));
  if (!live.length) {
    const e = el("div", "empty");
    e.appendChild(el("p", "", "Nothing remembered yet."));
    e.appendChild(el("p", "", "As agents work in this project, what they learn and decide shows up here."));
    box.appendChild(e);
  }
  const catOf = (full) => full.slice(0, full.indexOf("."));
  const known = CATEGORIES.map((c) => c[0]);
  const extra = [...new Set(live.map(([k]) => catOf(k)))].filter((c) => !known.includes(c)).sort();
  CATEGORIES.concat(extra.map((c) => [c, c, ""])).forEach(([cat, title, desc]) => {
    const list = live.filter(([k]) => catOf(k) === cat);
    if (!list.length) return;
    const s = el("div", "vsec" + (cat === "questions" ? " open" : ""));
    s.appendChild(el("h3", "", title));
    if (desc) s.appendChild(el("p", "hint", desc));
    const ul = el("ul", "flist");
    list.forEach(([k, f]) => ul.appendChild(factRow(k, f)));
    s.appendChild(ul);
    box.appendChild(s);
  });
  if (viewing.canWrite) box.appendChild(addForm());
}

function addForm() {
  const form = el("div", "inline-form addfact");
  const cat = el("select");
  cat.setAttribute("aria-label", "Category");
  CATEGORIES.forEach(([c, t]) => { const o = el("option", "", t); o.value = c; cat.appendChild(o); });
  const key = el("input");
  key.placeholder = "key, e.g. server-a.ip";
  const value = el("input");
  value.placeholder = "value";
  const add = el("button", "btn", "Add fact");
  const go = () => {
    const k = key.value.trim().toLowerCase().replace(/\s+/g, "-");
    if (k && value.value.trim()) editFact({ key: `${cat.value}.${k}`, value: value.value.trim() });
  };
  add.onclick = go;
  value.onkeydown = (e) => { if (e.key === "Enter") go(); };
  form.append(cat, key, value, add);
  return form;
}

async function openContext(name) {
  const org = session.current;
  $("list").hidden = true;
  $("people").hidden = true;
  $("detail").hidden = false;
  $("d-name").textContent = `${org}:${name}`;

  const c = await api(`/v1/contexts/${org}/${name}`);
  viewing = { org, name, canWrite: c.can_write };
  $("d-version").textContent = `v${c.version} · ${c.count} facts${c.can_write ? "" : " · read-only"}`;
  renderView(c.facts || {});

  const v = await api(`/v1/contexts/${org}/${name}/versions`);
  const box = $("d-versions");
  box.innerHTML = "";
  v.versions.forEach((ver, i) => {
    const row = el("div", "vrow");
    row.appendChild(el("span", "v", `v${ver.version}`));
    row.appendChild(el("span", "", `${ver.facts} facts`));
    row.appendChild(el("span", "by", `${ver.by} · ${ago(ver.at)}`));
    if (i > 0 && c.can_write) {
      const b = el("button", "link-btn", "revert to this");
      b.onclick = async () => {
        if (!confirm(`Revert ${name} to v${ver.version}? It's a new change, so every copy takes it on its next pull. Nothing is lost.`)) return;
        await post(`/v1/contexts/${org}/${name}/revert`, { version: ver.version });
        openContext(name);
      };
      row.appendChild(b);
    }
    box.appendChild(row);
  });
}

// Same menu as the rest of the site, whose last button is always "Console". In
// here it's "Sign out" when signed in, and "Sign in" on the sign-in form.
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
