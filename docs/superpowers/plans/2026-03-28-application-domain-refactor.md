# Application Domain Refactor Implementation Plan

## Status: COMPLETED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `project` domain terimini tüm sistemde `application` olarak değiştirip tenant/application modelini production-safe biçimde tutarlı hale getirmek.

**Architecture:** Refactor dört ana dilimde yapılacak: veritabanı ve model rename, auth/API compatibility katmanı, servis/repository/test rename ve son olarak dokümantasyon/doğrulama. İç kod ve veri modeli yalnızca `application` dili kullanacak; dış API'de `X-Application-ID` ana başlık olacak ve kısa süreli `X-Project-ID` fallback desteği bırakılacak.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, Qdrant, ARQ, pytest

---

## File Map

### Core schema / model surface

- Modify: `rag-service/app/models/db.py`
- Create: `rag-service/migrations/versions/008_refactor_projects_to_applications.py`
- Modify: `rag-service/tests/test_deployment_config.py`

### Auth / API surface

- Modify: `rag-service/app/middleware/auth.py`
- Modify: `rag-service/app/deps.py`
- Modify: `rag-service/app/api/ingest.py`
- Modify: `rag-service/app/api/query.py`
- Modify: `rag-service/app/api/evaluations.py`
- Modify: `rag-service/app/api/feedback.py`
- Modify: `rag-service/app/api/schedules.py`

### Repository / service surface

- Modify: `rag-service/app/repositories/ingestion.py`
- Modify: `rag-service/app/repositories/evaluations.py`
- Modify: `rag-service/app/repositories/feedback.py`
- Modify: `rag-service/app/repositories/schedules.py`
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/app/services/query.py`
- Modify: `rag-service/app/services/chat.py`
- Modify: `rag-service/app/services/query_cache.py`
- Modify: `rag-service/app/services/rate_limit.py`
- Modify: `rag-service/app/services/observability.py`
- Modify: `rag-service/app/services/tracing.py`
- Modify: `rag-service/app/services/evaluations.py`
- Modify: `rag-service/app/services/feedback.py`
- Modify: `rag-service/app/services/schedules.py`
- Modify: `rag-service/app/services/callbacks.py`
- Modify: `rag-service/app/services/dispatch.py`
- Modify: `rag-service/workers/tasks/ingest.py`
- Modify: `rag-service/workers/tasks/evaluations.py`
- Modify: `rag-service/workers/tasks/schedules.py`

### Schema / payload surface

- Modify: `rag-service/app/schemas/ingest.py`
- Modify: `rag-service/app/schemas/query.py`
- Modify: `rag-service/app/schemas/evaluations.py`
- Modify: `rag-service/app/schemas/feedback.py`
- Modify: `rag-service/app/schemas/schedules.py`

### Tests / fixtures

- Modify: `rag-service/tests/conftest.py`
- Modify: `rag-service/tests/test_auth.py`
- Modify: `rag-service/tests/test_api_endpoints.py`
- Modify: `rag-service/tests/test_ingest.py`
- Modify: `rag-service/tests/test_ingestion_service.py`
- Modify: `rag-service/tests/test_query_service.py`
- Modify: `rag-service/tests/test_query_cache.py`
- Modify: `rag-service/tests/test_rate_limit.py`
- Modify: `rag-service/tests/test_feedback.py`
- Modify: `rag-service/tests/test_evaluations.py`
- Modify: `rag-service/tests/test_schedules.py`
- Modify: `rag-service/tests/test_callbacks.py`
- Modify: `rag-service/tests/test_tracing.py`
- Modify: `rag-service/tests/test_worker_ingest.py`
- Modify: `rag-service/tests/test_worker_evaluations.py`

### Docs

- Modify: `docs/operations/rag-service-handbook.md`
- Modify: `docs/operations/rag-service-staging-runbook.md`
- Modify: `rag_service_checklist_v3.md`

---

## Chunk 1: Database and Model Rename

### Task 1: Add failing migration/deployment tests for application naming

**Files:**
- Modify: `rag-service/tests/test_deployment_config.py`
- Test: `rag-service/tests/test_deployment_config.py`

- [ ] **Step 1: Write failing tests for new schema expectations**

Add assertions that:
- Alembic revisions remain a single-head chain
- new migration includes rename from `rag_projects` to `rag_applications`
- code-level model names expose `RagApplication`

- [ ] **Step 2: Run targeted test to verify failure**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_deployment_config.py -k application
```

Expected: FAIL because migration/model rename does not exist yet.

- [ ] **Step 3: Implement DB/model rename**

In `app/models/db.py`:
- rename `RagProject` -> `RagApplication`
- rename all mapped `project_id` fields to `application_id`
- update foreign key targets to `rag_applications.id`

In new Alembic migration:
- rename table `rag_projects` -> `rag_applications`
- rename dependent columns `project_id` -> `application_id`
- rename indexes/constraints to application naming

- [ ] **Step 4: Run targeted tests to verify pass**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_deployment_config.py
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/models/db.py rag-service/migrations/versions/008_refactor_projects_to_applications.py rag-service/tests/test_deployment_config.py
git commit -m "refactor: rename project schema to application"
```

---

## Chunk 2: Auth and API Compatibility

### Task 2: Move header and request-state surface to application naming

**Files:**
- Modify: `rag-service/app/middleware/auth.py`
- Modify: `rag-service/app/deps.py`
- Modify: `rag-service/tests/test_auth.py`
- Modify: `rag-service/tests/conftest.py`
- Modify: `rag-service/tests/test_api_endpoints.py`

- [ ] **Step 1: Write failing auth/API tests**

Add tests that:
- `X-Application-ID` is accepted as primary header
- `X-Project-ID` still works as deprecated fallback
- request state exposes `application_id`

- [ ] **Step 2: Run targeted tests to verify failure**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_auth.py tests/test_api_endpoints.py -k application
```

Expected: FAIL because middleware and APIs still use project naming.

- [ ] **Step 3: Implement minimal compatibility layer**

Update middleware/deps so that:
- it reads `X-Application-ID` first
- falls back to `X-Project-ID`
- stores only `request.state.application_id`

Update API handlers to pass `application_id` through to services.

- [ ] **Step 4: Re-run targeted tests**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_auth.py tests/test_api_endpoints.py -k application
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/middleware/auth.py rag-service/app/deps.py rag-service/tests/test_auth.py rag-service/tests/conftest.py rag-service/tests/test_api_endpoints.py
git commit -m "refactor: rename auth header to application id"
```

---

## Chunk 3: Repository and Service Refactor

### Task 3: Rename internal service/repository API from project to application

**Files:**
- Modify: repository and service files listed in File Map
- Modify: schema files listed in File Map
- Test: `rag-service/tests/test_ingestion_service.py`
- Test: `rag-service/tests/test_query_service.py`
- Test: `rag-service/tests/test_feedback.py`
- Test: `rag-service/tests/test_evaluations.py`
- Test: `rag-service/tests/test_schedules.py`

- [ ] **Step 1: Write/adjust failing tests around service signatures**

Update tests to expect:
- `application_id` parameter names
- cache/rate-limit/trace payloads use `application_id`
- query/ingest/evaluation/feedback/schedule services no longer reference `project_id`

- [ ] **Step 2: Run focused suites to verify failure**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_ingestion_service.py tests/test_query_service.py tests/test_feedback.py tests/test_evaluations.py tests/test_schedules.py
```

Expected: FAIL with signature/payload naming mismatches.

- [ ] **Step 3: Implement minimal rename through repositories/services**

Apply rename consistently:
- repository method names
- function arguments
- JSON log fields
- trace metadata
- Redis cache/index keys
- rate-limit keys
- callback payload fields

Keep semantics unchanged; rename only what is necessary for domain consistency.

- [ ] **Step 4: Re-run focused suites**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_ingestion_service.py tests/test_query_service.py tests/test_feedback.py tests/test_evaluations.py tests/test_schedules.py tests/test_query_cache.py tests/test_rate_limit.py tests/test_callbacks.py tests/test_tracing.py
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/repositories rag-service/app/services rag-service/app/schemas rag-service/workers/tasks rag-service/tests/test_ingestion_service.py rag-service/tests/test_query_service.py rag-service/tests/test_feedback.py rag-service/tests/test_evaluations.py rag-service/tests/test_schedules.py rag-service/tests/test_query_cache.py rag-service/tests/test_rate_limit.py rag-service/tests/test_callbacks.py rag-service/tests/test_tracing.py
git commit -m "refactor: rename service domain to application"
```

---

## Chunk 4: Documentation and Rollout Notes

### Task 4: Update operator-facing docs and checklist terminology

**Files:**
- Modify: `docs/operations/rag-service-handbook.md`
- Modify: `docs/operations/rag-service-staging-runbook.md`
- Modify: `rag_service_checklist_v3.md`

- [ ] **Step 1: Write failing doc assertions or checklist search targets**

Use search-based validation to identify stale `project` domain references that should now read `application` where appropriate.

- [ ] **Step 2: Run search to capture stale terminology**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline && rg -n "X-Project-ID|project_id|rag_projects|RagProject" docs/operations rag_service_checklist_v3.md rag-service/app rag-service/tests
```

Expected: remaining hits show where docs/runtime still need cleanup or where fallback references must be explicitly marked deprecated.

- [ ] **Step 3: Update docs**

Document:
- why the refactor happened
- tenant/application model
- temporary `X-Project-ID` fallback
- where `knowledge_scope` fits

- [ ] **Step 4: Re-run terminology search**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline && rg -n "X-Project-ID|project_id|rag_projects|RagProject" docs/operations rag_service_checklist_v3.md
```

Expected: only deprecated fallback notes or intentional migration references remain.

- [ ] **Step 5: Commit**

```bash
git add docs/operations/rag-service-handbook.md docs/operations/rag-service-staging-runbook.md rag_service_checklist_v3.md
git commit -m "docs: update terminology to application model"
```

---

## Chunk 5: Full Verification and Release Handoff

### Task 5: Run full relevant verification and prepare rollout

**Files:**
- Verify all changed files from prior chunks

- [ ] **Step 1: Run migration verification**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && alembic upgrade head
```

Expected: PASS on clean verification DB

- [ ] **Step 2: Run full relevant pytest suite**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_api_endpoints.py tests/test_audio_metadata.py tests/test_callbacks.py tests/test_chunking.py tests/test_deployment_config.py tests/test_embedder.py tests/test_evaluations.py tests/test_feedback.py tests/test_ingest.py tests/test_ingestion_service.py tests/test_llm_service.py tests/test_query_service.py tests/test_reranker.py tests/test_sparse_encoder.py tests/test_vector_store.py tests/test_worker_evaluations.py tests/test_worker_ingest.py tests/test_circuit_breaker.py tests/test_db_session.py tests/test_observability.py tests/test_query_cache.py tests/test_query_expansion.py tests/test_rate_limit.py tests/test_schedules.py tests/test_tracing.py tests/test_worker_schedules.py
```

Expected: PASS

- [ ] **Step 3: Run smoke terminology checks**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline && rg -n "request\\.state\\.project_id|X-Project-ID|RagProject|rag_projects" rag-service/app rag-service/tests docs/operations rag_service_checklist_v3.md
```

Expected: only intentional deprecated compatibility references remain.

- [ ] **Step 4: Commit final polish if needed**

```bash
git add -A
git commit -m "refactor: complete application domain migration"
```

- [ ] **Step 5: Push**

```bash
git push origin main
```

---

## Notes for Executor

- Use `@superpowers/test-driven-development` for each code chunk before implementation.
- Do not remove `X-Project-ID` support until at least one compatibility release has shipped.
- Keep retrieval semantics unchanged; this is a domain-language refactor, not a behavior redesign.
- If migration rename proves unsafe in-place, stop and raise it before introducing dual-write complexity.
