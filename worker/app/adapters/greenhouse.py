from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from app.adapters.base import BaseAdapter
from app.adapters.field_matching import (
    fingerprint_options,
    is_consent_checkbox,
    is_greenhouse_url,
    is_unknown_question,
    match_answer_to_option,
    normalize_label,
    profile_key_for_label,
)
from app.profile import get_profile_dict


class GreenhouseAdapter(BaseAdapter):
    platform = "greenhouse"

    def __init__(self, profile: dict | None = None) -> None:
        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.profile: dict = profile if profile is not None else get_profile_dict()
        self._scanned_fields: list[dict[str, Any]] = []
        self.fill_log: list[dict] = []  # {"label", "value", "source": "profile"|"template"|"ui"}

    # ── Browser lifecycle ─────────────────────────────────────────────────────

    def _ensure_browser(self) -> None:
        if self.page is not None:
            return
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=False)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def close(self) -> None:
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        finally:
            self.context = None
            self.browser = None
            self.page = None
            self.playwright = None

    # ── Navigation ────────────────────────────────────────────────────────────

    def open_application(self, job: dict) -> None:
        self._ensure_browser()
        assert self.page is not None

        url = job["source_url"]
        if not is_greenhouse_url(url):
            print(f"[warn] URL does not look like a canonical Greenhouse job board URL: {url}")

        self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        self.page.wait_for_timeout(2000)

        for selector in ["form", "#application_form", ".application", ".main_fields"]:
            try:
                self.page.locator(selector).first.wait_for(timeout=3000)
                break
            except Exception:
                pass

        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.page.wait_for_timeout(1500)
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.wait_for_timeout(500)

        self._scanned_fields = self._scan_page_fields()

    # ── DOM scanning ──────────────────────────────────────────────────────────

    def _label_for_element(self, el) -> str:
        assert self.page is not None

        try:
            el_id = el.get_attribute("id")
            if el_id:
                label = self.page.locator(f"label[for='{el_id}']").first
                if label.count() > 0:
                    text = label.inner_text().strip()
                    if text:
                        return text
        except Exception:
            pass

        try:
            parent = el.locator("xpath=ancestor::label[1]").first
            if parent.count() > 0:
                text = parent.inner_text().strip()
                if text:
                    return text
        except Exception:
            pass

        try:
            container = el.locator(
                "xpath=ancestor::*[contains(@class,'field') or contains(@class,'question')][1]"
            ).first
            if container.count() > 0:
                labels = container.locator("label")
                if labels.count() > 0:
                    text = labels.first.inner_text().strip()
                    if text:
                        return text
        except Exception:
            pass

        try:
            aria = el.get_attribute("aria-label")
            if aria and aria.strip():
                return aria.strip()
        except Exception:
            pass

        try:
            ph = el.get_attribute("placeholder")
            if ph and ph.strip():
                return ph.strip()
        except Exception:
            pass

        return ""

    def _options_for_element(self, el, tag: str, input_type: str | None) -> list[str]:
        options: list[str] = []

        if tag == "select":
            try:
                opts = el.locator("option")
                for i in range(opts.count()):
                    txt = opts.nth(i).inner_text().strip()
                    if txt:
                        options.append(txt)
            except Exception:
                pass
            return options

        if input_type in {"radio", "checkbox"}:
            try:
                name = el.get_attribute("name")
                if name and self.page:
                    grouped = self.page.locator(f'input[name="{name}"]')
                    for i in range(grouped.count()):
                        candidate = grouped.nth(i)
                        lbl = self._label_for_element(candidate)
                        if lbl:
                            options.append(lbl)
                        else:
                            val = candidate.get_attribute("value")
                            if val:
                                options.append(val)
            except Exception:
                pass

        seen: set[str] = set()
        return [o for o in options if not (o in seen or seen.add(o))]  # type: ignore[func-returns-value]

    def _collect_react_select_options(self, el) -> list[str]:
        """Open a React Select dropdown and collect its options, then close it."""
        assert self.page is not None
        try:
            if not el.is_visible(timeout=500):
                return []
            container = el.locator(
                "xpath=ancestor::*[contains(@class,'select__control') or contains(@class,'select__container')][1]"
            ).first
            target = container if container.count() > 0 else el
            target.click()
            self.page.wait_for_timeout(400)

            opts_loc = self.page.locator("[role='listbox']:visible [role='option']")
            options = []
            for i in range(min(opts_loc.count(), 200)):
                text = opts_loc.nth(i).inner_text().strip()
                if text:
                    options.append(text)

            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(200)
            return options
        except Exception:
            return []

    def _is_react_select_input(self, el) -> bool:
        """Return True if this input is the internal field of a React Select or similar combobox."""
        try:
            cls = el.get_attribute("class") or ""
            if "select__input" in cls or "Select__input" in cls:
                return True
        except Exception:
            pass
        try:
            role = el.get_attribute("role") or ""
            popup = el.get_attribute("aria-haspopup") or ""
            aria_auto = el.get_attribute("aria-autocomplete") or ""
            if role == "combobox" or popup in {"listbox", "true"} or aria_auto == "list":
                return True
        except Exception:
            pass
        try:
            ancestor = el.locator(
                "xpath=ancestor::*["
                "contains(@class,'select__') or contains(@class,'Select__') or "
                "contains(@class,'-select__') or contains(@class,'select-container') or "
                "contains(@class,'SelectContainer')][1]"
            ).first
            if ancestor.count() > 0:
                return True
        except Exception:
            pass
        return False

    def _scroll_to_load(self) -> None:
        """Scroll slowly to the bottom so lazy-loaded sections (e.g. EEO) render."""
        assert self.page is not None
        try:
            self.page.evaluate(
                """() => {
                    return new Promise(resolve => {
                        let y = 0;
                        const step = () => {
                            window.scrollBy(0, 400);
                            y += 400;
                            if (y < document.body.scrollHeight) {
                                setTimeout(step, 80);
                            } else {
                                window.scrollTo(0, 0);
                                resolve();
                            }
                        };
                        step();
                    });
                }"""
            )
            self.page.wait_for_timeout(600)
        except Exception:
            pass

    def _scan_page_fields(self) -> list[dict[str, Any]]:
        assert self.page is not None
        self._scroll_to_load()
        fields: list[dict[str, Any]] = []

        # --- Pass 1: visible inputs and textareas ---
        for i, selector in enumerate(["input", "textarea"]):
            loc = self.page.locator(selector)
            for j in range(loc.count()):
                el = loc.nth(j)
                try:
                    tag = el.evaluate("n => n.tagName.toLowerCase()")
                except Exception:
                    continue
                try:
                    input_type = el.get_attribute("type")
                except Exception:
                    input_type = None
                if input_type in {"hidden", "submit", "button", "file"}:
                    continue
                try:
                    if not el.is_visible():
                        continue
                except Exception:
                    pass
                try:
                    if el.is_disabled():
                        continue
                except Exception:
                    pass
                label = self._label_for_element(el).strip()
                if not label:
                    continue
                try:
                    required = (
                        el.get_attribute("required") is not None
                        or el.get_attribute("aria-required") == "true"
                    )
                except Exception:
                    required = False

                is_react_select = self._is_react_select_input(el)
                options = (
                    self._collect_react_select_options(el)
                    if is_react_select
                    else self._options_for_element(el, tag, input_type)
                )
                fields.append({
                    "index": i * 10000 + j,
                    "tag": tag,
                    "input_type": input_type,
                    "is_react_select": is_react_select,
                    "label": label,
                    "required": required,
                    "options": options,
                    "locator": el,
                })

        # --- Pass 2: native <select> elements —
        #     Use looser visibility check: some ATSes hide selects with opacity/transform
        #     while showing a custom widget on top. We still want their options.
        sel_loc = self.page.locator("select")
        for j in range(sel_loc.count()):
            el = sel_loc.nth(j)
            try:
                # Only skip if truly removed from layout (display:none / visibility:hidden)
                hidden = el.evaluate(
                    "n => { const s = getComputedStyle(n); "
                    "return s.display === 'none' || s.visibility === 'hidden'; }"
                )
                if hidden:
                    continue
            except Exception:
                continue
            try:
                if el.is_disabled():
                    continue
            except Exception:
                pass
            label = self._label_for_element(el).strip()
            if not label:
                continue
            try:
                required = (
                    el.get_attribute("required") is not None
                    or el.get_attribute("aria-required") == "true"
                )
            except Exception:
                required = False
            options = self._options_for_element(el, "select", None)
            fields.append({
                "index": 20000 + j,
                "tag": "select",
                "input_type": None,
                "is_react_select": False,
                "label": label,
                "required": required,
                "options": options,
                "locator": el,
            })

        # Deduplicate by normalized label — prefer entry with more options / richer type
        seen: dict[str, dict] = {}
        for f in fields:
            key = normalize_label(f["label"])
            if key not in seen:
                seen[key] = f
            else:
                existing = seen[key]
                # Replace if new entry has more options, or existing is plain text with no options
                if len(f["options"]) > len(existing["options"]):
                    seen[key] = f
                elif len(f["options"]) == len(existing["options"]) and f.get("is_react_select"):
                    seen[key] = f

        return list(seen.values())

    # ── Classification ────────────────────────────────────────────────────────

    def _effective_type(self, field: dict) -> str:
        if field.get("is_react_select"):
            return "react_select"
        tag = field["tag"]
        input_type = field["input_type"]
        return tag if tag in {"textarea", "select"} else (input_type or tag)

    def classify_fields(self) -> dict[str, list[dict[str, Any]]]:
        known: list[dict] = []
        consent: list[dict] = []
        block: list[dict] = []

        for field in self._scanned_fields:
            label = field["label"]
            etype = self._effective_type(field)

            profile_key = profile_key_for_label(label)
            if profile_key:
                field["profile_key"] = profile_key
                field["profile_value"] = self.profile.get(profile_key)
                if field["profile_value"]:
                    known.append(field)
                else:
                    block.append(field)
                continue

            if is_consent_checkbox(label, etype):
                consent.append(field)
                continue

            if is_unknown_question(label, etype):
                block.append(field)

        return {"known": known, "consent": consent, "block": block}

    # ── Low-level fill helpers ────────────────────────────────────────────────

    def _fill_text(self, el, value: str) -> None:
        """Fill text and fire React synthetic events."""
        el.fill(value)
        el.dispatch_event("input")
        el.dispatch_event("change")

    def _fill_radio(self, el, answer: str) -> bool:
        assert self.page is not None
        try:
            name = el.get_attribute("name")
            if not name:
                return False
            radios = self.page.locator(f'input[name="{name}"]')
            for i in range(radios.count()):
                radio = radios.nth(i)
                lbl = self._label_for_element(radio)
                if normalize_label(lbl) == normalize_label(answer):
                    radio.click()
                    return True
            return False
        except Exception:
            return False

    # ── React Select helper ───────────────────────────────────────────────────

    def _select_react_option(self, el, target_text: str) -> bool:
        assert self.page is not None
        try:
            if not el.is_visible(timeout=500):
                return False
        except Exception:
            return False
        try:
            container = el.locator(
                "xpath=ancestor::*[contains(@class,'select__control') or contains(@class,'select__container')][1]"
            ).first
            if container.count() == 0:
                container = el
            container.click()
            self.page.wait_for_timeout(400)

            menu = el.locator(
                "xpath=ancestor::*[contains(@class,'select__container') or contains(@class,'select__')][1]"
                "//*[@role='listbox' or contains(@class,'select__menu')]"
            ).first

            if menu.count() > 0:
                options = menu.locator("[role='option']")
            else:
                options = self.page.locator("[role='listbox']:visible [role='option']")

            target_lower = target_text.lower().strip()
            for i in range(options.count()):
                opt = options.nth(i)
                text = (opt.inner_text() or "").strip()
                if text.lower() == target_lower or target_lower in text.lower():
                    opt.click()
                    self.page.wait_for_timeout(200)
                    return True

            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(200)
            return False
        except Exception as e:
            print(f"  [warn]   react select failed: {e}")
            return False

    # ── Resume upload ─────────────────────────────────────────────────────────

    def _upload_resume(self) -> None:
        assert self.page is not None
        resume_path = self.profile.get("resume_path", "")
        if not resume_path:
            return

        file_inputs = self.page.locator('input[type="file"]')
        for i in range(file_inputs.count()):
            el = file_inputs.nth(i)
            try:
                is_resume = False
                for attr in ["name", "id", "aria-label", "accept"]:
                    val = (el.get_attribute(attr) or "").lower()
                    if any(kw in val for kw in ["resume", "cv"]):
                        is_resume = True
                        break
                if not is_resume:
                    try:
                        ancestor = el.locator(
                            "xpath=ancestor::*[self::div or self::label or self::fieldset or self::li][1]"
                        ).first
                        if ancestor.count() > 0:
                            text = ancestor.inner_text().lower()
                            if any(kw in text for kw in ["resume", "cv", "curriculum vitae"]):
                                if "cover" not in text:
                                    is_resume = True
                    except Exception:
                        pass
                if is_resume:
                    el.set_input_files(resume_path)
                    self.page.wait_for_timeout(500)
                    print(f"  [resume] uploaded {resume_path}")
                    return
            except Exception as e:
                print(f"  [warn]   resume upload failed: {e}")

    # ── Multi-page navigation ─────────────────────────────────────────────────

    def go_to_next_page(self) -> bool:
        """Click Next/Continue if present and wait for the new page. Returns True if navigated."""
        assert self.page is not None
        candidates = [
            "button:has-text('Next')",
            "button:has-text('Continue')",
            "button:has-text('Next Step')",
            "input[type='submit'][value*='Next' i]",
            "input[type='submit'][value*='Continue' i]",
            "a:has-text('Next')",
        ]
        for selector in candidates:
            try:
                btn = self.page.locator(selector).first
                if btn.count() > 0 and btn.is_visible(timeout=300):
                    btn.click()
                    self.page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    self.page.wait_for_timeout(1500)
                    self._scanned_fields = []  # force re-scan on next call
                    return True
            except Exception:
                continue
        return False

    # ── Filling ───────────────────────────────────────────────────────────────

    def fill_known_fields(self, job: dict) -> None:
        # Always rescan before filling — resume upload and other DOM changes
        # invalidate index-based locators, so we need fresh handles every time.
        self._upload_resume()
        self._scanned_fields = self._scan_page_fields()

        classified = self.classify_fields()
        print(f"\n[scan] known={len(classified['known'])}  consent={len(classified['consent'])}  block={len(classified['block'])}")

        for field in classified["known"]:
            label = field["label"]
            tag = field["tag"]
            input_type = field["input_type"]
            value = field.get("profile_value")
            el = field["locator"]
            if not value:
                continue
            try:
                filled_value = None
                if field.get("is_react_select"):
                    if self._select_react_option(el, str(value)):
                        print(f"  [fill]   {label!r} → {value!r} (react_select)")
                        filled_value = str(value)
                    else:
                        print(f"  [warn]   {label!r} no react select match for {value!r}")
                elif tag in {"input", "textarea"} and input_type not in {"radio", "checkbox"}:
                    self._fill_text(el, str(value))
                    print(f"  [fill]   {label!r} → {value!r}")
                    filled_value = str(value)
                elif tag == "select":
                    matched = match_answer_to_option(str(value), field.get("options", []))
                    if matched:
                        el.select_option(label=matched)
                        print(f"  [fill]   {label!r} → {matched!r} (select)")
                        filled_value = matched
                    else:
                        print(f"  [warn]   {label!r} no matching select option for {value!r}")
                elif input_type == "radio":
                    if self._fill_radio(el, str(value)):
                        print(f"  [fill]   {label!r} → {value!r} (radio)")
                        filled_value = str(value)
                    else:
                        print(f"  [warn]   {label!r} no radio option for {value!r}")
                elif input_type == "checkbox":
                    if str(value).lower() in {"yes", "true", "1"}:
                        el.check()
                    else:
                        el.uncheck()
                    print(f"  [fill]   {label!r} → {value!r} (checkbox)")
                    filled_value = str(value)
                if filled_value is not None:
                    self.fill_log.append({
                        "label": label,
                        "value": filled_value,
                        "source": "profile",
                        "field_type": self._effective_type(field),
                        "options": field.get("options", []),
                    })
            except Exception as e:
                print(f"  [warn]   failed to fill {label!r}: {e}")

        for field in classified["consent"]:
            try:
                field["locator"].check()
                print(f"  [consent] {field['label'][:60]!r} → checked")
            except Exception as e:
                print(f"  [warn]   consent check failed: {e}")

    # ── Unknown questions ─────────────────────────────────────────────────────

    def find_unknown_questions(self, job: dict) -> list[dict]:
        if not self._scanned_fields:
            self._scanned_fields = self._scan_page_fields()

        classified = self.classify_fields()

        result = []
        for f in classified["block"]:
            options = f.get("options", [])
            field_type = self._effective_type(f)
            result.append({
                "raw_text": f["label"],
                "normalized_text": normalize_label(f["label"]),
                "field_type": field_type,
                "field_label": f["label"],
                "page_url": job["source_url"],
                "dom_hint": f"field_index:{f['index']}",
                "options": options,
                "options_fingerprint": fingerprint_options(options) if options else None,
                "required": f.get("required", False),
            })
        return result

    def fill_from_template_answers(self, answers: list[dict]) -> None:
        assert self.page is not None
        for item in answers:
            label = item["field_label"]
            answer = item["answer"]

            matched_field = None
            for f in self._scanned_fields:
                if normalize_label(f["label"]) == normalize_label(label):
                    matched_field = f
                    break

            if not matched_field:
                print(f"  [template] could not re-find field {label!r} — skipping")
                continue

            el = matched_field["locator"]
            tag = matched_field["tag"]
            input_type = matched_field["input_type"]

            source = item.get("_source", "template")  # "template" or "ui"
            try:
                filled_value = None
                if matched_field.get("is_react_select"):
                    ok = self._select_react_option(el, str(answer))
                    print(f"  [{source}] {label!r} → {answer!r} (react_select)" if ok else
                          f"  [{source}] {label!r} no react select match for {answer!r}")
                    if ok:
                        filled_value = str(answer)
                elif tag in {"input", "textarea"} and input_type not in {"radio", "checkbox"}:
                    self._fill_text(el, str(answer))
                    print(f"  [{source}] {label!r} → {answer!r}")
                    filled_value = str(answer)
                elif tag == "select":
                    matched_opt = match_answer_to_option(str(answer), matched_field.get("options", []))
                    if matched_opt:
                        el.select_option(label=matched_opt)
                        print(f"  [{source}] {label!r} → {matched_opt!r} (select)")
                        filled_value = matched_opt
                    else:
                        print(f"  [{source}] {label!r} no select option for {answer!r}")
                elif input_type == "radio":
                    if self._fill_radio(el, str(answer)):
                        print(f"  [{source}] {label!r} → {answer!r} (radio)")
                        filled_value = str(answer)
                    else:
                        print(f"  [{source}] {label!r} no radio option for {answer!r}")
                elif input_type == "checkbox":
                    if str(answer).lower() in {"yes", "true", "1"}:
                        el.check()
                    else:
                        el.uncheck()
                    print(f"  [{source}] {label!r} → {answer!r} (checkbox)")
                    filled_value = str(answer)
                else:
                    self._fill_text(el, str(answer))
                    print(f"  [{source}] {label!r} → {answer!r}")
                    filled_value = str(answer)
                if filled_value is not None:
                    self.fill_log.append({
                        "label": label,
                        "value": filled_value,
                        "source": source,
                        "field_type": self._effective_type(matched_field),
                        "options": matched_field.get("options", []),
                    })
            except Exception as e:
                print(f"  [warn] fill_from_template_answers failed for {label!r}: {e}")

    def submit(self, job: dict) -> dict:
        """Click the final submit button and return evidence dict."""
        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit Application')",
            "button:has-text('Submit')",
            "button:has-text('Apply')",
        ]
        clicked = False
        for sel in submit_selectors:
            btn = self.page.locator(sel).first
            try:
                if btn.count() > 0 and btn.is_visible(timeout=500):
                    btn.click()
                    self.page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    self.page.wait_for_timeout(2000)
                    print(f"[submit] clicked submit button: {sel!r}")
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            print("[submit] WARNING: no submit button found")
            return {"clicked": False, "success": False, "url": self.page.url, "message": "No submit button found"}

        # Capture evidence
        url = self.page.url
        try:
            body_text = self.page.inner_text("body", timeout=3000).lower()
        except Exception:
            body_text = ""

        SUCCESS_PHRASES = [
            "thank you", "application submitted", "application received",
            "successfully submitted", "we received your application",
            "your application has been", "application complete",
        ]
        success = (
            any(p in body_text for p in SUCCESS_PHRASES)
            or any(k in url.lower() for k in ("confirm", "thank", "success", "submitted"))
        )

        # Grab the most prominent visible text as the confirmation message
        message = ""
        for selector in ["h1", "h2", ".confirmation", ".success", "[class*='confirm']", "[class*='thank']"]:
            try:
                el = self.page.locator(selector).first
                if el.count() > 0 and el.is_visible(timeout=300):
                    message = el.inner_text(timeout=500).strip()
                    if message:
                        break
            except Exception:
                continue

        # Take screenshot
        screenshot_bytes: bytes | None = None
        try:
            screenshot_bytes = self.page.screenshot(full_page=True)
        except Exception:
            pass

        print(f"[submit] url={url}")
        print(f"[submit] success={success}  message={message!r}")
        return {
            "clicked": True,
            "success": success,
            "url": url,
            "message": message,
            "screenshot_bytes": screenshot_bytes,
        }
