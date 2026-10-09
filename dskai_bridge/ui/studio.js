let session, snapshot, activeQC;
const $ = selector => document.querySelector(selector);
function node(tag, text, parent, className) {
  const el = document.createElement(tag);
  if (text !== null) el.textContent = text;
  if (className) el.className = className;
  if (parent) parent.append(el);
  return el;
}
function notice(text) { $("#message").textContent = text; }
async function api(path, method = "GET", body) {
  const r = await fetch("/studio/api/" + path, {method, headers: {"Content-Type": "application/json", "X-CSRF-Token": session?.csrf || ""},
    ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  if (r.status === 401) { location.assign("/studio/login"); throw Error("Session expired"); }
  const value = await r.json();
  if (!r.ok) throw Error(typeof value.detail === "string" ? value.detail : "Invalid protocol record. Check required fields and versions.");
  return value;
}
const idKeys = ["schema_version","request_id","project","chapter","scene","shot","prompt_revision","take_id","take_version","request_sha256"];
function binding(result) { return Object.fromEntries(idKeys.map(k => [k, result[k]])); }
function mediaURL(m) { return "/studio/media/" + encodeURIComponent(m.asset_id) + "/" + m.version; }
async function record(kind, body) {
  await api("decisions/" + kind, "POST", body);
  notice("Decision recorded. Muse application remains pending until a worker acknowledgement arrives.");
  await refresh();
}
function button(parent, text, action) {
  const b = node("button", text, parent);
  b.addEventListener("click", () => Promise.resolve().then(action).catch(e => notice(e.message)));
}
function showJSON(parent, title, value) {
  const detail = node("details", null, parent); node("summary", title, detail);
  node("pre", JSON.stringify(value, null, 2), detail);
}
function render() {
  const selectedProject = $("#project").value;
  $("#project").replaceChildren();
  const all = node("option", "All projects", $("#project")); all.value = "";
  for (const p of [...new Set(snapshot.requests.map(r => r.project))].sort()) {
    const option = node("option", p, $("#project")); option.value = p;
  }
  $("#project").value = selectedProject;
  $("#submission").hidden = session.role !== "director";
  $("#connection").textContent = snapshot.sync.state + (snapshot.sync.error ? " · " + snapshot.sync.error : "");
  $("#sync").textContent = "Last successful synchronization: " +
    (snapshot.sync.last_success ? new Date(snapshot.sync.last_success * 1000).toLocaleString() : "Never") +
    " · Pending GitHub records: " + snapshot.pending_delivery;
  $("#shots").replaceChildren();
  const requests = snapshot.requests.filter(r => !selectedProject || r.project === selectedProject);
  if (!requests.length) node("p", "No production requests yet. No demo media or invented progress is shown.", $("#shots"));
  for (const r of requests) {
    const result = snapshot.results.find(x => x.request_id === r.request_id);
    const card = node("article", null, $("#shots"), "shot");
    const row = node("div", null, card, "row");
    node("h3", r.project + " / " + r.scene + " / " + r.shot, row);
    node("span", result?.status || "RECORDED — DELIVERY PENDING", row, "badge");
    node("p", "Prompt revision " + r.prompt_revision + " · Take " + r.take_version + " · " + r.relation, card);
    for (const f of snapshot.flags.filter(f => f.id === r.request_id)) node("p", f.reason, card);
    for (const b of result?.blockers || []) node("p", b, card);
    node("p", r.plan.primary_action, card);
    const story = node("div", null, card, "grid story");
    for (const m of r.plan.storyboard) {
      const img = node("img", null, story); img.src = mediaURL(m); img.alt = "Storyboard frame"; img.loading = "lazy";
    }
    showJSON(card, "Script, direction & continuity locks", r.plan);
    showJSON(card, "Reference assets & exact dependencies", {references: r.references, dependencies: r.dependencies});
    for (const m of result?.media || []) {
      if (m.mime.startsWith("video/") || m.mime.startsWith("audio/")) {
        const player = node(m.mime.startsWith("video/") ? "video" : "audio", null, card);
        player.controls = true; player.preload = "none"; player.src = mediaURL(m);
        player.addEventListener("error", () => notice("Media unavailable. Check the authenticated connection, tunnel origin and integrity status."));
      }
    }
    node("p", "Generations used: " + (result?.generations_used ?? "unknown") + " · Monetary cost: unavailable", card);
    const actions = node("div", null, card, "actions");
    const video = result?.media.find(m => m.mime === "video/mp4");
    if (session.role === "director") {
      // Request digest is supplied only by a verified result/claim; never fabricate one.
      const source = result || snapshot.claims.find(x => x.request_id === r.request_id);
      if (source) for (const action of ["HOLD", "RESUME"]) button(actions, action, async () => {
        const reason = prompt(action + " reason (queued intent; active renders cannot be cancelled)");
        if (reason) await record("control", {...binding(source), decision_id: crypto.randomUUID(), action, reason});
      });
      if (video) {
        button(actions, "Review take", () => {
          activeQC = {...binding(result), media_sha256: video.sha256};
          $("#qc-form").reset(); $("#qc-dialog").showModal();
        });
        button(actions, "Select retained cut", async () => {
          const values = prompt("Enter in-frame, last INCLUDED frame, timebase numerator, timebase denominator. Use measured media timing.");
          if (!values) return;
          const parts = values.split(",").map(Number);
          if (parts.length !== 4 || parts.some(x => !Number.isInteger(x))) throw Error("Four integer values required");
          const selections = snapshot.selections.filter(s => ["project","chapter","scene","shot"].every(k => s[k] === r[k]));
          await record("selection", {...binding(result), decision_id: crypto.randomUUID(), media_sha256: video.sha256,
            selection_revision: Math.max(0, ...selections.map(s => s.selection_revision)) + 1,
            in_frame: parts[0], last_retained_frame: parts[1], timebase_num: parts[2], timebase_den: parts[3]});
        });
      }
      button(actions, "Prepare correction", () => {
        const strategy = prompt("What will change in this attempt? A DONE take requires Kai's new-take mapping.");
        if (!strategy) return;
        const next = structuredClone(r);
        next.supersedes = r.request_id; next.request_id = crypto.randomUUID(); next.take_id = crypto.randomUUID();
        next.prompt_revision = Math.max(...snapshot.requests.filter(x => ["project","chapter","scene","shot"].every(k => x[k] === r[k])).map(x => x.prompt_revision)) + 1;
        next.take_version = Math.max(...snapshot.requests.filter(x => ["project","chapter","scene","shot"].every(k => x[k] === r[k])).map(x => x.take_version)) + 1;
        next.strategy_change = strategy; next.created_at = new Date().toISOString();
        $("#request-json").value = JSON.stringify(next, null, 2);
        notice("Correction draft prepared. Revise its prompt, scene plan and references before submitting."); $("#submission").scrollIntoView();
      });
    }
    if (session.role === "client" && video) {
      const selection = snapshot.selections.find(s => s.request_id === r.request_id);
      if (selection) for (const verdict of ["CLIENT_APPROVED", "CLIENT_REJECTED"]) button(actions, verdict.replace("_", " "), async () => {
        if (!confirm("Record " + verdict + " for this exact selected take and cut?")) return;
        await record("approval", {...binding(result), decision_id: crypto.randomUUID(), media_sha256: video.sha256,
          selection_revision: selection.selection_revision, verdict});
      });
    }
  }
  $("#history").replaceChildren();
  for (const item of snapshot.history.slice(-50).reverse()) showJSON($("#history"), item.verdict || item.action || item.outcome || item.status || "Record", item);
  $("#tasks").replaceChildren();
  for (const t of snapshot.director_tasks) node("p", t.request_id + " · " + (t.acked ? "Inspection recorded" : t.lease * 1000 > Date.now() ? "Inspection leased" : "Waiting for director"), $("#tasks"));
}
let refreshing = false;
async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try { snapshot = await api("state"); render(); }
  catch(e) { notice(e.message); $("#connection").textContent = "DISCONNECTED — displayed state may be stale"; }
  finally { refreshing = false; }
}
$("#refresh").addEventListener("click", refresh);
$("#project").addEventListener("change", render);
$("#request-form").addEventListener("submit", async event => {
  event.preventDefault();
  try { await api("requests", "POST", JSON.parse($("#request-json").value)); notice("Request recorded. Delivery and worker execution are separate states."); await refresh(); }
  catch(e) { notice(e.message); }
});
$("#qc-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await record("qc", {...activeQC, decision_id: crypto.randomUUID(), verdict: $("#verdict").value,
      full_motion_reviewed: $("#motion").checked, audio_listened: $("#listened").checked, cut_boundaries_reviewed: $("#cuts").checked,
      findings: [$("#findings").value], limitations: $("#limitations").value.trim() ? [$("#limitations").value] : []});
    $("#qc-dialog").close();
  } catch(e) { notice(e.message); $("#qc-dialog").close(); }
});
$("#close-qc").onclick = () => $("#qc-dialog").close();
$("#logout").onclick = async () => {
  await fetch("/studio/logout", {method:"POST", headers:{"X-CSRF-Token":session.csrf}});
  location.assign("/studio/login");
};
(async () => { session = await api("session"); await refresh(); setInterval(() => { if (!document.hidden) refresh(); }, 10000); })().catch(e => notice(e.message));
