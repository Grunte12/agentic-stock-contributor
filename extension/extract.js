// Read-only page extraction. No clicks, no cookies, no storage. intelHistory is the only network read: one same-origin GET per asset.
// Returns a plain object; all parsing of numbers happens later in Python.
// The uploads and portfolio pages embed their asset list as URL-encoded JSON. Only the whitelisted fields leave this function:
// the same state also holds a CSRF token, the user's profile and moderator data.
function intelContent() {
  const src = Array.from(document.scripts || []).map((s) => s.textContent || "").find((t) => t.includes("__react_context__"));
  const m = src && src.match(/__react_context__\s*=\s*"([^"]*)"/);
  if (!m) return { found: false, items: [] };
  try {
    const ctx = JSON.parse(decodeURIComponent(m[1]));
    const list = ctx && ctx.reduxState && ctx.reduxState.content;
    if (!Array.isArray(list)) return { found: false, items: [] };
    const meta = (ctx.reduxState.contentMeta) || {};
    return { found: true, total: Number.isInteger(meta.contentTotal) ? meta.contentTotal : null,
      items: list.slice(0, 500).map((e) => ({ asset_id: e.id, original_name: e.originalName || e.original_name || null,
        status: e.status || null, created_ms: e.creationDate, width: e.width, height: e.height, downloads: e.nb_downloads })) };
  } catch (err) { return { found: false, items: [], error: "json_parse" }; }
}

function intelExtract(kind) {
  const text = (document.body && document.body.innerText) || "";
  const h1 = document.querySelector("h1");
  const title = document.title || "";
  const host = location.hostname;
  let page_state = null;
  if (document.querySelector('iframe[src*="captcha" i], .g-recaptcha, #cf-challenge, [id*="captcha" i]') ||
      /captcha|verify you are human|unusual traffic/i.test(text.slice(0, 4000))) page_state = "captcha";
  else if (/temporarily restricted|access denied|too many requests/i.test(text.slice(0, 4000) + " " + title)) page_state = "restricted";
  else if (/adobelogin\.com|\/sign-?in/i.test(host + location.pathname)) page_state = "signin";

  let http_status = null;
  try {
    const nav = performance.getEntriesByType("navigation")[0];
    if (nav && typeof nav.responseStatus === "number" && nav.responseStatus > 0) http_status = nav.responseStatus;
  } catch (err) { /* leave null */ }
  const out = { kind, page_url: location.href, page_state, http_status, h1: h1 ? h1.innerText.slice(0, 300) : null };

  if (kind === "search" || kind === "contributor") {
    const el = document.getElementById("image-detail-json");
    let rows = [];
    if (el) {
      try {
        const j = JSON.parse(el.textContent);
        rows = Object.values(j).sort((a, b) => a.order_key - b.order_key).map((e) => ({
          rank: e.order_key,
          asset_id: e.content_id,
          title: e.title,
          creator_id: e.creator_id,
          is_gentech: e.is_gentech,
          category: e.category && e.category.name,
          w: e.content_original_width,
          h: e.content_original_height,
        }));
      } catch (err) { out.rows_error = "json_parse"; }
    }
    out.results_text = h1 ? h1.innerText.slice(0, 300) : null;
    out.rows = rows;
  } else if (kind === "portfolio") {
    const num = (sel) => { const e = document.querySelector(sel); return e ? e.textContent.trim() : null; };
    out.overview_downloads_text = num('[data-t="user-dashboard-overview-downloads"]');
    out.overview_earnings_text = num('[data-t="user-dashboard-overview-earnings"]');
    const tf = document.querySelector('[data-t="user-dashboard-overview-select"] select');
    out.time_frame = tf ? tf.value : null;
    const all = text.match(/All\((\d+)\)/);
    out.all_count_text = all ? all[0] : null;
    out.sort_text = (text.match(/Sort by [A-Za-z ]+/) || [null])[0];
    out.cards = Array.from(document.querySelectorAll('[data-t="portfolio-single-asset-wrapper"]')).map((c) => {
      const img = c.querySelector("img");
      const m = img && img.src.match(/_F_(\d+)_/);
      const v = c.querySelector("span.text-medium");
      return { asset_id: m ? Number(m[1]) : null, downloads_text: v ? v.textContent.trim() : null,
               thumb_url: img ? img.src.split("?")[0] : null };
    });
    const c = intelContent();
    out.named = c.items.map((i) => ({ asset_id: i.asset_id, original_name: i.original_name, status: i.status, created_ms: i.created_ms }));
    out.named_total = c.total;
  } else if (kind === "probe") {
    const c = intelContent();
    out.named = c.items.map((i) => ({ asset_id: i.asset_id, original_name: i.original_name, status: i.status }));
    out.named_total = c.total;
    out.text = text.slice(0, 40000);
    out.tab_labels = Array.from(new Set(text.match(/[A-Za-z][A-Za-z ]{2,24}\(\d+\)/g) || [])).slice(0, 40);
    const tags = {};
    document.querySelectorAll("[data-t]").forEach((e) => { const k = e.getAttribute("data-t"); tags[k] = (tags[k] || 0) + 1; });
    out.data_t = tags;
    const ids = new Set();
    document.querySelectorAll("img").forEach((i) => { const m = (i.src || "").match(/_F_(\d+)_/); if (m) ids.add(Number(m[1])); });
    out.asset_ids = Array.from(ids).slice(0, 500);
    out.sub_menus = Array.from(document.querySelectorAll('[data-t^="sub_menu"]')).slice(0, 20).map((e) => {
      const a = e.closest ? e.closest("a") : null;
      return { t: e.getAttribute("data-t"), tag: e.tagName, href: a ? a.href : (e.href || null), text: (e.textContent || "").trim().slice(0, 60) };
    });
    out.links = Array.from(document.querySelectorAll("a[href]")).map((a) => ({ text: (a.textContent || "").trim().slice(0, 60), href: a.href }))
      .filter((l) => /contributor\.stock\.adobe\.com/.test(l.href)).slice(0, 80);
    out.status_lines = text.split("\n").map((l) => l.trim()).filter((l) => l && l.length < 160 &&
      /reject|approv|pending|review|declin|accept|not accepted|similar|quality/i.test(l)).slice(0, 150);
  } else if (kind === "outcomes") {
    const c = intelContent();
    out.ctx_found = c.found;
    out.items = c.items.map(({ downloads, ...rest }) => rest);
    if (c.error) out.ctx_error = c.error;
  } else if (kind === "asset") {
    const m = location.pathname.match(/\/(\d{5,})(?:[/?]|$)/);
    out.asset_id = m ? Number(m[1]) : null;
    out.title = h1 ? h1.innerText.slice(0, 300) : null;
    const kws = [];
    document.querySelectorAll('[data-t^="similar-keyword-item-"]').forEach((el) => {
      const t = (el.textContent || "").trim();
      if (t && !kws.includes(t)) kws.push(t);
    });
    out.keywords = kws;
    const all = Array.from(document.querySelectorAll("button, a")).map((e) => (e.textContent || "").trim())
      .find((t) => t.length < 30 && /\(\d+\)\s*$/.test(t));
    out.keywords_total_text = all || null;
  }
  return out;
}
// Adobe's own per-asset moderation record, the same GET the Uploaded Files page makes when the user selects a tile.
// Same-origin, read-only, one asset at a time with a pause. Keeps the cause fields only (the reply also names a moderator).
async function intelHistory(ids) {
  const out = {};
  for (const id of ids) {
    if (!Number.isInteger(id) || id <= 0) continue;
    try {
      const r = await fetch(`/en/content/${id}/history`, { method: "GET" });
      if (r.status === 403 || r.status === 429) { out.__stop = r.status; break; }
      if (r.ok) {
        const j = await r.json();
        out[id] = { cause: j.cause, cause_label: j.causeLabel, status: j.status, status_label: j.statusLabel };
      }
    } catch (err) { /* leave this asset without a cause */ }
    await new Promise((res) => setTimeout(res, 800 + Math.random() * 700));
  }
  return out;
}
if (typeof module !== "undefined") module.exports = { intelExtract, intelHistory };
