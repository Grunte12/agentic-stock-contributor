const $ = (id) => document.getElementById(id);
chrome.storage.local.get("token").then((v) => { if (v.token) $("token").value = v.token; });
$("save").addEventListener("click", async () => {
  await chrome.storage.local.set({ token: $("token").value.trim() });
  $("msg").textContent = "Saved";
});
chrome.storage.local.get(["last_state"]).then((v) => { $("state").textContent = v.last_state || ""; });
