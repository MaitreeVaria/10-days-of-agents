# Day 07 — Multi-Agent Orchestration over a Blackboard


A simple, auditable multi-agent system:

* **Supervisor** (LangGraph single node `tick`) plans & routes.
* **Researcher** → writes `out/notes.md` (bullets + citations).
* **Coder** → synthesizes `out/mcp.md` (≤120 words, carries citations).
* **Critic** → verifies rubric, writes `out/review.md`.
* Shared **Blackboard** (`blackboard/storage.json`) logs tasks, artifacts, messages, event history.
* Runs **sequentially** for clarity (concurrency comes later).

---

## Why a blackboard (simple state hub)

* One shared source of truth for:

  * `task` (goal, scope, constraints, acceptance, budget)
  * `subtasks` (queue + status + inputs/outputs)
  * `artifacts` (notes/code/review files under `out/`)
  * `messages` (typed logs per agent)
  * `event_log` (every change for screenshots/audit)
  * `locks` (who owns an artifact while writing)
* Easy to persist & screenshot (`storage.json`, `run.json`).

---

## Folder layout

```
Day07/
  agents/
    researcher.py
    coder.py
    critic.py
  blackboard/
    storage.json           # live state across ticks
    snapshots/             # auto snapshots (optional)
  out/
    notes.md               # Researcher output
    mcp.md                 # Coder output
    review.md              # Critic output
  blackboard.py            # file-backed board (used by agents pre-Day07+)
  tools.py                 # file_write_safe guardrails
  graph_supervisor.py      # LangGraph single-node supervisor (tick + Command)
  run_graph_demo.py        # demo runner + final run.json snapshot
  run.json                 # final snapshot for README (created by runner)
  images/
    (screenshots you’ll add)
```

---

## How it works (Supervisor `tick`)

On each `tick`:

1. **Acceptance check** → stop if met.
2. **Run one** queued subtask (Researcher/Coder/Critic).
3. **Plan** the next subtask when there’s nothing to run:

   * Seed `research_request`
   * After notes → queue `code_request`
   * After code → queue `review_request`
4. If there’s nothing left to run or plan → **stop**.
   The node uses `Command(goto=...)` so it **cannot** loop forever.

---

## Acceptance (demo)

* `file_exists: out/mcp.md`
* `file_exists: out/review.md`

Rubric checked by Critic:

* `max_words: 120` on `out/mcp.md`
* `min_citations: 2` (URLs) in the summary

---

## Run it

```bash
python Day07/run_graph_demo.py
# Example output:
# Graph status: done
# notes.md: True
# mcp.md: True
# review.md: True
# Blackboard: Day07/blackboard/storage.json
# Snapshot: Day07/blackboard/snapshots/<ts>-final.json
# Final run.json: Day07/run.json
```

---

## Blackboard schema (high level)

* `task`: goal, scope, constraints, acceptance, budget
* `subtasks`: `{id, owner, kind, status, input, output, attempts, depends_on, started_at, finished_at}`
* `artifacts`: `{id, type, name, path, version, owner}`
* `messages`: `{id, role, type, content, refs, ts}`
* `event_log`: `{id, kind, who, what, at, refs, delta}`
* `locks`: `{key: owner}`
* `metrics`: `steps`, `tool_calls`, `elapsed_seconds`

---

## Agents & tool access

| Agent      | Purpose            | Allowed writes  | Notes                                                |
| ---------- | ------------------ | --------------- | ---------------------------------------------------- |
| Researcher | Gather notes+cites | `out/notes.md`  | Stubbed bullets + 2 URLs (swap in real search later) |
| Coder      | Produce summary    | `out/mcp.md`    | ≤120 words, carries up to 2 citations from notes     |
| Critic     | QA vs rubric       | `out/review.md` | Checks word count & citations; emits PASS/FAIL       |

All agents write **only** under `Day07/out/` with simple **locks** to avoid clobbering the same file.

---

## Architecture (diagram)

```mermaid
graph LR
    S[Supervisor (tick)] --> R[Researcher]
    S --> C[Coder]
    S --> Q[Critic]
    R --|notes.md| B[(Blackboard + out/)]
    C --|mcp.md| B
    Q --|review.md| B
    B <-->|reads/writes| S
```

---

## Acceptance checklist

* [x] Supervisor creates subtasks in order (even if pre-planned/stubbed).
* [x] Handoffs are visible in `event_log` with clear `plan` / `code_result` / `review_result` messages.
* [x] Researcher produces notes with ≥2 citations.
* [x] Coder writes `out/mcp.md` under `out/`.
* [x] Critic checks rubric and writes `out/review.md`.
* [x] Supervisor stops when acceptance is met or budget exceeded.
* [x] You can point to the exact trace in `event_log`.

---

## Troubleshooting

* **Recursion limit**: the single-node `tick` with `Command(goto=...)` guarantees a stop. If it ever ran too many steps, the **budget** (default 60 in the demo) also halts cleanly.
* **Paths**: use `out/...` (not `day07/out/...`) in acceptance and when referring to artifacts.
* **Deprecation warning**: if you see `datetime.utcnow()` warnings, swap to `datetime.datetime.now(datetime.UTC)` in future patches (doesn’t affect this run).
