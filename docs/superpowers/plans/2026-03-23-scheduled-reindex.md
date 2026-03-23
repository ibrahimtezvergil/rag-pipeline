# Scheduled Re-index Plan

1. Add failing tests for schedule endpoint, schedule persistence, due schedule execution, and worker tick.
2. Add schedule model, schema, repository, service, and cron parser.
3. Wire `POST /schedules` into FastAPI router.
4. Wire ARQ `run_schedule_tick` cron job into worker settings.
5. Add migration/test fixture support for `rag_schedules`.
6. Run focused regression and close checklist item with short ref/flow note.
