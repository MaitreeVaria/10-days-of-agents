# Day 09 — Scaling & Observability

This takes the Day 08 MCP-based tool mesh and **runs everything in containers** with:

✅ Redis-backed async queue
✅ `rq` worker to process jobs
✅ OpenTelemetry traces
✅ Jaeger UI for monitoring
✅ No local Python execution — **everything via Docker**

---

## ✅ What’s new vs Day 08

* **Everything is containerized**:

  * `app` → HTTP endpoint to enqueue goals
  * `worker` → runs the pipeline (research → code → review)
  * `redis` → job queue
  * `otel-collector` → receives traces
  * `jaeger` → trace visualization UI
* MCP servers are also containerized (`fs-mcp`, `web-mcp`, `docs-mcp`)
* `RQ` replaces immediate synchronous pipeline calls
* Environment variables + volumes handled in `docker-compose.yml`

---

## ✅ Folder layout (relevant for Docker)

```
10-days-of-agents/
 ├─ Day07/ ...               (for Blackboard import, unchanged)
 ├─ Day08/ ...               (MCP servers + registry + out/)
 ├─ Day09/
 │   ├─ app/
 │   │   ├─ main.py
 │   │   └─ Dockerfile
 │   ├─ worker/
 │   │   ├─ worker.py
 │   │   ├─ jobs.py
 │   │   └─ Dockerfile
 │   ├─ servers/
 │   │   ├─ fs-mcp/
 │   │   ├─ web-mcp/
 │   │   ├─ docs-mcp/
 │   │   └─ (their Dockerfiles)
 │   ├─ otel-collector/
 │   │   └─ config.yaml
 │   └─ docker-compose.yml
 └─ Day09/...
```

---

## ✅ Start everything

From the **repo root** (same level as `Day09/`):

```bash
docker compose -f Day09/docker-compose.yml up -d --build
```

To rebuild only app/worker:

```bash
docker compose -f Day09/docker-compose.yml build app worker
docker compose -f Day09/docker-compose.yml up -d app worker
```

Check containers:

```bash
docker compose -f Day09/docker-compose.yml ps
```

You should see `redis`, `app`, `worker`, `otel-collector`, `jaeger`, and the MCP servers.

---

## ✅ Health check

```bash
curl -s http://localhost:8080/health
```

If the app is running, you’ll see something like:

```
{"ok": true}
```

---

## ✅ Enqueue a run

```bash
curl -s -X POST http://localhost:8080/enqueue \
  -H "Content-Type: application/json" \
  -d '{"goal":"Research -> code -> review"}'
```

Expected response:

```json
{"ok":true,"job_id":"<uuid>","run_id":"run-xxxx"}
```

The `worker` container will pick it up automatically and the MCP servers will be launched behind the scenes via the adapter.

---

## ✅ Where artifacts appear

Results are written to:

```
Day08/out/
 ├─ notes.md
 ├─ mcp.md
 ├─ review.md
```

Blackboard logs & snapshots go under:

```
Day08/blackboard/
```

Logs from containers:

```bash
docker logs day09-worker --tail=100
docker logs day09-app --tail=100
```

---

## ✅ View traces (Jaeger)

Open in browser:

```
http://localhost:16686
```

Select service:

* `agents-app`
* `agents-worker`

You’ll see traces for each tool call and pipeline step.

---

## ✅ Restart or stop everything

Shut down all containers:

```bash
docker compose -f Day09/docker-compose.yml down
```

Restart:

```bash
docker compose -f Day09/docker-compose.yml up -d
```

---

## ✅ Troubleshooting

### ❌ “Cannot connect to Docker daemon”

Start Docker Desktop.

### ❌ `ModuleNotFoundError` for Day07/Day08

Make sure volumes in `docker-compose.yml` point to the correct repo root and you ran from the root directory.

### ❌ No tools or MCP calls failing

Check that the MCP server folders exist under `Day09/servers/` and the registry paths are correct (`Day08/registry/endpoints.yaml` is still referenced).

### ❌ No files in `out/`

Check worker logs:

```bash
docker logs day09-worker
```

---

## ✅ Summary

✅ No local Python runs
✅ No manual MCP server launching
✅ Queue-based pipeline (RQ + Redis)
✅ Traces via OTEL → Jaeger
✅ `curl` is your only interaction layer

Once `curl /enqueue` works and files appear in `Day08/out/`, **Day 09 is complete**.


