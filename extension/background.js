// Pulls one job at a time from the local bridge, opens the allowlisted URL in one background tab,
// reads it with extract.js, and posts the payload back. It never fills or touches cookies; the only clicks are in meta.js (upload_metadata jobs) and pager.js (a page-number control of the portfolio pagination).
// upload_metadata jobs open the portal's Upload CSV dialog with the plan's CSV and set the common flags (meta.js allow list); Submit and Delete are never clicked.
// upload_stage jobs put plan-verified files on the Uploads page's drop zone (stage.js) and read the All (N) count back; nothing is clicked and the Submit button is never touched.
// The one extra read is intelHistory (extract.js): same-origin GETs of /en/content/<id>/history on the Not accepted page.
const BRIDGE = "http://127.0.0.1:8777";
const ALLOWED = /^(https:\/\/stock\.adobe\.com\/|https:\/\/contributor\.stock\.adobe\.com\/en\/(portfolio|uploads|uploads\/rejected)$)/;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let running = false;
let FILE_TOKEN = "";
importScripts("extract.js");
try { importScripts("token.js"); FILE_TOKEN = typeof INTEL_TOKEN === "string" ? INTEL_TOKEN : ""; } catch (e) { /* token.js is optional */ }

async function headers() {
  const { token } = await chrome.storage.local.get("token");
  return { "X-Intel-Token": token || FILE_TOKEN, "X-Intel-Ext": chrome.runtime.getManifest().version, "Content-Type": "application/json" };
}

async function note(s) { await chrome.storage.local.set({ last_state: `${new Date().toISOString()} ${s}` }); }

async function workTab(url) {
  const { tabId } = await chrome.storage.session.get("tabId");
  if (tabId) {
    try { await chrome.tabs.update(tabId, { url, active: false }); return tabId; } catch (e) { /* tab was closed */ }
  }
  const t = await chrome.tabs.create({ url, active: false });
  await chrome.storage.session.set({ tabId: t.id });
  return t.id;
}

function loaded(tabId, timeoutMs) {
  return new Promise((resolve) => {
    const done = (v) => { chrome.tabs.onUpdated.removeListener(fn); clearTimeout(timer); resolve(v); };
    const fn = (id, info) => { if (id === tabId && info.status === "complete") done(true); };
    const timer = setTimeout(() => done(false), timeoutMs);
    chrome.tabs.onUpdated.addListener(fn);
  });
}

async function extract(tabId, kind) {
  let last = null;
  for (let i = 0; i < 8; i++) {
    await chrome.scripting.executeScript({ target: { tabId }, files: ["extract.js"] });
    const [res] = await chrome.scripting.executeScript({ target: { tabId }, func: (k) => intelExtract(k), args: [kind] });
    last = res && res.result;
    const ready = last && (last.page_state || (kind === "asset" ? last.title && last.keywords && last.keywords.length
      : kind === "probe" ? last.text && last.text.length > 200
      : kind === "outcomes" ? last.ctx_found === true
      : kind === "portfolio" ? last.cards && last.cards.length && last.overview_downloads_text
      : last.rows && last.rows.length));
    if (ready) return last;
    await sleep(1500);
  }
  return last;
}

const STAGE_BATCH_BYTES = 12 * 1024 * 1024;
const MIME = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png" };
const submitCount = (t) => { const m = /^Submit\s+(\d+)\s+files?$/i.exec((t || "").trim()); return m ? Number(m[1]) : null; };

async function sha256Hex(buf) {
  return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", buf))).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function toBase64(buf) {
  const b = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return btoa(s);
}

async function pageCall(tabId, func, args) {
  const [res] = await chrome.scripting.executeScript({ target: { tabId }, func, args });
  return res && res.result;
}

// Reads the Uploads page counts once the list has finished loading: the same count twice in a row, no upload running.
async function readStable(tabId, names) {
  let last = null;
  let prev = null;
  for (let i = 0; i < 20; i++) {
    await sleep(1500);
    last = await pageCall(tabId, (n) => intelStageState(n), [names]);
    const ok = last && last.input_found && last.all_count !== null && !last.uploading;
    if (ok && prev === last.all_count) return last;
    prev = ok ? last.all_count : null;
  }
  return last;
}

async function reloadTab(tabId) {
  const done = loaded(tabId, 45000);
  await chrome.tabs.reload(tabId);
  await done;
  await chrome.scripting.executeScript({ target: { tabId }, files: ["stage.js"] });
}

// Fetches each plan file from the bridge, re-checks its sha256, hands it to the page's drop zone in small batches, then reloads the
// page and reads the "File types: All (N)" count again (read only). A background tab does not refresh its own list reliably, so the
// count that decides success always comes from a fresh page load.
async function stageFiles(tabId, job) {
  const base = await extract(tabId, "probe");
  const out = { kind: "upload_stage", page_state: base && base.page_state, http_status: base && base.http_status, error: null };
  if (!base || base.page_state || (base.http_status && base.http_status >= 400)) return out;
  const names = job.files.map((f) => f.name);
  await chrome.scripting.executeScript({ target: { tabId }, files: ["stage.js"] });
  out.before = await readStable(tabId, names);
  if (!out.before || !out.before.input_found) { out.error = "no_upload_input"; return out; }
  if (out.before.all_count === null || out.before.uploading) return out;
  let batch = [];
  let size = 0;
  const flush = async () => {
    if (!batch.length) return true;
    const r = await pageCall(tabId, (b) => intelStageBatch(b), [batch]);
    batch = [];
    size = 0;
    return !!(r && r.input_found && r.assigned > 0);
  };
  for (const f of job.files) {
    const r = await fetch(`${BRIDGE}/v1/file?job=${job.job_id}&i=${f.index}`, { headers: await headers() });
    if (!r.ok) { out.error = "bridge_file"; return out; }
    const buf = await r.arrayBuffer();
    if (buf.byteLength !== f.size || (await sha256Hex(buf)) !== f.sha256) { out.error = "sha_mismatch"; out.bad_file = f.name; return out; }
    if (batch.length && size + buf.byteLength > STAGE_BATCH_BYTES && !(await flush())) { out.error = "no_upload_input"; return out; }
    batch.push({ name: f.name, type: MIME[f.name.split(".").pop().toLowerCase()] || "application/octet-stream", b64: toBase64(buf) });
    size += buf.byteLength;
  }
  if (!(await flush())) { out.error = "no_upload_input"; return out; }
  const end = Date.now() + (job.stage_timeout_seconds || 120) * 1000;
  const startedAt = Date.now();
  for (;;) {  // let the page's own uploader finish before the fresh read
    await sleep(2000);
    const s = await pageCall(tabId, (n) => intelStageState(n), [names]);
    if ((s && !s.uploading && Date.now() - startedAt > 8000) || Date.now() > end) break;
  }
  await reloadTab(tabId);
  out.after = await readStable(tabId, names);
  out.names_seen = (out.after && out.after.names_seen) || [];
  return out;
}

// Polls the page until check(state) is true or the step times out; returns the last state either way.
async function waitMeta(tabId, ms, check) {
  const end = Date.now() + ms;
  let st = null;
  for (;;) {
    st = await pageCall(tabId, () => intelMetaState(), []);
    if (st && check(st)) return { ok: true, st };
    if (Date.now() > end) return { ok: false, st };
    await sleep(1000);
  }
}

async function injectMeta(tabId) { await chrome.scripting.executeScript({ target: { tabId }, files: ["meta.js"] }); }

// Applies the plan's CSV and the common flags to the files already in the New list, then reads the portal's own state back.
// Clicks happen only inside meta.js, through its allow list; Submit and Delete are never clicked. Any surprise stops with an error and the steps so far.
async function metaFlow(tabId, job) {
  const base = await extract(tabId, "probe");
  const out = { kind: "upload_metadata", page_state: base && base.page_state, http_status: base && base.http_status, error: null, steps: [] };
  if (!base || base.page_state || (base.http_status && base.http_status >= 400)) return out;
  const ms = (job.step_timeout_seconds || 90) * 1000;
  const fail = (e, st) => { out.error = e; if (st) out.detail = JSON.stringify(st).slice(0, 300); return out; };
  await injectMeta(tabId);
  const st0 = await pageCall(tabId, () => intelMetaState(), []);
  if (!st0 || st0.all_count === null || st0.uploading) return fail("page_not_ready", st0);
  if (st0.all_count !== job.count) return fail("count_mismatch", { all_count: st0.all_count, expected: job.count });
  out.steps.push("page_ready");
  const f = job.files[0];
  const r = await fetch(`${BRIDGE}/v1/file?job=${job.job_id}&i=${f.index}`, { headers: await headers() });
  if (!r.ok) return fail("bridge_file");
  const buf = await r.arrayBuffer();
  if (buf.byteLength !== f.size || (await sha256Hex(buf)) !== f.sha256) { out.bad_file = f.name; return fail("sha_mismatch"); }
  out.steps.push("csv_checked");
  const open = await pageCall(tabId, () => intelMetaOpenCsv(), []);
  if (!open || !open.clicked) return fail("csv_button_missing");
  const w1 = await waitMeta(tabId, ms, (s) => s.csv_input);
  if (!w1.ok) return fail("csv_dialog_missing", w1.st);
  out.steps.push("csv_dialog");
  const set = await pageCall(tabId, (x) => intelMetaSetCsv(x), [{ name: f.name, b64: toBase64(buf) }]);
  if (!set || !set.input_found || !set.assigned) return fail("csv_not_assigned");
  const w2 = await waitMeta(tabId, ms, (s) => !s.csv_modal);
  if (!w2.ok) return fail("csv_dialog_stayed_open", w2.st);
  out.steps.push("csv_applied");
  await sleep(3000);
  await reloadTab(tabId);
  await injectMeta(tabId);
  const w3 = await waitMeta(tabId, ms, (s) => s.all_count === job.count && !s.uploading);
  if (!w3.ok) return fail("page_not_ready_after_csv", w3.st);
  const sel = await pageCall(tabId, () => intelMetaSelectAll(), []);
  if (!sel || !sel.found || !sel.checked) return fail("select_all_failed", sel);
  const w4 = await waitMeta(tabId, ms, (s) => s.selected === job.count);
  if (!w4.ok) return fail("selection_count_mismatch", w4.st);
  out.steps.push("selected_all");
  out.flags_applied = await pageCall(tabId, (fl) => intelMetaApplyFlags(fl), [job.flags]);
  await sleep(1000);  // a box that appears only after another one is set; the call only clicks boxes still unchecked
  out.flags_applied = await pageCall(tabId, (fl) => intelMetaApplyFlags(fl), [job.flags]);
  out.steps.push("flags_clicked");
  await sleep(1500);
  const save = await pageCall(tabId, () => intelMetaSave(), []);
  out.steps.push(save && save.clicked ? "saved" : "save_not_clicked");
  await sleep(4000);
  await reloadTab(tabId);
  await injectMeta(tabId);
  const w5 = await waitMeta(tabId, ms, (s) => s.all_count === job.count && !s.uploading && s.submit_count !== null);
  out.after = w5.st;
  out.steps.push("verified_after_reload");
  return out;
}

let extInfo;
// Per-asset cause for the Not accepted list, in chunks so the service worker never idles through one long call.
async function addHistory(tabId, payload) {
  const ids = (payload.items || []).map((i) => i.asset_id).filter((n) => Number.isInteger(n) && n > 0).slice(0, 150);
  const history = {};
  await chrome.scripting.executeScript({ target: { tabId }, files: ["extract.js"] });
  for (let i = 0; i < ids.length; i += 10) {
    const [res] = await chrome.scripting.executeScript({ target: { tabId }, func: (c) => intelHistory(c), args: [ids.slice(i, i + 10)] });
    const part = (res && res.result) || {};
    if (part.__stop) { payload.http_status = part.__stop; break; }
    Object.assign(history, part);
  }
  payload.history = history;
}

async function whoAmI() {
  if (!extInfo) {
    const buf = new TextEncoder().encode(intelExtract.toString());
    const h = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", buf))).map((b) => b.toString(16).padStart(2, "0")).join("");
    extInfo = { version: chrome.runtime.getManifest().version, extract_fn_sha256: h };
  }
  return extInfo;
}

// The portfolio shows 100 assets per page. Reads page 1 as before, then clicks each further page number (pager.js, the only click) and
// collects the cards of every page, so accepted assets beyond page 1 are counted. Names stay page 1 only: later pages have no embedded list.
const PORTFOLIO_MAX_PAGES = 30;
async function readPortfolio(tabId) {
  const first = await extract(tabId, "portfolio");
  if (!first || first.page_state || !first.cards || !first.cards.length) return first;
  await chrome.scripting.executeScript({ target: { tabId }, files: ["pager.js"] });
  const nav = await pageCall(tabId, () => intelPagerPages(), []);
  const pages = ((nav && nav.pages) || []).filter((n) => n > 1 && n <= PORTFOLIO_MAX_PAGES);
  first.page_numbers = (nav && nav.pages) || [];
  first.pages_read = [1];
  const seen = new Set(first.cards.map((c) => c.asset_id));
  let before = await pageCall(tabId, () => intelPagerIds(), []);
  for (const n of pages) {
    const go = await pageCall(tabId, (x) => intelPagerGo(x), [n]);
    if (!go || !go.clicked) { first.pager_error = (go && go.reason) || "no_result"; break; }
    let ids = before;
    for (let i = 0; i < 20 && ids.join() === before.join(); i++) { await sleep(500); ids = await pageCall(tabId, () => intelPagerIds(), []); }
    if (ids.join() === before.join()) { first.pager_error = "page_did_not_change"; break; }
    const [res] = await chrome.scripting.executeScript({ target: { tabId }, func: (k) => intelExtract(k), args: ["portfolio"] });
    const cards = (res && res.result && res.result.cards) || [];
    for (const c of cards) if (!seen.has(c.asset_id)) { seen.add(c.asset_id); first.cards.push(c); }
    first.pages_read.push(n);
    before = ids;
    await sleep(800);
  }
  return first;
}

async function runJob(job) {
  if (!ALLOWED.test(job.url)) throw new Error("url not allowlisted");
  const tabId = await workTab(job.url);
  await loaded(tabId, 45000);
  const final = (await chrome.tabs.get(tabId)).url || "";
  // The portal sometimes redirects /en/uploads to /en/uploads?isa0=1 (seen 2026-10-16); accept only that exact query.
  const finalChecked = final.replace(/\?isa0=\d+$/, "");
  const payload = !ALLOWED.test(finalChecked) ? { page_state: "restricted", note: "redirected outside allowlist" }
    : job.kind === "upload_stage" ? await stageFiles(tabId, job)
    : job.kind === "upload_metadata" ? await metaFlow(tabId, job)
    : job.kind === "portfolio" ? await readPortfolio(tabId) : await extract(tabId, job.kind);
  if (job.kind === "outcomes" && payload.ctx_found && !payload.page_state) await addHistory(tabId, payload);
  payload._ext = await whoAmI();
  const r = await fetch(`${BRIDGE}/v1/result`, { method: "POST", headers: await headers(), body: JSON.stringify({ job_id: job.job_id, payload }) });
  await note(`job ${job.job_id} -> ${r.status}`);
}

async function loop() {
  if (running) return;
  running = true;
  try {
    for (;;) {
      try {
        const r = await fetch(`${BRIDGE}/v1/next`, { headers: await headers() });
        if (r.status === 401) { await note("bad token: open the extension options"); await sleep(15000); continue; }
        const j = await r.json();
        if (j.reload === true) { await note("reload requested by the user's CLI"); chrome.runtime.reload(); return; }
        if (j.job) await runJob(j.job);
        else if (j.reason && j.reason.startsWith("stopped")) { await note(`bridge stopped: ${j.reason}`); await sleep(20000); }
      } catch (e) {
        await note(`bridge unreachable: ${e.message}`);
        await sleep(5000);
      }
    }
  } finally { running = false; }
}

// Toolbar button: ask the bridge for the read-only dashboard link and open it in a normal tab.
chrome.action.onClicked.addListener(async () => {
  try {
    const r = await fetch(`${BRIDGE}/v1/dashboard-url`, { headers: await headers() });
    const { url } = await r.json();
    if (typeof url === "string" && url.startsWith(`${BRIDGE}/dashboard?t=`)) await chrome.tabs.create({ url });
    else await note("dashboard link refused");
  } catch (e) { await note(`dashboard unreachable: ${e.message}`); }
});

chrome.alarms.create("keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => { loop(); });
chrome.runtime.onStartup.addListener(() => { loop(); });
chrome.runtime.onInstalled.addListener(() => { loop(); });
loop();
