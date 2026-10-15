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
  const ok = INTEL_META_ALLOWED_DT.includes(dt) || label === "select-all" || label === "people-no" || label === "fictional";
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
function intelMetaApplyFlags(flags) {
  const out = {};
  const ai = document.querySelector('input[data-t="content-tagger-checkbox"]');
  if (flags.generative_ai && ai && !ai.checked) intelMetaClick(ai, "ai");
  out.ai_checked = ai ? ai.checked : null;
  const fic = intelMetaFictionalBox();
  if (flags.people_property_fictional && fic && !fic.checked) intelMetaClick(fic, "fictional");
  out.fictional_checked = fic ? fic.checked : null;
  const want = { no: "No", yes: "Yes", later: "Later" }[flags.people_property];
  const btn = Array.from(document.querySelectorAll("button")).find((b) => (b.textContent || "").trim() === want && b.closest("[class*='sidebar'], [class*='tagger'], form, section, div"));
  out.people_clicked = !!btn && intelMetaClick(btn, want === "No" ? "people-no" : "people-other");
  const inc = document.querySelector('input[data-t="reusable-checkbox"]');
  if (flags.include_in_submission && inc && !inc.checked) intelMetaClick(inc, "include");
  out.include_checked = inc ? inc.checked : null;
  return out;
}

function intelMetaSave() {
  const b = document.querySelector('button[data-t="save-work"]');
  if (!b || b.disabled) return { clicked: false, found: !!b };
  return { clicked: intelMetaClick(b, "save"), found: true };
}
if (typeof module !== "undefined") module.exports = { intelMetaClick, intelMetaState, intelMetaFictionalBox, intelMetaOpenCsv, intelMetaSetCsv, intelMetaSelectAll, intelMetaApplyFlags, intelMetaSave };
