import base64
import time

from app.adapters.factory import get_adapter
from app.api_client import BackendClient


class _JobDeleted(Exception):
    """Raised anywhere in the flow when the job is removed from the queue."""


def _post_evidence(client: BackendClient, worker_id: str, job_id: str, evidence: dict) -> None:
    """Post submission evidence (screenshot + URL) to backend."""
    try:
        screenshot_b64 = None
        if evidence.get("screenshot_bytes"):
            screenshot_b64 = base64.b64encode(evidence["screenshot_bytes"]).decode()
        client.post_submission_evidence(job_id, {
            "clicked": evidence.get("clicked", False),
            "success": evidence.get("success", False),
            "url": evidence.get("url", ""),
            "message": evidence.get("message", ""),
            "screenshot_b64": screenshot_b64,
        })
    except Exception as e:
        print(f"[warn] could not post submission evidence: {e}")


def _handle_page(
    client: BackendClient,
    worker_id: str,
    job_id: str,
    job: dict,
    adapter,
    page_num: int,
) -> None:
    """Fill known fields + handle unknown questions for the current form page."""
    client.heartbeat(worker_id, "autofilling", job_id, f"fill_known_fields_p{page_num}")
    adapter.fill_known_fields(job)
    time.sleep(1)

    unknown_questions = adapter.find_unknown_questions(job)
    if not unknown_questions:
        return

    auto_fill: list[dict] = []
    to_block: list[dict] = []

    for q in unknown_questions:
        template = client.get_exact_template(
            q["normalized_text"],
            q.get("field_type"),
            q.get("options_fingerprint"),
        )
        if template is not None:
            if template["answer_text"]:
                auto_fill.append({**q, "answer": template["answer_text"]})
            else:
                print(f"  [skip]   {q['raw_text']!r} (remembered skip)")
        else:
            to_block.append(q)

    if auto_fill:
        print(f"\n[template] auto-filling {len(auto_fill)} question(s):")
        for item in auto_fill:
            print(f"           · {item['raw_text']!r} → {item['answer']!r}")
        adapter.fill_from_template_answers([{**item, "_source": "template"} for item in auto_fill])

    if to_block:
        print(f"\n[blocked] {len(to_block)} question(s) need human input:")
        for q in to_block:
            print(f"         · {q['raw_text']}")
        client.heartbeat(worker_id, "waiting_for_user", job_id, "blocked_on_question")

        # Create questions in backend, then poll until all resolved
        id_to_q: dict[str, dict] = {}
        for q in to_block:
            result = client.create_question({
                "job_id": job_id,
                "worker_id": worker_id,
                "raw_text": q["raw_text"],
                "normalized_text": q["normalized_text"],
                "field_type": q.get("field_type"),
                "field_label": q.get("field_label"),
                "page_url": q.get("page_url"),
                "dom_hint": q.get("dom_hint"),
                "options": q.get("options"),
                "options_fingerprint": q.get("options_fingerprint"),
                "required": q.get("required", False),
            })
            qid = result["question_id"]
            id_to_q[qid] = q
            print(f"  [blocked] {q['raw_text']!r}  id={qid}")

        print(f"\n[waiting] open http://localhost:8000/ui/blocked")
        while True:
            if not client.job_exists(job_id):
                print("[waiting] job was deleted — aborting")
                raise _JobDeleted()
            blocked = client.get_blocked_questions()
            blocked_ids = {str(bq["id"]) for bq in blocked}
            remaining = [qid for qid in id_to_q if qid in blocked_ids]
            if not remaining:
                print("[waiting] all questions resolved — resuming")
                break
            print(f"[waiting] {len(remaining)} still pending…")
            time.sleep(5)

        # Fetch each answer and fill it into the form
        fill_from_ui: list[dict] = []
        for qid, q in id_to_q.items():
            answer_text = client.get_question_answer(qid)
            if answer_text:
                fill_from_ui.append({**q, "answer": answer_text})
            else:
                print(f"  [skip]   {q['raw_text']!r} (no answer / skipped)")

        if fill_from_ui:
            print(f"\n[ui-fill] filling {len(fill_from_ui)} human-answered question(s)")
            adapter.fill_from_template_answers([{**item, "_source": "ui"} for item in fill_from_ui])

        client.heartbeat(worker_id, "autofilling", job_id, f"resuming_p{page_num}")


def process_job(client: BackendClient, worker_id: str, job: dict) -> None:
    job_id = job["id"]

    # Use profile from backend API (editable in UI), fall back to .env
    try:
        profile = client.get_profile()
    except Exception:
        from app.profile import get_profile_dict
        profile = get_profile_dict()
        print("[profile] using .env (backend profile API unavailable)")

    adapter = get_adapter(job["platform"], profile=profile)

    try:
        print(f"Claimed job: {job['company']} - {job['title']}")

        client.heartbeat(worker_id, "opening_application", job_id, "open_application")
        adapter.open_application(job)
        client.update_job_status(job_id, worker_id, "claimed", "applying")

        page_num = 0
        while True:
            page_num += 1
            _handle_page(client, worker_id, job_id, job, adapter, page_num)

            if not adapter.go_to_next_page():
                break
            print(f"\n[page] navigated to page {page_num + 1}")

        client.update_job_status(job_id, worker_id, "applying", "review")

        # Post fill log so UI can show what was filled
        if hasattr(adapter, "fill_log") and adapter.fill_log:
            try:
                client.post_fill_log(worker_id, adapter.fill_log)
            except Exception as e:
                print(f"[warn] could not post fill log: {e}")

        auto_submit = profile.get("auto_submit", False)
        if auto_submit:
            print(f"[auto-submit] submitting {job['company']} - {job['title']} automatically")
            evidence = adapter.submit(job)
            _post_evidence(client, worker_id, job_id, evidence)
            client.update_job_status(job_id, worker_id, "review", "submitted")
            client.heartbeat(worker_id, "idle", None, None)
            print(f"[submitted] {job['company']} - {job['title']}")
        else:
            client.heartbeat(worker_id, "paused", job_id, "review_before_submit")
            print(f"[review] {job['company']} - {job['title']} — waiting for submit/skip in UI")

            while True:
                if not client.job_exists(job_id):
                    print(f"[review] job was deleted — aborting")
                    raise _JobDeleted()

                signal = client.get_submit_signal(job_id)
                if signal == "submit":
                    evidence = adapter.submit(job)
                    _post_evidence(client, worker_id, job_id, evidence)
                    client.update_job_status(job_id, worker_id, "review", "submitted")
                    client.heartbeat(worker_id, "idle", None, None)
                    print(f"[submitted] {job['company']} - {job['title']}")
                    break
                elif signal == "skip":
                    try:
                        client.update_job_status(job_id, worker_id, "review", "skipped")
                    except Exception:
                        pass  # job may have been deleted
                    client.heartbeat(worker_id, "idle", None, None)
                    print(f"[skipped] {job['company']} - {job['title']}")
                    break

                # Apply any field edits the user made from the UI
                try:
                    overrides = client.get_field_overrides(worker_id)
                    if overrides:
                        print(f"[review] applying {len(overrides)} field edit(s) from UI")
                        adapter.fill_from_template_answers([{**o, "_source": "ui"} for o in overrides])
                        # Patch the fill log with new values and re-publish
                        for o in overrides:
                            for entry in adapter.fill_log:
                                if entry["label"] == o["label"]:
                                    entry["value"] = o["value"]
                                    entry["source"] = "ui"
                                    break
                            else:
                                adapter.fill_log.append({
                                    "label": o["label"],
                                    "value": o["value"],
                                    "source": "ui",
                                    "field_type": o.get("field_type", "text"),
                                    "options": o.get("options", []),
                                })
                        client.post_fill_log(worker_id, adapter.fill_log)
                except Exception as e:
                    print(f"[warn] override poll failed: {e}")

                time.sleep(4)

    except _JobDeleted:
        print(f"[abort] job {job_id} was deleted — going idle")
        client.heartbeat(worker_id, "idle", None, None)
    finally:
        if hasattr(adapter, "close"):
            adapter.close()
