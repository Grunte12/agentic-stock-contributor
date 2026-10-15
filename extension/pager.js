// Portfolio pager. The portfolio list shows 100 assets per page, so a read of page 1 misses the rest.
// One guarded click: only a plain page-number control inside the portal's own pagination block (data-t="core-pagination").
// Next/Previous, anything outside that block and anything named submit, delete, remove, trash, publish or release is refused.
const INTEL_PAGER_DENY = /submit|delete|remove|trash|publish|release|save|upload/i;
function intelPagerNav() { return document.querySelector('[data-t="core-pagination"]'); }
function intelPagerControls(nav) {
  const hit = Array.from(nav.querySelectorAll("button, a, [role='button']"));
  return hit.length ? hit : Array.from(nav.querySelectorAll("li"));
}
function intelPagerPages() {
  const nav = intelPagerNav();
  if (!nav) return { found: false, pages: [] };
  const nums = intelPagerControls(nav).map((e) => (e.textContent || "").trim()).filter((t) => /^\d{1,3}$/.test(t)).map(Number);
  return { found: true, pages: Array.from(new Set(nums)).sort((a, b) => a - b) };
}
function intelPagerGo(n) {
  if (!Number.isInteger(n) || n < 1 || n > 200) return { clicked: false, reason: "bad_page" };
  const nav = intelPagerNav();
  if (!nav) return { clicked: false, reason: "no_pagination" };
  const el = intelPagerControls(nav).find((e) => (e.textContent || "").trim() === String(n));
  if (!el) return { clicked: false, reason: "no_such_page" };
  const label = `${el.getAttribute("data-t") || ""} ${el.getAttribute("aria-label") || ""}`;
  if (INTEL_PAGER_DENY.test(label)) return { clicked: false, reason: "denied_control" };
  el.click();
  return { clicked: true };
}
function intelPagerIds() {
  const ids = [];
  document.querySelectorAll('[data-t="portfolio-single-asset-wrapper"] img').forEach((i) => {
    const m = (i.src || "").match(/_F_(\d+)_/);
    if (m) ids.push(Number(m[1]));
  });
  return ids;
}
if (typeof module !== "undefined") module.exports = { intelPagerPages, intelPagerGo, intelPagerIds };
