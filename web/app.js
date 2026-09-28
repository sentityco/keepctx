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
// Everything below draws from three things: the facts, the prose sections the
// agents keep beside them, and the journal. No model and no server rendering,
// so a self-hosted server shows exactly the same page.

const FACT = /^\s*-\s+\*\*([^*]+)\*\*\s*([—→-])\s*(.*)$/;

function parseFacts(text) {
  const out = [];
  let cur = null;
  (text || "").split("\n").forEach((line) => {
    const m = line.match(FACT);
    if (m) {
      let value = m[3];
      const verified = value.includes("`[verified]`");
      value = value.replace("`[verified]`", "").trim();
      cur = { key: m[1].trim(), rel: m[2], value, verified, more: [] };
      out.push(cur);
    } else if (cur && line.trim() && /^\s/.test(line)) {
      cur.more.push(line.trim().replace(/^[-*]\s+/, ""));
    } else {
      cur = null;
    }
  });
  return out;
}

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// Markdown, the small part of it prose uses. Escaped first, so nothing in a
// context can put markup on the page.
function inline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" rel="noopener">$1</a>');
}

function md(text) {
  const blocks = (text || "").replace(/<!--[\s\S]*?-->/g, "").trim().split(/\n\s*\n/);
  return blocks.map((b) => {
    const lines = b.split("\n");
    if (/^#{1,6}\s/.test(lines[0]) && lines.length === 1) {
      return `<h4>${inline(lines[0].replace(/^#+\s*/, ""))}</h4>`;
    }
    if (lines.every((l) => /^\s*[-*]\s+/.test(l))) {
      return "<ul>" + lines.map((l) => `<li>${inline(l.replace(/^\s*[-*]\s+/, ""))}</li>`).join("") + "</ul>";
    }
    const head = /^#{1,6}\s/.test(lines[0]) ? `<h4>${inline(lines.shift().replace(/^#+\s*/, ""))}</h4>` : "";
    return head + (lines.length ? `<p>${inline(lines.join(" "))}</p>` : "");
  }).join("");
}

function factList(facts, strip) {
  const ul = el("ul", "flist");
  facts.forEach((f) => {
    const li = el("li");
    const label = strip && f.key.startsWith(strip + ".") ? f.key.slice(strip.length + 1) : f.key;
    li.innerHTML = `<span class="fk">${esc(label)}</span>` +
      `<span class="fr">${f.rel === "→" ? "→" : "—"}</span> ${inline(f.value)}` +
      (f.verified ? ' <span class="ok-tag">verified</span>' : "") +
      (f.more.length ? "<ul>" + f.more.map((m) => `<li>${inline(m)}</li>`).join("") + "</ul>" : "");
    ul.appendChild(li);
  });
  return ul;
}

function proseBlock(p) {
  const box = el("div", "prose");
  if (p.stale || p.orphaned) {
    box.appendChild(el("div", "stale",
      p.orphaned ? "No facts left under this section — it describes something that's gone."
                 : "The facts below changed after this was written. The next agent working here rewrites it."));
  }
  const body = el("div");
  body.innerHTML = md(p.text);
  box.appendChild(body);
  box.appendChild(el("div", "byline", `${p.by} · ${ago(p.at)}`));
  return box;
}

// The architecture, drawn from the → facts alone: each is an arrow from the
// thing the key is about to what it names. Nothing to invent components with.
function edgesOf(facts) {
  return facts.filter((f) => f.rel === "→").map((f) => {
    const [src, ...rest] = f.key.split(".");
    const tgt = f.value.replace(/`/g, "").split(/,|;| \(| — | - /)[0].trim().slice(0, 40);
    return { src, tgt, label: rest.join(".") };
  }).filter((e) => e.tgt && e.src.toLowerCase() !== e.tgt.toLowerCase());
}

function diagram(edges) {
  const NS = "http://www.w3.org/2000/svg";
  const names = new Map();                      // lowercased -> as first written
  edges.forEach((e) => [e.src, e.tgt].forEach((n) => { if (!names.has(n.toLowerCase())) names.set(n.toLowerCase(), n); }));
  const ids = [...names.keys()];
  const layer = Object.fromEntries(ids.map((i) => [i, 0]));
  for (let pass = 0; pass < ids.length; pass++) {   // longest path; the cap ends cycles
    let moved = false;
    edges.forEach((e) => {
      const s = e.src.toLowerCase(), t = e.tgt.toLowerCase();
      if (layer[t] < layer[s] + 1 && layer[s] + 1 < ids.length) { layer[t] = layer[s] + 1; moved = true; }
    });
    if (!moved) break;
  }
  const cols = {};
  ids.forEach((i) => { (cols[layer[i]] = cols[layer[i]] || []).push(i); });
  // order each column by where its neighbours sit (barycentres), a few sweeps
  // each way: the usual cheap fix for arrows crossing each other
  const rank = {};
  const setRanks = () => Object.values(cols).forEach((c) => c.forEach((i, r) => { rank[i] = r; }));
  setRanks();
  const nbrs = (i, dir) => edges.filter((e) => (dir > 0 ? e.tgt : e.src).toLowerCase() === i)
    .map((e) => (dir > 0 ? e.src : e.tgt).toLowerCase());
  const L = Object.keys(cols).map(Number).sort((a, b) => a - b);
  for (let sweep = 0; sweep < 4; sweep++) {
    const dir = sweep % 2 ? -1 : 1;
    (dir > 0 ? L.slice(1) : L.slice(0, -1).reverse()).forEach((l) => {
      const bary = (i) => { const n = nbrs(i, dir); return n.length ? n.reduce((s, x) => s + rank[x], 0) / n.length : rank[i]; };
      cols[l].sort((a, b) => bary(a) - bary(b));
      setRanks();
    });
  }
  const W = 150, H = 38, CW = 225, RH = 72, PAD = 12;
  const pos = {};
  Object.entries(cols).forEach(([l, list]) => list.forEach((i, r) => { pos[i] = { x: PAD + l * CW, y: PAD + r * RH }; }));
  const width = PAD * 2 + (Math.max(...Object.keys(cols).map(Number)) * CW) + W;
  const height = PAD * 2 + (Math.max(...Object.values(cols).map((c) => c.length)) - 1) * RH + H;

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", width);
  svg.setAttribute("class", "dg");
  svg.innerHTML = '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="dg-head"/></marker></defs>';
  const add = (tag, attrs, text) => {
    const n = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v));
    if (text !== undefined) n.textContent = text;
    svg.appendChild(n);
    return n;
  };
  edges.forEach((e) => {
    const a = pos[e.src.toLowerCase()], b = pos[e.tgt.toLowerCase()];
    const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2;
    const d = b.x > a.x
      ? `M${x1} ${y1} C${x1 + 40} ${y1} ${x2 - 40} ${y2} ${x2} ${y2}`
      : `M${a.x + W / 2} ${a.y + H} C${a.x + W / 2} ${a.y + H + 40} ${b.x + W / 2} ${b.y + H + 40} ${b.x + W / 2} ${b.y + H}`;
    add("path", { d, class: "dg-edge", "marker-end": "url(#arr)" });
    if (e.label) {
      const mx = b.x > a.x ? (x1 + x2) / 2 : (a.x + b.x + W) / 2;
      const my = b.x > a.x ? (y1 + y2) / 2 - 5 : Math.max(a.y, b.y) + H + 34;
      add("text", { x: mx, y: my, class: "dg-label", "text-anchor": "middle" }, e.label);
    }
  });
  ids.forEach((i) => {
    const p = pos[i], full = names.get(i);
    add("rect", { x: p.x, y: p.y, width: W, height: H, rx: 7, class: "dg-node" });
    const t = add("text", { x: p.x + W / 2, y: p.y + H / 2 + 4.5, class: "dg-text", "text-anchor": "middle" },
      full.length > 20 ? full.slice(0, 19) + "…" : full);
    if (full.length > 20) { const tt = document.createElementNS(NS, "title"); tt.textContent = full; t.appendChild(tt); }
  });
  const wrap = el("div", "dg-wrap");
  wrap.appendChild(svg);
  return wrap;
}

// Intent comes first, in this order; every other prefix is an area of its own.
const INTENT = [
  ["goal", "Goals"], ["req", "Requirements"], ["decision", "Decisions"],
  ["rejected", "Considered and rejected"], ["question", "Open questions"],
];

function renderView(v) {
  const box = $("d-view");
  box.innerHTML = "";
  const facts = parseFacts(v.facts);
  const prose = Object.fromEntries(v.prose.map((p) => [p.section, p]));
  const prefix = (f) => f.key.split(".")[0];
  const under = (p) => facts.filter((f) => prefix(f) === p);
  const section = (title, cls) => {
    const s = el("div", "vsec " + (cls || ""));
    s.appendChild(el("h3", "", title));
    box.appendChild(s);
    return s;
  };
  const used = new Set();

  if (!facts.length && !v.prose.length && !v.journal.length) {
    const e = el("div", "empty");
    e.appendChild(el("p", "", "Nothing captured yet."));
    e.appendChild(el("p", "", "As agents work in this project, what they learn and decide shows up here."));
    box.appendChild(e);
    return;
  }

  const ov = prose.overview;
  const purpose = under("purpose");
  if (ov || purpose.length) {
    const s = section("Overview", "lead");
    if (ov) { s.appendChild(proseBlock(ov)); used.add("overview"); }
    if (purpose.length) s.appendChild(factList(purpose, "purpose"));
    used.add("purpose");
  }

  const edges = edgesOf(facts);
  if (edges.length) {
    const s = section("Architecture");
    if (prose.architecture) { s.appendChild(proseBlock(prose.architecture)); used.add("architecture"); }
    s.appendChild(diagram(edges));
    s.appendChild(el("p", "hint", "Drawn from the → relationships in the facts, so it shows only what's recorded."));
  }

  INTENT.forEach(([p, title]) => {
    const list = under(p);
    used.add(p);
    if (!list.length && !prose[p]) return;
    const s = section(title, p === "question" ? "open" : "");
    if (prose[p]) s.appendChild(proseBlock(prose[p]));
    if (list.length) s.appendChild(factList(list, p));
  });

  const areas = [...new Set(facts.map(prefix).concat(v.prose.map((p) => p.section)))]
    .filter((p) => !used.has(p)).sort();
  areas.forEach((p) => {
    const s = section(p);
    if (prose[p]) s.appendChild(proseBlock(prose[p]));
    const list = under(p);
    if (list.length) s.appendChild(factList(list, p));
  });

  if (v.journal.length) {
    const s = section("Journal");
    s.appendChild(el("p", "sub", "How it got this way — written by the agents as the work happened."));
    v.journal.forEach((j) => {
      const row = el("div", "jrow");
      const when = new Date(j.at * 1000);
      row.appendChild(el("div", "jwhen",
        `${when.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })} · ${j.by}`));
      const body = el("div", "jbody");
      body.innerHTML = md(j.text);
      row.appendChild(body);
      s.appendChild(row);
    });
  }
}

async function openContext(name) {
  const org = session.current;
  $("list").hidden = true;
  $("people").hidden = true;
  $("detail").hidden = false;
  $("d-name").textContent = `${org}:${name}`;

  const c = await api(`/v1/contexts/${org}/${name}/view`);
  $("d-version").textContent = `v${c.version} · ${c.count} facts · ${ago(c.updated)}`;
  $("d-facts").textContent = c.facts || "(empty)";
  renderView(c);

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
        if (!confirm(`Revert ${name} to v${ver.version}? This creates a new version — nothing is lost.`)) return;
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
