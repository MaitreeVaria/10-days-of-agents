# Day09/app/main.py
import os, json, uuid
from flask import Flask, request, jsonify
import redis
from rq import Queue, Retry

from Day09.worker.jobs import run_pipeline
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "runs")  # must match worker

r = redis.from_url(REDIS_URL)
q = Queue(QUEUE_NAME, connection=r)

app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify({"ok": True})

@app.post("/enqueue")
def enqueue():
    body = request.get_json(force=True) or {}
    goal = body.get("goal", "Research -> code -> review")

    run_id = f"run-{uuid.uuid4().hex[:8]}"
    job_id = str(uuid.uuid4())
    payload = {"run_id": run_id, "goal": goal}

    # IMPORTANT: enqueue with a dotted path, so the worker can import it
    job = q.enqueue(
        run_pipeline,
        kwargs=payload,
        job_id=job_id,
        retry=Retry(max=2, interval=[5, 10]),
        ttl=600,
        result_ttl=600,
        failure_ttl=3600,
        description=f"pipeline {run_id}",
    )
    return jsonify({"ok": True, "run_id": run_id, "job_id": job.id})


if __name__ == "__main__":
    # For local debugging only; in docker we run via `python Day09/app/main.py`
    app.run(host="0.0.0.0", port=8080)
