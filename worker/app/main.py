import time

from app.api_client import BackendClient
from app.config import settings
from app.flows.apply_flow import process_job


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

        process_job(client, worker_id, job)
        time.sleep(1)


if __name__ == "__main__":
    main()
