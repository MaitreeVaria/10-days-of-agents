# Day09/worker/worker.py
import os, sys, argparse
from rq import Worker, Queue, Connection
import redis

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", default=os.getenv("QUEUE_NAME", "runs"))
    parser.add_argument("--redis", default=os.getenv("REDIS_URL", "redis://redis:6379/0"))
    args = parser.parse_args()

    # Ensure /workspace is importable so Day09.* and Day08.* can be imported
    if "/workspace" not in sys.path:
        sys.path.insert(0, "/workspace")

    r = redis.from_url(args.redis)
    with Connection(r):
        w = Worker([Queue(args.queue)])
        print(f"[worker] listening on queue={args.queue}, redis={args.redis}", flush=True)
        w.work(with_scheduler=True)

if __name__ == "__main__":
    main()
