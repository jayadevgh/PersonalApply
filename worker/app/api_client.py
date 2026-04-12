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

    def get_submit_signal(self, job_id: str) -> str | None:
        resp = self.client.get(f"/jobs/{job_id}/signal")
        resp.raise_for_status()
        return resp.json().get("signal")

    def get_profile(self) -> dict:
        resp = self.client.get("/profile")
        resp.raise_for_status()
        return resp.json()

    def get_question_answer(self, question_id: str) -> str | None:
        resp = self.client.get(f"/questions/{question_id}/answer")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("final_submitted_text")

    def post_fill_log(self, worker_id: str, events: list[dict]) -> None:
        resp = self.client.post(f"/workers/{worker_id}/fill-log", json=events)
        resp.raise_for_status()

    def get_fill_log(self, worker_id: str) -> list[dict]:
        resp = self.client.get(f"/workers/{worker_id}/fill-log")
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json()

    def post_field_override(self, worker_id: str, override: dict) -> None:
        resp = self.client.post(f"/workers/{worker_id}/field-override", json=override)
        resp.raise_for_status()

    def get_field_overrides(self, worker_id: str) -> list[dict]:
        resp = self.client.get(f"/workers/{worker_id}/field-overrides")
        resp.raise_for_status()
        return resp.json()

    def get_exact_template(
        self,
        normalized_text: str,
        field_type: str | None,
        options_fingerprint: str | None,
    ) -> dict | None:
        """Return matching template dict or None if no exact match."""
        params: dict = {"normalized_text": normalized_text}
        if field_type:
            params["field_type"] = field_type
        if options_fingerprint:
            params["options_fingerprint"] = options_fingerprint
        resp = self.client.get("/answers/templates/exact-match", params=params)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
