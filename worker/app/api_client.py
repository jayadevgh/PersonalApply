import httpx


class BackendClient:
    def __init__(self, base_url: str):
        self.client = httpx.Client(base_url=base_url, timeout=30.0)

    def register_worker(self, name: str) -> dict:
        resp = self.client.post("/workers/register", json={"name": name})
        resp.raise_for_status()
        return resp.json()

    def heartbeat(self, worker_id: str, status: str, current_job_id: str | None, current_stage: str | None) -> dict:
        resp = self.client.post(
            f"/workers/{worker_id}/heartbeat",
            json={
                "status": status,
                "current_job_id": current_job_id,
                "current_stage": current_stage,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def claim_job(self, worker_id: str) -> dict:
        resp = self.client.post("/jobs/claim", json={"worker_id": worker_id})
        resp.raise_for_status()
        return resp.json()

    def update_job_status(self, job_id: str, worker_id: str, from_status: str, to_status: str) -> dict:
        resp = self.client.post(
            f"/jobs/{job_id}/status",
            json={"worker_id": worker_id, "from_status": from_status, "to_status": to_status},
        )
        resp.raise_for_status()
        return resp.json()

    def create_question(self, payload: dict) -> dict:
        resp = self.client.post("/questions", json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_blocked_questions(self) -> list[dict]:
        resp = self.client.get("/questions/blocked")
        resp.raise_for_status()
        return resp.json()
