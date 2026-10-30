import json
import re
import shutil
import subprocess
import unittest

from helpers import ROOT

EXT = ROOT / "extension"
FORBIDDEN_JS = [r"chrome\.cookies", r"document\.cookie", r"localStorage", r"sessionStorage", r"indexedDB",
                r"\.click\(", r"\.submit\(", r"\beval\(", r"new Function", r"XMLHttpRequest", r"WebSocket",
                r"chrome\.debugger", r"chrome\.webRequest", r"chrome\.history", r"chrome\.downloads",
                r"\.value\s*=", r"dispatchEvent", r"chrome\.management"]


class StaticScan(unittest.TestCase):
    def test_changelog_lists_current_version(self):
        v = json.loads((EXT / "manifest.json").read_text())["version"]
        self.assertRegex(v, r"^\d+\.\d+\.\d+$")
        self.assertIn(f"- {v}:", (EXT.parent / "CHANGELOG.md").read_text())

    def test_manifest_is_minimal(self):
        m = json.loads((EXT / "manifest.json").read_text())
        self.assertEqual(m["manifest_version"], 3)
        self.assertEqual(sorted(m["permissions"]), ["alarms", "scripting", "storage"])
        self.assertEqual(sorted(m["host_permissions"]), ["http://127.0.0.1:8777/*", "https://contributor.stock.adobe.com/en/portfolio",
                                                       "https://contributor.stock.adobe.com/en/uploads",
                                                       "https://contributor.stock.adobe.com/en/uploads/rejected",
                                                       "https://contributor.stock.adobe.com/en/uploads/review", "https://stock.adobe.com/*"])
        for k in ("content_scripts", "externally_connectable", "web_accessible_resources", "optional_permissions"):
            self.assertNotIn(k, m)

    def test_background_allows_only_exact_review_page(self):
        src = (EXT / "background.js").read_text()
        regex = re.search(r"const ALLOWED = (/.*?/);", src).group(1)
        js = 'const allowed = ' + regex + '; console.log(JSON.stringify([' + ','.join(json.dumps(u) for u in [
            "https://contributor.stock.adobe.com/en/uploads/review",
            "https://contributor.stock.adobe.com/en/uploads/review?x=1",
            "https://contributor.stock.adobe.com/en/uploads/review/submit"]) + '].map(u => allowed.test(u))));'
        if not shutil.which("node"):
            self.skipTest("node not installed")
        result = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [True, False, False])

    def test_no_forbidden_apis(self):
        for f in EXT.glob("*.js"):
            src = f.read_text()
            for pat in FORBIDDEN_JS:
                if f.name == "options.js" and pat == r"\.value\s*=":  # its own settings input, not a page
                    continue
                if f.name == "meta.js" and pat in (r"\.click\(", "dispatchEvent"):  # guarded click + the CSV dialog's file input, see tests below
                    continue
                if f.name == "pager.js" and pat == r"\.click\(":  # one guarded page-number click, see test below
                    continue
                if f.name == "stage.js" and pat == "dispatchEvent":  # the one place that hands the page's drop zone its files
                    continue
                self.assertIsNone(re.search(pat, src), f"{f.name} uses {pat}")

    def test_fetch_only_to_bridge(self):
        for f in EXT.glob("*.js"):
            for m in re.finditer(r"fetch\(([^,)]*)", f.read_text()):
                if m.group(1) == "`/en/content/${id}/history`":  # the one same-origin read, see test below
                    self.assertEqual(f.name, "extract.js")
                    continue
                self.assertIn("BRIDGE", m.group(1), f"{f.name}: {m.group(0)}")

    def test_history_read_is_get_only_digits_only_and_keeps_cause_fields(self):
        src = (EXT / "extract.js").read_text()
        self.assertEqual(len(re.findall(r"fetch\(", src)), 1)
        self.assertIn('{ method: "GET" }', src)
        self.assertIn("!Number.isInteger(id) || id <= 0", src)
        self.assertNotIn("email", src)
        self.assertIn(r"uploads\/rejected", (EXT / "background.js").read_text())

    def test_dashboard_button_opens_only_bridge_links(self):
        src = (EXT / "background.js").read_text()
        self.assertIn("chrome.action.onClicked", src)
        self.assertIn("url.startsWith(`${BRIDGE}/dashboard?t=`)", src)

    def test_stage_js_never_clicks_submits_or_fetches_and_only_drops_files_on_the_drop_zone(self):
        src = (EXT / "stage.js").read_text()
        for pat in (r"\.click\(", r"\.submit\(", r"fetch\(", r"XMLHttpRequest", r"\.requestSubmit", r"form\b.*\.submit"):
            self.assertIsNone(re.search(pat, src), pat)
        self.assertEqual(len(re.findall(r"dispatchEvent\(", src)), 1)
        self.assertIn('["dragenter", "dragover", "drop"]', src)
        self.assertNotIn("textContent =", src)
        self.assertNotIn("innerText =", src)

    def test_stage_is_gated_by_job_kind_and_checks_sha_before_the_page_sees_a_file(self):
        bg = (EXT / "background.js").read_text()
        self.assertIn('job.kind === "upload_stage" ? await stageFiles', bg)
        self.assertLess(bg.index("sha256Hex(buf)) !== f.sha256"), bg.index("batch.push("))
        self.assertIn("/v1/file?job=", bg)

    def test_combined_stage_checks_empty_new_before_fetching_files(self):
        bg = (EXT / "background.js").read_text()
        guard = bg.index('if (job.require_empty && out.before.all_count !== 0)')
        self.assertLess(guard, bg.index('const r = await fetch', guard))
        self.assertIn('out.error = "new_not_empty"', bg[guard:guard + 150])

    def test_bridge_port_matches_config(self):
        cfg = json.loads((ROOT / "config" / "stock_analytics.json").read_text())
        self.assertIn(f"127.0.0.1:{cfg['bridge']['port']}", (EXT / "background.js").read_text())


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ExtractTests(unittest.TestCase):
    def run_extract(self, kind, dom):
        js = f"""
        const dom = {json.dumps(dom)};
        const cardEls = (dom.cards || []).map(c => ({{querySelector: (q) => q === "img" ? {{src: c.src}} : {{textContent: c.dl}}}}));
        global.document = {{
          title: dom.title || "", body: {{innerText: dom.text || ""}},
          querySelector: (s) => /overview-downloads/.test(s) ? {{textContent: "3"}} : /overview-earnings/.test(s) ? {{textContent: "$1.50"}} :
                                /overview-select/.test(s) ? {{value: "total"}} : (s === "h1" && dom.h1) ? {{innerText: dom.h1}} : (/captcha/i.test(s) && dom.captcha_el ? {{}} : null),
          scripts: (dom.scripts || []).map(t => ({{textContent: t}})),
          getElementById: (id) => (id === "image-detail-json" && dom.json) ? {{textContent: JSON.stringify(dom.json)}} : null,
          querySelectorAll: (s) => s.includes("portfolio-single-asset-wrapper") ? cardEls : s.includes("similar-keyword-item") ? (dom.kw || []).map(t => ({{textContent: t}})) :
                                   s === "button, a" ? (dom.btn || []).map(t => ({{textContent: t}})) : []
        }};
        global.location = {{href: dom.href, hostname: "stock.adobe.com", pathname: dom.path}};
        global.performance = {{getEntriesByType: () => [{{responseStatus: dom.status || 200}}]}};
        const {{intelExtract}} = require({json.dumps(str(EXT / "extract.js"))});
        process.stdout.write(JSON.stringify(intelExtract({json.dumps(kind)})));
        """
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_search_page(self):
        j = {"2": {"order_key": 2, "content_id": 22, "title": "b", "creator_id": 9, "is_gentech": True, "category": {"name": "c"}},
             "1": {"order_key": 1, "content_id": 11, "title": "a", "creator_id": 8, "is_gentech": False}}
        r = self.run_extract("search", {"h1": "91,325 results for x", "json": j, "href": "https://stock.adobe.com/search?k=x", "path": "/search"})
        self.assertEqual([x["asset_id"] for x in r["rows"]], [11, 22])
        self.assertEqual(r["results_text"], "91,325 results for x")
        self.assertIsNone(r["page_state"])

    def test_captcha_and_restricted_detected(self):
        r = self.run_extract("search", {"text": "Please verify you are human", "href": "https://stock.adobe.com/search?k=x", "path": "/search"})
        self.assertEqual(r["page_state"], "captcha")
        r = self.run_extract("search", {"text": "Access is temporarily restricted", "href": "https://stock.adobe.com/search?k=x", "path": "/search"})
        self.assertEqual(r["page_state"], "restricted")

    def test_http_status_reported(self):
        r = self.run_extract("search", {"href": "https://stock.adobe.com/search?k=x", "path": "/search", "status": 429})
        self.assertEqual(r["http_status"], 429)

    def test_portfolio_page(self):
        r = self.run_extract("portfolio", {"text": "All(125) Sort by Downloads", "href": "https://contributor.stock.adobe.com/en/portfolio",
                                           "path": "/en/portfolio",
                                           "cards": [{"src": "https://example.invalid/220_F_1234567890_abc.jpg", "dl": "1"},
                                                     {"src": "https://x/220_F_5_k.jpg", "dl": "-"}]})
        self.assertEqual(r["cards"], [
            {"asset_id": 1234567890, "downloads_text": "1", "thumb_url": "https://example.invalid/220_F_1234567890_abc.jpg"},
            {"asset_id": 5, "downloads_text": "-", "thumb_url": "https://x/220_F_5_k.jpg"}])
        self.assertEqual((r["overview_downloads_text"], r["all_count_text"], r["time_frame"]), ("3", "All(125)", "total"))

    def test_probe_page_dumps_structure_without_interacting(self):
        r = self.run_extract("probe", {"text": "Rejected(3)\nApproved (10)\nQuality issues\nhello", "href": "https://contributor.stock.adobe.com/en/uploads",
                                       "path": "/en/uploads"})
        self.assertIn("Rejected(3)", r["tab_labels"])
        self.assertIn("Quality issues", r["status_lines"])
        self.assertEqual(r["asset_ids"], [])

    def test_stage_functions_drop_files_on_the_zone_in_three_events_and_read_the_all_count(self):
        js = f"""
        const events = [];
        const zone = {{dispatchEvent: (e) => {{ events.push(e.type + ":" + e.bubbles + ":" + e.dataTransfer.files.length); return true; }}}};
        const button = {{textContent: " Submit 0 files "}};
        class DT {{ constructor() {{ this.items = {{add: (f) => this.list.push(f)}}; this.list = []; }} get files() {{ return this.list; }} }}
        global.DataTransfer = DT;
        global.File = class {{ constructor(parts, name, opts) {{ this.name = name; this.size = parts[0].length; this.type = opts.type; }} }};
        global.DragEvent = class {{ constructor(t, o) {{ this.type = t; this.bubbles = o.bubbles; this.dataTransfer = o.dataTransfer; this.file = o.dataTransfer.files[0]; }} }};
        global.document = {{
          body: {{innerText: "Submit 0 files\\nFile types: All (3)\\ntiles a.jpg only\\n1 Upload Remaining..."}},
          querySelector: (s) => s === ".uploader__drop" ? zone : s.includes("submit-moderation-button") ? button : null
        }};
        const {{intelStageBatch, intelStageState}} = require({json.dumps(str(EXT / "stage.js"))});
        const b64 = Buffer.from("hello").toString("base64");
        const r = intelStageBatch([{{name: "a.jpg", type: "image/jpeg", b64}}]);
        const st = intelStageState(["a.jpg", "b.jpg"]);
        process.stdout.write(JSON.stringify({{r, events, st}}));
        """
        out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(out["r"], {"input_found": True, "assigned": 1})
        self.assertEqual(out["events"], ["dragenter:true:1", "dragover:true:1", "drop:true:1"])
        self.assertEqual(out["st"], {"input_found": True, "all_count": 3, "uploading": True, "submission_limit": False,
                                     "submission_blocked": False,
                                     "submit_text": "Submit 0 files", "names_seen": ["a.jpg"]})

    def test_stage_detects_submission_limit_without_clicking(self):
        js = f"""
        global.document = {{
          body: {{innerText: "Submission limit reached\\nFile types: All (47)"}},
          querySelector: (s) => s === ".uploader__drop" ? {{}} : null
        }};
        const {{intelStageState}} = require({json.dumps(str(EXT / "stage.js"))});
        process.stdout.write(JSON.stringify(intelStageState([])));
        """
        out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
        self.assertTrue(out["submission_limit"])

    def test_stage_detects_partial_submission_banner_without_guessing_limit_kind(self):
        js = f"""
        global.document = {{
          body: {{innerText: "Not all of your contents could be submitted for moderation.\\nFile types: All (51)"}},
          querySelector: (s) => s === ".uploader__drop" ? {{}} : null
        }};
        const {{intelStageState}} = require({json.dumps(str(EXT / "stage.js"))});
        process.stdout.write(JSON.stringify(intelStageState([])));
        """
        out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
        self.assertTrue(out["submission_blocked"])
        self.assertFalse(out["submission_limit"])

    def test_meta_js_has_one_guarded_click_and_never_submits_or_fetches(self):
        src = (EXT / "meta.js").read_text()
        for pat in (r"\.submit\(", r"\.requestSubmit", r"fetch\(", r"XMLHttpRequest", r"\.value\s*=", r"\beval\("):
            self.assertIsNone(re.search(pat, src), pat)
        self.assertEqual(len(re.findall(r"\.click\(", src)), 1)
        self.assertEqual(len(re.findall(r"dispatchEvent\(", src)), 2)
        guard = src[src.index("function intelMetaClick"):src.index("function intelMetaState")]
        self.assertLess(guard.index("submit-moderation-button"), guard.index("el.click()"))
        self.assertLess(guard.index("INTEL_META_DENY.test(dt)"), guard.index("el.click()"))
        for deny in ("submit", "delete", "remove", "trash"):
            self.assertIn(deny, src[:src.index("function intelMetaClick")])
        self.assertNotIn("asset-sidebar-delete-asset-button", src[src.index("INTEL_META_ALLOWED_DT"):src.index("function intelMetaClick")])

    def test_pager_js_has_one_guarded_click_and_never_fetches(self):
        src = (EXT / "pager.js").read_text()
        for pat in (r"\.submit\(", r"\.requestSubmit", r"fetch\(", r"XMLHttpRequest", r"\.value\s*=", r"\beval\(", "dispatchEvent"):
            self.assertIsNone(re.search(pat, src), pat)
        self.assertEqual(len(re.findall(r"\.click\(", src)), 1)
        go = src[src.index("function intelPagerGo"):src.index("function intelPagerIds")]
        self.assertLess(go.index("INTEL_PAGER_DENY.test(label)"), go.index("el.click()"))
        self.assertLess(go.index("core-pagination") if "core-pagination" in go else go.index("intelPagerNav()"), go.index("el.click()"))
        for deny in ("submit", "delete", "remove", "trash", "save", "upload"):
            self.assertIn(deny, src[:src.index("function intelPagerNav")])
        bg = (EXT / "background.js").read_text()
        self.assertIn('job.kind === "portfolio" ? await readPortfolio', bg)
        self.assertLess(bg.index("async function readPortfolio"), bg.index("async function runJob"))

    def run_pager(self, dom_js, body):
        js = f"""
        global.document = {dom_js};
        const m = require({json.dumps(str(EXT / "pager.js"))});
        process.stdout.write(JSON.stringify({body}));
        """
        return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)

    def test_pager_clicks_only_numeric_controls_inside_the_pagination_block(self):
        dom = """{ querySelector: (s) => s === '[data-t="core-pagination"]' ? nav : null }"""
        out = self.run_pager("{}", f"""(() => {{
          global.clicks = [];
          const mk = (text, dt, aria) => ({{textContent: text, getAttribute: (k) => k === 'data-t' ? dt : k === 'aria-label' ? aria : null, click() {{ clicks.push(text); }}}});
          const ctrls = [mk('1'), mk('2'), mk('Next'), mk('3', 'submit-page')];
          const nav = {{ querySelectorAll: () => ctrls }};
          global.document = {dom};
          return {{pages: m.intelPagerPages(), go2: m.intelPagerGo(2), next: m.intelPagerGo(0), nextText: m.intelPagerGo(500),
                  denied: m.intelPagerGo(3), clicks}};
        }})()""")
        self.assertEqual(out["pages"], {"found": True, "pages": [1, 2, 3]})
        self.assertEqual(out["go2"], {"clicked": True})
        self.assertEqual(out["next"]["clicked"], False)
        self.assertEqual(out["nextText"]["clicked"], False)
        self.assertEqual(out["denied"], {"clicked": False, "reason": "denied_control"})
        self.assertEqual(out["clicks"], ["2"])

    def test_metadata_is_gated_by_job_kind_and_checks_sha_before_the_page_sees_the_csv(self):
        bg = (EXT / "background.js").read_text()
        self.assertIn('job.kind === "upload_metadata" ? await metaFlow', bg)
        flow = bg[bg.index("async function metaFlow"):]
        self.assertLess(flow.index("sha256Hex(buf)) !== f.sha256"), flow.index("intelMetaSetCsv"))
        self.assertLess(flow.index("intelMetaSetCsv"), flow.index("intelMetaSelectAll"))
        self.assertNotIn("submit-moderation", bg)

    def run_meta(self, dom_js, body):
        js = f"""
        global.document = {dom_js};
        const m = require({json.dumps(str(EXT / "meta.js"))});
        process.stdout.write(JSON.stringify({body}));
        """
        return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)

    def test_meta_click_guard_refuses_submit_delete_and_unlisted_controls(self):
        mk = "(dt, text, aria, inside) => ({getAttribute: (k) => k === 'data-t' ? dt : k === 'aria-label' ? aria : null, textContent: text, closest: () => inside ? {} : null, click() { clicks.push(dt); }})"
        out = self.run_meta("{}", f"""(() => {{
          global.clicks = [];
          const mk = {mk};
          return {{
            submit: m.intelMetaClick(mk("submit-moderation-button", "Submit 16 files", "", false), "save"),
            inside_submit: m.intelMetaClick(mk("save-work", "Save", "", true), "save"),
            delete: m.intelMetaClick(mk("asset-sidebar-delete-asset-button", "x", "", false), "save"),
            aria_delete: m.intelMetaClick(mk("save-work", "x", "Delete files", false), "save"),
            text_submit: m.intelMetaClick(mk("save-work", "Submit", "", false), "save"),
            unlisted: m.intelMetaClick(mk("something-else", "Hi", "", false), "csv"),
            save: m.intelMetaClick(mk("save-work", "Save work", "", false), "save"),
            clicks }};
        }})()""")
        self.assertEqual(out, {"submit": False, "inside_submit": False, "delete": False, "aria_delete": False, "text_submit": False,
                               "unlisted": False, "save": True, "clicks": ["save-work"]})

    def test_meta_state_reads_counts_and_flags(self):
        dom = """{body: {innerText: "File types: All (16)\\nChanges made below will affect 16 selected files"},
          querySelector: (s) => s.includes("submit-moderation-button") ? {textContent: "Submit 16 files"}
            : s.includes("assets-content-grid") ? {children: [{innerText: "12\\nkeywords"}, {innerText: "3"}]}
            : s.includes("content-tagger-checkbox") ? {checked: true} : s.includes("reusable-checkbox") ? {checked: false}
            : s.includes("save-work") ? {disabled: false} : null,
          querySelectorAll: () => [{checked: true, closest: () => ({innerText: "People and Property are fictional"})}]}"""
        out = self.run_meta(dom, "m.intelMetaState()")
        self.assertEqual((out["all_count"], out["submit_count"], out["selected"], out["keyword_counts"]), (16, 16, 16, [12, 3]))
        self.assertEqual((out["ai_checked"], out["include_checked"], out["save_enabled"], out["csv_modal"], out["fictional_checked"]), (True, False, True, False, True))

    def test_meta_ticks_the_fictional_box_only_when_unchecked_and_flagged(self):
        dom = """(() => {
          global.clicks = [];
          const box = (label, checked, dt) => ({checked, getAttribute: (k) => k === 'data-t' ? dt : null, textContent: '', closest: (s) => s === 'label' ? {innerText: label} : null, click() { this.checked = !this.checked; clicks.push(label); }});
          global.fic = box("People and Property are fictional", false, "");
          global.ai = box("Created using generative AI tools", true, "content-tagger-checkbox");
          return {querySelectorAll: (s) => s === 'input[type="checkbox"]' ? [ai, fic] : [], querySelector: (s) => s.includes("content-tagger-checkbox") ? ai : null}; })()"""
        out = self.run_meta(dom, """(() => { const a = m.intelMetaApplyFlags({generative_ai: true, people_property: "no", people_property_fictional: true, include_in_submission: false});
          const b = m.intelMetaApplyFlags({generative_ai: true, people_property: "no", people_property_fictional: true, include_in_submission: false});
          return {a: a.fictional_checked, b: b.fictional_checked, clicks, state: m.intelMetaState().fictional_checked}; })()""")
        self.assertEqual(out, {"a": True, "b": True, "clicks": ["People and Property are fictional"], "state": True})

    def test_meta_set_csv_assigns_the_file_to_the_dialog_input(self):
        dom = """(() => { const input = {files: null, ev: [], dispatchEvent(e) { this.ev.push(e.type); return true; }};
          global.input = input;
          global.DataTransfer = class { constructor() { this.list = []; this.items = {add: (f) => this.list.push(f)}; } get files() { return this.list; } };
          global.File = class { constructor(p, n, o) { this.name = n; this.type = o.type; this.size = p[0].length; } };
          global.Event = class { constructor(t) { this.type = t; } };
          return {querySelector: (s) => s.includes("csv-modal") ? input : null}; })()"""
        out = self.run_meta(dom, """(() => { const r = m.intelMetaSetCsv({name: "a.csv", b64: Buffer.from("x,y").toString("base64")});
          return {r, ev: input.ev, name: input.files[0].name, type: input.files[0].type, size: input.files[0].size}; })()""")
        self.assertEqual(out, {"r": {"input_found": True, "assigned": 1}, "ev": ["input", "change"], "name": "a.csv", "type": "text/csv", "size": 3})

    def test_stage_without_an_input_reports_it(self):
        js = f"""
        global.document = {{body: {{innerText: ""}}, querySelector: () => null}};
        const {{intelStageBatch}} = require({json.dumps(str(EXT / "stage.js"))});
        process.stdout.write(JSON.stringify(intelStageBatch([])));
        """
        out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(out, {"input_found": False, "assigned": 0})

    def run_node(self, body):
        return subprocess.run(["node", "-e", body], capture_output=True, text=True, check=True).stdout

    def test_outcomes_page_keeps_only_list_fields(self):
        import urllib.parse
        ctx = {"csrfToken": "SECRET", "reduxState": {"user": {"firstName": "X"}, "content": [
            {"id": 11, "originalName": "a.jpg", "status": "state_refused", "creationDate": 5, "width": 4200, "height": 2800,
             "title": "t", "keywords": ["k"], "thumbnailUrl": "https://x/y?q=1", "moderationHistory": {"email": "mod@example.com"}}]}}
        src = 'window.__react_context__ = "' + urllib.parse.quote(json.dumps(ctx), safe="") + '";'
        r = self.run_extract("outcomes", {"text": "", "href": "https://contributor.stock.adobe.com/en/uploads/rejected",
                                          "path": "/en/uploads/rejected", "scripts": [src]})
        self.assertTrue(r["ctx_found"])
        self.assertEqual(r["items"], [{"asset_id": 11, "original_name": "a.jpg", "status": "state_refused",
                                       "created_ms": 5, "width": 4200, "height": 2800}])
        blob = json.dumps(r)
        for secret in ("SECRET", "mod@example.com", "firstName"):
            self.assertNotIn(secret, blob)

    def test_portfolio_page_records_names_from_embedded_list_only(self):
        import urllib.parse
        ctx = {"csrfToken": "SECRET", "reduxState": {"contentMeta": {"contentTotal": 125}, "content": [
            {"id": 11, "originalName": "a.jpg", "status": "state_online", "creationDate": 5, "nb_downloads": 1,
             "thumbnailUrl": "https://x/y?q=1"}]}}
        src = 'window.__react_context__ = "' + urllib.parse.quote(json.dumps(ctx), safe="") + '";'
        r = self.run_extract("portfolio", {"text": "All(125)", "href": "https://contributor.stock.adobe.com/en/portfolio",
                                           "path": "/en/portfolio", "cards": [], "scripts": [src]})
        self.assertEqual(r["named"], [{"asset_id": 11, "original_name": "a.jpg", "status": "state_online", "created_ms": 5}])
        self.assertEqual(r["named_total"], 125)
        self.assertNotIn("SECRET", json.dumps(r))

    def test_outcomes_page_without_embedded_list_is_not_found(self):
        r = self.run_extract("outcomes", {"text": "", "href": "https://contributor.stock.adobe.com/en/uploads/rejected",
                                          "path": "/en/uploads/rejected", "scripts": []})
        self.assertFalse(r["ctx_found"])

    def test_uploads_probe_keeps_identity_without_private_context(self):
        import urllib.parse
        ctx = {"csrfToken": "SECRET", "reduxState": {"contentMeta": {"contentTotal": 2}, "content": [
            {"id": 11, "originalName": "a.jpg", "status": "state_new", "title": "private title"}]}}
        src = 'window.__react_context__ = "' + urllib.parse.quote(json.dumps(ctx), safe="") + '";'
        r = self.run_extract("probe", {"href": "https://contributor.stock.adobe.com/en/uploads",
                                       "path": "/en/uploads", "scripts": [src]})
        self.assertEqual(r["named"], [{"asset_id": 11, "original_name": "a.jpg", "status": "state_new"}])
        self.assertEqual(r["named_total"], 2)
        for secret in ("SECRET", "private title", "csrfToken"):
            self.assertNotIn(secret, json.dumps(r))

    def test_review_probe_retains_waiting_status_and_unknown_list(self):
        import urllib.parse
        ctx = {"reduxState": {"contentMeta": {"contentTotal": 1}, "content": [
            {"id": 22, "originalName": "review.jpg", "status": "state_waiting_validation"}]}}
        src = 'window.__react_context__ = "' + urllib.parse.quote(json.dumps(ctx), safe="") + '";'
        page = {"href": "https://contributor.stock.adobe.com/en/uploads/review", "path": "/en/uploads/review"}
        result = self.run_extract("probe", {**page, "scripts": [src]})
        self.assertEqual(result["named"], [{"asset_id": 22, "original_name": "review.jpg", "status": "state_waiting_validation"}])
        self.assertEqual(result["named_total"], 1)
        unknown = self.run_extract("probe", {**page, "scripts": []})
        self.assertEqual(unknown["named"], [])
        self.assertIsNone(unknown.get("named_total"))  # unknown is not a confirmed empty list

    def test_history_reads_only_cause_fields_and_stops_on_429(self):
        out = self.run_node("""
        const calls = [];
        global.fetch = async (u, o) => { calls.push([u, o.method]); return u.includes("/22/") ? {status: 429, ok: false} :
          {status: 200, ok: true, json: async () => ({cause: 9, causeLabel: "Tech problems", status: 5, statusLabel: "Refused", email: "mod@example.com"})}; };
        global.setTimeout = (f) => { f(); };
        const {intelHistory} = require(%s);
        intelHistory([11, -3, 22, 33]).then((r) => process.stdout.write(JSON.stringify({r, calls})));
        """ % json.dumps(str(EXT / "extract.js")))
        res = json.loads(out)
        self.assertEqual(res["calls"], [["/en/content/11/history", "GET"], ["/en/content/22/history", "GET"]])
        self.assertEqual(res["r"]["11"], {"cause": 9, "cause_label": "Tech problems", "status": 5, "status_label": "Refused"})
        self.assertEqual(res["r"]["__stop"], 429)
        self.assertNotIn("mod@example.com", out)

    def test_asset_page(self):
        r = self.run_extract("asset", {"h1": "title", "kw": ["cafes", "tea", "tea"], "btn": ["Show all (28)"],
                                       "href": "https://stock.adobe.com/th/images/x/900000007", "path": "/th/images/x/900000007"})
        self.assertEqual((r["asset_id"], r["keywords"], r["keywords_total_text"]), (900000007, ["cafes", "tea"], "Show all (28)"))


if __name__ == "__main__":
    unittest.main()
