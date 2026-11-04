// Fills metadata of files already in the Uploads page's New list. Every click goes through intelMetaClick, which refuses
// anything that is not on the short allow list below and anything that looks like Submit or Delete. It never touches
// the Submit button except to read its text. Titles, keywords and categories come from the plan's CSV through the
// portal's own "Upload CSV" dialog; this file only opens that dialog, hands it the CSV and sets four common flags.
const INTEL_META_DENY = /submit|delete|remove|trash|publish|release/i;
const INTEL_META_ALLOWED_DT = ["edit-menu-upload-csv", "content-tagger-checkbox", "reusable-checkbox", "save-work"];

function intelMetaClick(el, label) {
  if (!el) return false;
  const dt = el.getAttribute("data-t") || "";
  const aria = el.getAttribute("aria-label") || "";
  const text = (el.textContent || "").trim();
  if (el.closest('[data-t="submit-moderation-button"]') || INTEL_META_DENY.test(dt) || INTEL_META_DENY.test(aria) || /^submit/i.test(text)) return false;
  const ok = INTEL_META_ALLOWED_DT.includes(dt) || label === "select-all" || label === "people-no" || label === "fictional" || label === "scoped-tile";
  if (!ok) return false;
  el.click();
  return true;
}

// The checkbox "People and Property are fictional" has no data-t; find it by its own label text.
function intelMetaFictionalBox() {
  return Array.from(document.querySelectorAll('input[type="checkbox"]')).find((i) => (((i.closest("label") || i.parentElement || {}).innerText) || "").trim() === "People and Property are fictional") || null;
}

function intelMetaState() {
  const text = (document.body && document.body.innerText) || "";
  const all = text.match(/File types:\s*All\s*\((\d+)\)/i);
  const sub = document.querySelector('[data-t="submit-moderation-button"]');
  const sm = sub && /^Submit\s+(\d+)\s+files?$/i.exec((sub.textContent || "").trim());
  const grid = document.querySelector('[data-t="assets-content-grid"]');
  const sel = text.match(/affect\s+(\d+)\s+selected\s+files?/i);
  const ai = document.querySelector('input[data-t="content-tagger-checkbox"]');
  const inc = document.querySelector('input[data-t="reusable-checkbox"]');
  const fic = intelMetaFictionalBox();
  return {
    all_count: all ? parseInt(all[1], 10) : null, submit_count: sm ? parseInt(sm[1], 10) : null,
    uploading: /\d+\s+Uploads?\s+Remaining/i.test(text), selected: sel ? parseInt(sel[1], 10) : 0,
    keyword_counts: grid ? Array.from(grid.children).map((t) => { const m = (t.innerText || "").match(/\d+/); return m ? parseInt(m[0], 10) : null; }) : [],
    csv_modal: !!document.querySelector('[data-t="csv-modal"]'), csv_input: !!document.querySelector('[data-t="csv-modal"] input[type="file"]'),
    ai_checked: ai ? ai.checked : null, include_checked: inc ? inc.checked : null, fictional_checked: fic ? fic.checked : null,
    save_enabled: (() => { const b = document.querySelector('[data-t="save-work"]'); return b ? !b.disabled : null; })(),
  };
}

// Identity is proven twice: the sole active grid tile and the sidebar thumbnail must agree.
function intelMetaSelected(id) {
  const grid = document.querySelector('[data-t="assets-content-grid"]');
  const tiles = grid ? Array.from(grid.querySelectorAll('.upload-tile__wrapper')) : [];
  const active = tiles.filter((t) => t.classList.contains('active'));
  const side = Array.from(document.querySelectorAll('[data-t="asset-sidebar-header-thumbnail"]'));
  const thumbId = (el) => { const img = el && (el.matches('img') ? el : el.querySelector('img')); const m = img && (img.src || '').match(/_F_(\d+)_/); return m ? Number(m[1]) : null; };
  return intelMetaState().selected <= 1 && active.length === 1 && side.length === 1 && thumbId(active[0]) === id && thumbId(side[0]) === id;
}

function intelMetaSelectId(id) {
  if (!Number.isSafeInteger(id) || id <= 0) return {clicked: false};
  const grid = document.querySelector('[data-t="assets-content-grid"]');
  const tiles = grid ? Array.from(grid.querySelectorAll('.upload-tile__wrapper')) : [];
  const matches = tiles.filter((t) => { const imgs = t.querySelectorAll('img[alt="thumbnail"]'); return imgs.length === 1 && (imgs[0].src || '').match(/_F_(\d+)_/)?.[1] === String(id); });
  if (matches.length !== 1) return {clicked: false};
  if (intelMetaSelected(id)) return {clicked: true};
  return {clicked: intelMetaClick(matches[0], "scoped-tile")};
}

function intelMetaScopedState(id) {
  if (!intelMetaSelected(id)) return null;
  const all = Array.from(document.querySelectorAll('input[type="checkbox"]')).find((i) => ((i.closest("label") || {}).innerText || "").trim() === "Select All");
  if (!all || all.checked) return null;
  const st = intelMetaState();
  const text = (document.body && document.body.innerText) || "";
  const people_prompt_visible = /(?:Add )?recognizable people or property\?/i.test(text);
  return {ai_checked: st.ai_checked, include_checked: st.include_checked, fictional_checked: st.fictional_checked,
    people_prompt_visible, save_enabled: st.save_enabled};
}

function intelMetaTarget(id, name) {
  if (!intelMetaSelected(id)) return null;
  const title = document.querySelector('textarea[data-t="asset-title-content-tagger"]');
  const keywords = document.querySelector('textarea[data-t="content-keywords-ui-textarea"]');
  const st = intelMetaState();
  const scoped = intelMetaScopedState(id);
  if (!scoped) return null;
  const categories = Array.from(document.querySelectorAll('button[data-t="content-tagger-category-select"]'));
  return {asset_id: id, original_name: name, category: categories.length === 1 ? (categories[0].textContent || "").trim() : null,
    people_prompt_visible: scoped.people_prompt_visible, people_property: null, keyword_count: keywords ? keywords.value.split(",").filter((k) => k.trim()).length : null,
    ai_checked: st.ai_checked, include_checked: st.include_checked, fictional_checked: st.fictional_checked,
    title: title ? title.value : null, keywords: keywords ? keywords.value : null};
}

function intelMetaOpenCsv() {
  const b = document.querySelector('button[data-t="edit-menu-upload-csv"]');
  return { clicked: !!b && (b.textContent || "").trim() === "Upload CSV" && intelMetaClick(b, "csv") };
}

function intelMetaSetCsv(f) {
  const input = document.querySelector('[data-t="csv-modal"] input[type="file"]');
  if (!input) return { input_found: false };
  const bin = atob(f.b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const dt = new DataTransfer();
  dt.items.add(new File([bytes], f.name, { type: "text/csv" }));
  input.files = dt.files;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  return { input_found: true, assigned: input.files.length };
}

function intelMetaSelectAll() {
  const box = Array.from(document.querySelectorAll('input[type="checkbox"]')).find((i) => ((i.closest("label") || {}).innerText || "").trim() === "Select All");
  if (!box) return { found: false };
  if (!box.checked) intelMetaClick(box, "select-all");
  return { found: true, checked: box.checked };
}

// With every file selected: set the common flags. A box is clicked only when it is not already in the wanted state.
function intelMetaApplyFlags(flags, id) {
  const guarded = (el, label) => (id === undefined || intelMetaScopedState(id)) && intelMetaClick(el, label);
  const out = {};
  const ai = document.querySelector('input[data-t="content-tagger-checkbox"]');
  if (flags.generative_ai && ai && !ai.checked) guarded(ai, "ai");
  out.ai_checked = ai ? ai.checked : null;
  const fic = intelMetaFictionalBox();
  if (flags.people_property_fictional && fic && !fic.checked) guarded(fic, "fictional");
  out.fictional_checked = fic ? fic.checked : null;
  const want = { no: "No", yes: "Yes", later: "Later" }[flags.people_property];
  const btn = Array.from(document.querySelectorAll("button")).find((b) => (b.textContent || "").trim() === want && b.closest("[class*='sidebar'], [class*='tagger'], form, section, div"));
  // Scoped AI metadata proves the fictional checkbox, never a generic Yes/No button.
  out.people_clicked = id === undefined && !!btn && guarded(btn, want === "No" ? "people-no" : "people-other");
  const inc = document.querySelector('input[data-t="reusable-checkbox"]');
  if (flags.include_in_submission && inc && !inc.checked) guarded(inc, "include");
  out.include_checked = inc ? inc.checked : null;
  return out;
}

function intelMetaSave(id) {
  if (id !== undefined && !intelMetaScopedState(id)) return { clicked: false, found: false };
  const b = document.querySelector('button[data-t="save-work"]');
  if (!b || b.disabled) return { clicked: false, found: !!b };
  return { clicked: intelMetaClick(b, "save"), found: true };
}
if (typeof module !== "undefined") module.exports = { intelMetaClick, intelMetaState, intelMetaFictionalBox, intelMetaOpenCsv, intelMetaSetCsv, intelMetaSelectAll, intelMetaApplyFlags, intelMetaSave, intelMetaSelected, intelMetaSelectId, intelMetaScopedState, intelMetaTarget };
