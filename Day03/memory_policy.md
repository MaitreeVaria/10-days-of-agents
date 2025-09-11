# Memory Policy — Day 03

This agent uses two kinds of memory:

* **Short-term (buffer):** last *N* messages of the current chat (verbatim detail).
* **Episodic (session summary):** a compact summary of older turns in the current chat.
* **Semantic (long-term):** durable user facts/preferences stored in a vector DB across sessions.

The goal is to keep context useful, bounded, and safe.

---

## 1) Definitions

* **Buffer (short-term):** last `BUFFER_TURNS` messages (default: 8).
* **Episodic memory:** 2–4 sentence summary of older turns in the current session.
* **Semantic memory:** short, durable fact(s) persisted across sessions (e.g., preferences, identities, projects).

---

## 2) What we store (✅) vs. do not store (🚫)

### ✅ Store (Semantic)

* Stable preferences (e.g., “prefers TypeScript and VS Code”).
* Identity & public handles (e.g., GitHub username).
* Long-running projects (e.g., “building 10-days-of-agents”).
* Reusable definitions the user authored (“my ‘agent’ means X in this repo”).

### 🚫 Do not store

* Secrets, credentials, API keys, tokens, passwords.
* Sensitive personal data (health, political/religious identity, exact address).
* One-time codes/links, ephemeral clipboard data.
* Large raw logs, entire documents/web pages (use RAG, not memory).

If unsure → **don’t store**.

---

## 3) Capture Triggers

### Episodic (auto)

* When the buffer exceeds `BUFFER_TURNS`, summarize overflow into 2–4 sentences:

  * Include: user goals, decisions, cited sources/links, open TODOs.
  * Exclude: exact numbers/IDs unless crucial.

### Semantic (heuristic)

* After each turn, attempt to extract **at most one** durable fact.
* Save only if it is:

  * **Stable** (useful across sessions for weeks/months),
  * **Short** (≤ 240 chars),
  * **Non-sensitive** and **non-secret**.

---

## 4) Data Shape (Schemas)

### Episodic (in state)

```json
{
  "episodic_summary": "Short 2–4 sentence summary of prior turns in this session."
}
```

### Semantic (vector store item)

```json
{
  "text": "User prefers TypeScript.",
  "metadata": {
    "tags": "preference",          // primitive string
    "confidence": 0.7,             // 0–1 float (heuristic)
    "created_at": 1736640000       // unix seconds
  }
}
```

> Metadata must be primitives (str/int/float/bool/None). If you have lists, join or JSON-stringify.

---

## 5) Confidence & Quality

* **Confidence** is a heuristic (default `0.7`) indicating belief this is durable & correct.
* Optional (future): ask the LLM to provide a confidence bucket (e.g., 0.3/0.6/0.9) based on language cues (“might”, “probably”, “always”).

---

## 6) Retrieval Policy (when & how to use memory)

* **Before** answering:

  1. Build context as:

     * `System: Episodic summary` (if present)
     * `System: Known user context` (top-K semantic hits, default `MEMORY_K=3`)
     * Recent buffer messages
  2. Keep the **combined context small** (short summary + last N turns).

* Do **not** inject more than `MEMORY_K` semantic items; keep each item concise.

---

## 7) Forgetting & Size Control

* **Buffer:** fixed size (`BUFFER_TURNS`); older turns summarized, not kept verbatim.
* **Episodic:** replaced/updated as overflow occurs; stays only for current session.
* **Semantic (long-term):**

  * **Cap** total items (e.g., 200). When full, drop **oldest + lowest-confidence** (unless pinned).
  * **Decay**: optionally reduce confidence for items unused after `DECAY_DAYS` (e.g., 30).
  * **Merge** duplicates (string-similarity threshold) into a single, fresher item.
  * **Pinning** (optional): allow a tag `"pinned"` to avoid decay/eviction.

---

## 8) Controls & Toggles

All can be env vars / CLI flags:

* `MEMORY_ENABLED=true|false` (master switch; default: `true`)
* `EPISODIC_ENABLED=true|false` (default: `true`)
* `SEMANTIC_ENABLED=true|false` (default: `true`)
* `BUFFER_TURNS=8`
* `MEMORY_K=3` (semantic top-K retrieval)
* `MEMORY_STORE=chroma|pgvector` (backend)
* `DECAY_DAYS=30` (optional)
* `MEMORY_CAP=200` (optional)

---

## 9) Privacy & Safety

* Never store secrets or sensitive categories.
* **User intent first**: if the user says “don’t remember this”, do not store and delete if present.
* Support **export** and **delete**:

  * Export: dump all `text + metadata` as JSON upon request.
  * Delete: remove memory items matching a query, or all items.

---

## 10) Examples

* **Good semantic memory:**

  * “User GitHub: `MaitreeVaria`.” (tags=`identity`, confidence=`0.9`)
  * “Prefers TypeScript + LangGraph.” (tags=`preference`, confidence=`0.8`)
* **Not good:**

  * “My temporary token is …” → reject.
  * “OpenAI key: …” → reject + warn.
  * “Join Zoom at 10:15 today” → ephemeral; don’t store.

---

## 11) Testing Checklist

1. **Buffer:** exceed `BUFFER_TURNS`, verify overflow is not in state but summary exists.
2. **Episodic recall:** ask about early decisions → answer should use the summary.
3. **Semantic persistence:** teach a fact → restart agent → retrieve fact.
4. **No sensitive capture:** paste an API key → verify not stored.
5. **Toggle off:** set `SEMANTIC_ENABLED=false` → restart → fact not recalled.
6. **Cap/Eviction (optional):** inject many facts → verify oldest/low-confidence is dropped.

---

## 12) Implementation Notes

* Keep episodic summaries **short** (2–4 sentences) to avoid ballooning tokens.
* When writing semantic memory, **validate**: short length, no secrets, non-sensitive.
* When reading semantic memory, **prepend** as bullet points under “Known user context”.
* Ensure metadata remains **primitive** (flatten lists or JSON-stringify if needed).
* For Chroma, use a persistent directory (e.g., `Day03/mem_index/`) and **.gitignore** it.

---

**TL;DR:**
Store a short session summary plus a few durable facts. Keep everything small, safe, and easy to turn off.
