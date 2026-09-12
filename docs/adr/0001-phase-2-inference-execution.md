# ADR-0001: Phase 2 inference execution model

**Status:** Accepted — implemented 2026-09-12
**Date:** 2026-09-12
**Deciders:** Project owner
**Affects:** `backend/app/routers/tryon.py`, `backend/app/services/tryon_service.py`, `backend/app/tryon/base.py`, `frontend/src/components/CameraStage.tsx`

## Context

Phase 1 is shipped. `OverlayEngine` composites a PNG in roughly 50 ms, so
`POST /api/tryon` returning the finished image in the same response is not only
acceptable, it is the right design — the round trip is faster than a spinner.

Phase 2 puts a diffusion model behind the same endpoint. CatVTON at 30–50 steps is
5–20 s on a consumer GPU, and minutes on CPU. That is a 100–400× change in the latency
of a single call, which invalidates the assumptions the current request path was built on.

What is actually true of the current code, as opposed to what is often assumed:

- `create_tryon` is declared `def`, not `async def`. FastAPI therefore runs it in the
  anyio threadpool, so a slow engine does **not** block the event loop. Health checks and
  catalog requests keep being served.
- The threadpool defaults to 40 slots. So the failure mode is not a stalled server; it is
  that up to 40 diffusion runs can be admitted concurrently.
- One GPU cannot run 40 diffusions. It will thrash VRAM and then OOM. **The GPU is a
  single serialized resource, and nothing in the current design says so.**
- `run_tryon` already inserts a `TryOnResult` row with `status=PROCESSING` and a
  `public_id` *before* invoking the engine, then updates it in place. `ResultStatus`
  already declares an unused `PENDING`. `GET /api/tryon/{public_id}` already returns
  status and `output_url`.

The forces at play:

1. **Physics.** Queue depth at the GPU is 1. Any design that admits more work than that is
   deferring an OOM, not preventing one.
2. **This is a local single-user desktop app.** Concurrency is ~1 user clicking Generate,
   not a service under load. Operational weight is a real cost with no offsetting benefit.
3. **Weights are big.** 800 MB – 6 GB, loaded once, resident. Whichever process holds the
   model is pinned to one instance.
4. **Phase 1 must not regress.** Fifteen tests assert synchronous overlay behaviour, and the
   live preview depends on the fast path staying fast.
5. **The cache makes many requests free.** `run_tryon` hashes content and checks
   `result_cache` before touching the engine. A cache hit must stay synchronous and instant
   regardless of what the engine would have cost.

## Decision

Adopt **per-engine execution modes** with an in-process single-consumer worker.

Add a declared latency class to `TryOnEngine`. Fast engines keep the current synchronous
path unchanged. Slow engines are admitted to a queue of depth 1 and answered with `202`
plus a `public_id` the client polls.

Concretely:

- `TryOnEngine` gains `execution: Literal["inline", "queued"] = "inline"`. `OverlayEngine`
  inherits `inline`; the diffusion engines declare `queued`.
- `tryon_service.run_tryon` splits into `resolve(db, payload)` — cheap, synchronous, does
  garment lookup, decode, hashing and the cache check — and `execute(result_id)`, which
  runs the engine. `resolve` returning a cache hit short-circuits before either path,
  so cache hits stay instant for every engine.
- A single `asyncio.Queue` with **one** consumer task, started in the existing `lifespan`
  hook. The consumer runs `execute` in a dedicated thread (`run_in_executor`), which keeps
  the event loop free while guaranteeing one inference at a time. Depth 1 is the whole
  point, not a limitation to relax later.
- `POST /api/tryon` returns `200` with the image for `inline` engines (unchanged) and
  `202` with `status="pending"` for `queued` engines. The response model does not change —
  `TryOnResultRead` already carries `status` and a nullable `output_url`.
- Startup reaps orphans: any row left in `PROCESSING` or `PENDING` from a previous process
  is marked `FAILED` with "interrupted". There is no heartbeat, and a crashed process
  otherwise leaves rows that never resolve.

## Options Considered

### Option A: Stay synchronous, add a GPU semaphore

Keep the request path as-is. Wrap `engine.generate` in a `threading.Semaphore(1)` so only
one inference runs; everyone else blocks in the threadpool until their turn.

| Dimension | Assessment |
|-----------|------------|
| Complexity | **Low** — roughly 5 lines |
| Ops cost | **None** — no new process, no new dependency |
| Scalability | **Poor** — queued callers occupy threadpool slots while waiting; 40 clicks exhausts the pool and then genuinely does stall unrelated requests |
| Fit for local desktop | **Partial** — solves OOM, solves nothing else |

**Pros:**
- Smallest possible diff; no frontend change at all.
- Correctly serializes the GPU, which is the actual hazard.
- Preserves the "one call, one image" ergonomics.

**Cons:**
- A 20 s response is at the mercy of every intermediary timeout — Next's rewrite proxy,
  the browser, any future reverse proxy. These fail opaquely and the work is lost even
  though it completed.
- No progress feedback is possible. A 20 s dead request reads as a hang.
- No cancellation. The user changes garment, the old inference still owns the GPU.
- Waiting callers hold threadpool slots, converting a GPU queue into a server-wide one.
- On CPU-only machines, minutes-long inference makes this untenable rather than merely bad.

### Option B: In-process queue with one consumer, poll for the result (chosen)

`asyncio.Queue`, one consumer task in `lifespan`, inference in a dedicated thread. Slow
engines return `202` immediately; the client polls the existing result endpoint.

| Dimension | Assessment |
|-----------|------------|
| Complexity | **Medium** — queue, consumer, reaper, client polling loop |
| Ops cost | **None** — no broker, no extra container |
| Scalability | **Good to the ceiling that matters** — one GPU, many waiting clients, bounded memory |
| Fit for local desktop | **Strong** — `make dev` and `docker compose up` are unchanged |

**Pros:**
- HTTP responses stay fast, so no timeout class of failure exists.
- Enables progress and cancellation: the consumer holds a handle to the running job, and
  diffusion pipelines expose step callbacks that can write progress onto the result row.
- Serialization is structural rather than defensive — depth 1 is the design, not a guard.
- Reuses what is already there: `PENDING`, the pre-committed `PROCESSING` row,
  `GET /api/tryon/{public_id}`, the `lifespan` hook, and `warmup()`.
- Per-engine mode means Phase 1 keeps its exact current behaviour and its tests.

**Cons:**
- Pins the API to a single uvicorn worker. Weights are process-resident singletons
  (`registry.py` instantiates at import), so `--workers 2` would load the model twice and
  OOM. This must be documented and enforced.
- Queue is in memory: a crash loses pending work. Mitigated by the reaper, and acceptable
  when the input is a webcam frame the user can trivially re-send.
- Two code paths through the try-on service, and the frontend gains polling state.

### Option C: Separate worker process (Celery / RQ / arq + Redis)

API enqueues to a broker. A dedicated worker process owns the model and the GPU.

| Dimension | Assessment |
|-----------|------------|
| Complexity | **High** — broker, worker lifecycle, serialization, two sets of logs |
| Ops cost | **High** — Redis container, a second image, `make dev` becomes three processes |
| Scalability | **Excellent** — and entirely wasted here |
| Fit for local desktop | **Poor** — heavy dependency for a single-user app |

**Pros:**
- Clean separation: API restarts do not evict the loaded model.
- The API can then run multiple workers, since none of them hold weights.
- Retries, scheduling and multi-GPU fan-out come essentially free.
- The correct destination if this ever becomes a hosted multi-tenant service.

**Cons:**
- Adds a broker to an app whose selling point is that it runs locally from a folder.
- Roughly triples the setup surface in the README, against zero user-visible gain.
- Images must cross a process boundary — either large broker payloads or a shared volume
  plus path juggling.
- Solves a concurrency problem this app does not have.

## Trade-off Analysis

**A versus B is the real decision; C is a destination, not a next step.**

The trap is treating this as a throughput problem. It is not. Throughput is fixed at one
inference at a time by the hardware, and all three options deliver that. What actually
differs is how the *waiting* is represented.

Option A represents waiting as a held-open HTTP request. That makes the wait invisible
(no progress), fragile (every timeout in the chain is now load-bearing), uninterruptible
(no cancel), and contagious (waiters consume shared threadpool slots, so a GPU queue
becomes a server queue). Each of those is independently annoying; together, on a 20 s
operation, they add up to a product that feels broken.

Option B represents waiting as state in a row. Progress becomes a column. Cancellation
becomes a flag the consumer checks. Failure becomes `status=FAILED` with an error string
the UI can render. The cost is one extra round trip and a polling loop.

Option C represents waiting as a message in a broker, which buys durability and horizontal
scale. For a single-user desktop app, durability across API restarts is worth little — the
input is a live webcam frame, and re-clicking Generate is cheaper than the infrastructure
that would have preserved it.

The decisive argument for B over A is not performance. It is that **B is a superset of A's
behaviour that additionally leaves room for progress and cancellation**, and those two are
not optional at 20 s. The decisive argument for B over C is that C's advantages are all
about multi-tenancy, and the app is explicitly local and single-user.

The per-engine split deserves its own defence. The alternative — route everything through
the queue for uniformity — would add a round trip and a poll to a 50 ms overlay, and would
break the fifteen tests that assert synchronous behaviour. Uniformity is not worth making
the fast path slow. Declaring the mode on the engine keeps the branch in one place and
makes it a property of the model rather than a special case in the router.

**Known cost we are accepting:** single-worker API. It is invisible today, and Option C
remains available unchanged if it ever stops being invisible — `TryOnEngine` does not care
which process calls `generate()`.

## Consequences

**Easier**
- Adding a slow engine: declare `execution = "queued"` and implement `generate()`.
- Progress reporting, cancellation, and a job history view — all become row state.
- GPU safety is structural; concurrent clicks cannot OOM the box.
- Phase 1 is untouched, tests included.

**Harder**
- The API must run single-worker while a GPU engine is registered. Needs a documented
  constraint and a startup assertion, not just a README line.
- Two paths through `tryon_service` to reason about and test.
- The frontend gains polling, which means retry and abandonment logic.
- Debugging moves partly out of the request/response cycle and into the consumer's logs.

**Revisit when**
- More than one concurrent user is real — go to Option C.
- A second GPU appears — the depth-1 queue becomes depth-N with a device pool.
- Inference drops below ~1 s (distilled or quantized model), at which point Option A's
  simplicity becomes attractive again and the `inline` mode already exists to take it.

## Action Items

1. [x] Add `execution: Literal["inline", "queued"] = "inline"` to `TryOnEngine`; set
       `"queued"` on `CatVTONEngine` and `IDMVTONEngine`.
2. [x] Split `tryon_service.run_tryon` into `resolve()` (lookup, decode, hash, cache check)
       and `execute(result_id)` (engine run, save, cache insert). Keep `run_tryon` as the
       inline composition of both so Phase 1 tests pass unchanged.
3. [x] Add `backend/app/services/job_queue.py`: one consumer, start/stop in `lifespan`.
4. [x] Branch `create_tryon` on `engine.execution`; return `202` for `queued`. Cache hits
       return `200` regardless of engine.
5. [x] Startup reaper: `PENDING`/`PROCESSING` rows from a dead process become `FAILED`
       with `error="interrupted"`.
6. [x] Warn at startup when a `queued` engine is available (see note 4 below).
7. [x] Call `warmup()` from `lifespan` for the default engine so the first request does not
       also pay the weight-loading cost.
8. [x] Frontend: poll `GET /api/tryon/{public_id}` on `202`, show progress, allow cancel.
9. [x] Add `progress` (0–1) and `cancelled` columns to `tryon_results`, plus migration
       `database/migrations/0002_job_queue.sql`.
10. [x] Tests: queued engine returns 202; consumer completes the row; cache hit bypasses the
        queue; a job waiting behind a busy worker can be cancelled; reaper clears orphans.
        20 backend tests pass.
11. [x] Correct the README roadmap — step 3 said a slow engine "will hold a worker", which
        understated the threadpool behaviour and missed the GPU contention.

## Implementation notes

Four places where the built thing differs from the proposal above. Kept here rather than
edited into the body, so the reasoning stays legible.

1. **`queue.Queue` + a worker thread, not `asyncio.Queue` + `run_in_executor`.** The route
   handlers are sync `def`, so FastAPI already runs them in the anyio threadpool. Putting
   to an asyncio queue from those threads needs `call_soon_threadsafe` round-trips against
   a loop reference the service would have to stash at startup. A thread-safe queue with
   one consumer thread expresses exactly the same depth-1 guarantee with no cross-thread
   machinery. Same semantics, less surface.

2. **Availability is checked in `resolve()`, via a new `TryOnEngine.unavailable_reason()`.**
   This was implied but not stated. It is load-bearing: previously the `503` for a missing
   CatVTON came from `EngineUnavailable` raised inside `generate()`. Once `generate()` runs
   on a worker thread, that exception has no client to answer, and the caller would get a
   cheerful `202` for a job that can never run. Admission has to reject it.

3. **Added a `CANCELLED` status alongside the `cancelled` column.** The column is the
   *request* ("someone asked to stop"), the status is the *outcome*. Folding cancellation
   into `FAILED` would have made the UI render a user's own deliberate action as an error.

4. **Single-worker enforcement is a startup warning, not an assertion.** A process cannot
   portably discover how many uvicorn workers it is one of. The honest option was to log
   the constraint loudly when a queued engine is live, which is what it does.

Cancellation is currently honoured *before* a job starts. Interrupting a running diffusion
needs the engine to check `result.cancelled` from its step callback; the column and the
endpoint are in place for whoever implements the first real Phase 2 engine.
