# Scheduled Re-index Design

## Status: COMPLETED

## Goal

`POST /schedules` ile project bazlı tekrar eden ingestion schedule kaydetmek ve ARQ cron tick üzerinden due kayıtları async ingestion job'larına çevirmek.

## Scope

- Yeni `rag_schedules` tablosu
- `POST /schedules` endpoint
- `ScheduleService.create_schedule()`
- `ScheduleService.run_due_schedules()`
- ARQ cron tick: her dakika due schedule tarama
- `rag_sync_checkpoints` ile `cursor_state` merge

## Flow

1. Client `POST /schedules` çağrısı yapar.
2. Schedule row `cron_expr`, `payload_json`, `next_run_at` ile persist edilir.
3. ARQ cron job her dakika `run_schedule_tick` çalıştırır.
4. Due schedule'lar yüklenir.
5. `source_connector_id` varsa son `rag_sync_checkpoints.cursor_state` payload'a eklenir.
6. Schedule payload `mode=async` ile `IngestionService.create_ingestion_job()` çağrısına çevrilir.
7. Başarılı enqueue sonrası `last_run_at` ve yeni `next_run_at` yazılır.

## Notes

- İlk sürümde tek endpoint `POST /schedules`.
- Cron parser bağımlılık eklemeden dahili çalışır; `*`, `*/n`, liste ve aralık sözdizimini destekler.
- Schedule çalıştırma fail ederse row enabled kalır ve `next_run_at` ilerletilmez.
