// Mockup shell: draws the sidebar (laptop), top bar and bottom tabs (phone) of web/app/(app)/layout.tsx
// with the IA approved at checkpoint A (spec §6), plus a mockup-only bar that switches page states.
// <body data-page="home" data-states="live empty loading error stale"> ... </body>
(function () {
  const NAV = [
    ["home", "Home", "home.html", "⌂"],
    ["review", "Review", "review.html", "▶"],
    ["calendar", "Calendar", null, "▦"],
    ["accounts", "Accounts", "accounts.html", "◫"],
    ["produce", "Produce", "produce.html", "✚"],
    ["experiments", "Experiments", null, "⚗"],
    ["results", "Results", "results.html", "▤"],
    ["sources", "Sources", null, "⛁"],
  ];
  const MORE = [["personas", "Personas", "personas.html"], ["jobs", "Jobs", null], ["decisions", "Decisions", null],
    ["desk", "Desk", null], ["funnel", "Funnel", null], ["settings", "Settings", null]];
  const TABS = [["home", "Home", "home.html", "⌂", 3], ["review", "Review", "review.html", "▶", 0],
    ["accounts", "Accounts", "accounts.html", "◫", 0], ["results", "Results", "results.html", "▤", 0],
    ["more", "More", "personas.html", "⋯", 0]];
  const COUNTS = { home: 3, review: 4 };

  const body = document.body;
  const page = body.dataset.page;
  const el = (tag, attrs, text) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    if (text != null) n.textContent = text;
    return n;
  };

  // Mockup bar
  const bar = el("div", { class: "mock-bar", role: "region", "aria-label": "Mockup controls" });
  const left = el("div", { class: "row wrap" });
  left.append(el("a", { href: "index.html" }, "← All mockups"), el("span", {}, "Static mockup · sample data, not real accounts"));
  bar.append(left);
  const states = (body.dataset.states || "live").split(" ");
  const sw = el("div", { class: "states", role: "group", "aria-label": "Page state" });
  const LABEL = { live: "Live", empty: "Empty", loading: "Loading", error: "Error", stale: "Stale", over: "Over budget", done: "Already handled", spend: "Spend row", promote: "Promotion row", pres2: "Before S2", faces: "Step 2: faces", brief: "Step 1: brief", voice: "Step 4: voice", lora: "Step 6: LoRA", link: "Step 7: link" };
  const set = (s) => {
    body.dataset.state = s;
    const note = document.getElementById("stale-note");
    if (note) note.hidden = s !== "stale";
    document.querySelectorAll("[data-when]").forEach((n) => {
      const when = n.dataset.when.split(" ");
      n.hidden = !(when.includes(s) || (s === "stale" && when.includes("live")));
    });
    sw.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.s === s)));
    try { history.replaceState(null, "", "#" + s); } catch (e) { /* file:// may refuse */ }
  };
  states.forEach((s) => {
    const b = el("button", { type: "button", "data-s": s }, LABEL[s] || s);
    b.addEventListener("click", () => set(s));
    sw.append(b);
  });
  bar.append(sw);
  // Account type switch (mockup only): <body data-accts="clips story ..."> shows [data-type~=<type>] blocks.
  const types = (body.dataset.accts || "").split(" ").filter(Boolean);
  if (types.length) {
    const sel = el("select", { "aria-label": "Account type", style: "width:auto;min-height:0;padding:0.1rem 0.4rem;font-size:0.75rem" });
    types.forEach((t) => sel.append(el("option", { value: t }, "Type: " + t)));
    const applyType = (t) => {
      body.dataset.acct = t; sel.value = t;
      document.querySelectorAll("[data-type]").forEach((n) => n.classList.toggle("type-on", n.dataset.type.split(" ").includes(t)));
      document.querySelectorAll("[data-tabs]").forEach((g) => { const b = g.querySelector('[data-tab="' + g.dataset.tabs + '"]'); if (b) b.click(); });
      window.dispatchEvent(new Event("resize"));
    };
    sel.addEventListener("change", () => applyType(sel.value));
    body._applyType = applyType;
    const q = new URLSearchParams(location.search).get("type");
    body.dataset.acct = types.includes(q) ? q : types[0];
    sw.prepend(sel);
  }
  body.prepend(bar);

  // Sidebar
  const side = el("nav", { class: "sidebar", "aria-label": "Sidebar" });
  side.append(el("span", { class: "brand" }, "ClipForge"));
  const ul = el("ul");
  NAV.forEach(([id, label, href]) => {
    const li = el("li");
    const a = el("a", { href: href || "#", ...(id === page ? { "aria-current": "page" } : {}), ...(href ? {} : { title: "Not mocked in card 009" }) });
    a.append(el("span", {}, label));
    if (COUNTS[id]) a.append(el("span", { class: "count", "aria-label": COUNTS[id] + " need you" }, String(COUNTS[id])));
    li.append(a); ul.append(li);
  });
  const more = el("li"); more.append(el("span", { class: "more-label" }, "More")); ul.append(more);
  MORE.forEach(([id, label, href]) => {
    const li = el("li");
    li.append(el("a", { href: href || "#", ...(id === page ? { "aria-current": "page" } : {}) }, label));
    ul.append(li);
  });
  side.append(ul);
  const foot = el("div", { class: "foot" });
  foot.append(el("span", { class: "xs muted" }, "Brake: all accounts running"), el("button", { class: "btn", type: "button" }, "Pause all"),
    el("button", { class: "btn ghost", type: "button", style: "justify-content:flex-start;padding:0;color:var(--muted-foreground)" }, "Sign out"));
  side.append(foot);
  body.prepend(side);

  // Phone top bar and bottom tabs
  const pageWrap = document.querySelector(".page");
  const top = el("header", { class: "topbar" });
  const topR = el("div", { class: "row" });
  topR.append(el("button", { class: "btn ghost", type: "button", "aria-label": "Add a note or hook idea" }, "+ Note"),
    el("button", { class: "btn ghost", type: "button", style: "color:var(--muted-foreground)" }, "Sign out"));
  top.append(el("span", { class: "brand" }, "ClipForge"), topR);
  pageWrap.prepend(top);
  // S3a's StaleNote: one quiet line, shown in the "stale" state; nothing dims and actions stay enabled.
  const main = document.querySelector("main");
  if (main && states.includes("stale")) {
    const n = el("p", { id: "stale-note", class: "xs muted", role: "status", hidden: "" }, "Updated 6 min ago · retrying every 15 s. Actions still work; each one is re-checked when you tap it.");
    main.prepend(n);
  }
  const tabs = el("nav", { class: "tabs-bottom", "aria-label": "Tabs" });
  TABS.forEach(([id, label, href, glyph, n]) => {
    const a = el("a", { href, ...(id === page || (id === "more" && page === "personas") ? { "aria-current": "page" } : {}) });
    a.append(el("span", { class: "glyph", "aria-hidden": "true" }, glyph), el("span", {}, label));
    if (n) a.append(el("span", { class: "dot", "aria-label": n + " need you" }, String(n)));
    tabs.append(a);
  });
  body.append(tabs);

  const first = (location.hash || "").slice(1);
  set(states.includes(first) ? first : states[0]);

  // Simple tab groups: <div data-tabs> buttons[data-tab=x] + panels[data-panel=x]
  document.querySelectorAll("[data-tabs]").forEach((g) => {
    const scope = g.closest("[data-tab-scope]") || document;
    const show = (id) => {
      g.querySelectorAll("[data-tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === id)));
      scope.querySelectorAll("[data-panel]").forEach((p) => { p.hidden = p.dataset.panel !== id; });
    };
    g.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
    show(g.dataset.tabs);
  });
  if (body._applyType) body._applyType(body.dataset.acct);
  // Switches and dials are clickable so the mockup feels real.
  document.querySelectorAll(".switch").forEach((s) => s.addEventListener("click", () =>
    s.setAttribute("aria-checked", String(s.getAttribute("aria-checked") !== "true"))));
  document.querySelectorAll(".dial").forEach((d) => d.querySelectorAll("button").forEach((b) => b.addEventListener("click", () =>
    d.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", String(x === b))))));
})();
