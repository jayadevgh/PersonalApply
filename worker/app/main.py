import time

from app.api_client import BackendClient
from app.config import settings


def normalize_question(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text).split())


def simulate_unknown_question(job: dict) -> dict | None:
    # Placeholder for real Greenhouse adapter logic later.
    # For now, any title containing "intern" triggers a sample blocked question.
    if "intern" in job["title"].lower():
        return {
            "raw_text": "Why do you want to work here?",
            "normalized_text": normalize_question("Why do you want to work here?"),
            "field_type": "textarea",
            "field_label": "Why are you interested in this company?",
            "page_url": job["source_url"],
            "dom_hint": "textarea[name='question_1']",
        }
    return None


def wait_until_question_resolved(client: BackendClient, question_id: str) -> None:
    while True:
        blocked = client.get_blocked_questions()
        still_blocked = any(q["id"] == question_id for q in blocked)
        if not still_blocked:
            return
        time.sleep(5)


def main():
    client = BackendClient(settings.backend_base_url)
    worker = client.register_worker(settings.worker_name)
    worker_id = worker["id"]

    print(f"Registered worker: {worker}")

    last_heartbeat = 0.0

    while True:
        now = time.time()
        if now - last_heartbeat >= settings.heartbeat_seconds:
            client.heartbeat(worker_id, "idle", None, None)
            last_heartbeat = now

        claim_resp = client.claim_job(worker_id)
        job = claim_resp.get("job")
        if not job:
            print("No claimable jobs found. Sleeping.")
            time.sleep(settings.claim_poll_seconds)
            continue

        job_id = job["id"]
        print(f"Claimed job: {job['company']} - {job['title']}")

        client.heartbeat(worker_id, "opening_application", job_id, "open_greenhouse_page")
        client.update_job_status(job_id, worker_id, "claimed", "applying")

        client.heartbeat(worker_id, "autofilling", job_id, "fill_known_fields")
        time.sleep(2)

        maybe_question = simulate_unknown_question(job)
        if maybe_question:
            client.heartbeat(worker_id, "waiting_for_user", job_id, "blocked_on_question")
            question_resp = client.create_question(
                {
                    "job_id": job_id,
                    "worker_id": worker_id,
                    **maybe_question,
                }
            )
            question_id = question_resp["question_id"]
            print(f"Blocked on question {question_id}")
            wait_until_question_resolved(client, question_id)

        client.heartbeat(worker_id, "submitting", job_id, "submit_application")
        time.sleep(2)
        client.update_job_status(job_id, worker_id, "applying", "submitted")
        client.heartbeat(worker_id, "completed", None, "submitted")
        print(f"Submitted job: {job['company']} - {job['title']}")
        time.sleep(1)


if __name__ == "__main__":
    main()
