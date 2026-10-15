// Stages verified files on the Uploads page: hands them to the page's own drop zone (the page's uploader listens for a drop
// event, not for a script-set file input), then reads the portal's own counts back.
// It never clicks, never submits and never touches the Submit button. The files arrive already checked against the
// plan's sha256 by background.js. Measured 2026-10-12: a `drop` on `.uploader__drop` starts the upload; setting
// input.files plus input/change events does nothing; "Submit N files" counts only files already included in a
// submission, so the count that proves staging is "File types: All (N)".
function intelDropZone() {
  return document.querySelector(".uploader__drop") || document.querySelector(".uploader");
}

function intelStageBatch(batch) {
  const zone = intelDropZone();
  if (!zone) return { input_found: false, assigned: 0 };
  const dt = new DataTransfer();
  for (const f of batch) {
    const bin = atob(f.b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    dt.items.add(new File([bytes], f.name, { type: f.type }));
  }
  for (const t of ["dragenter", "dragover", "drop"]) zone.dispatchEvent(new DragEvent(t, { bubbles: true, cancelable: true, dataTransfer: dt }));
  return { input_found: true, assigned: dt.files.length };
}

function intelStageState(names) {
  const text = (document.body && document.body.innerText) || "";
  const m = text.match(/File types:\s*All\s*\((\d+)\)/i);
  const byTag = document.querySelector('[data-t="submit-moderation-button"]');
  return { input_found: !!intelDropZone(), all_count: m ? parseInt(m[1], 10) : null, uploading: /\d+\s+Uploads?\s+Remaining/i.test(text),
    submit_text: byTag ? (byTag.textContent || "").trim() : null, names_seen: (names || []).filter((n) => text.includes(n)) };
}
if (typeof module !== "undefined") module.exports = { intelDropZone, intelStageBatch, intelStageState };
