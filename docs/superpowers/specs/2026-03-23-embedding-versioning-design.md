# Embedding Versioning Design

## Goal

Aktif `embed_version` ile eski child chunk `embed_version` kayıtlarını karşılaştırıp stale belgeleri yeniden async ingestion kuyruğuna almak.

## Scope

- `IngestionService.requeue_stale_documents()`
- latest indexed document taraması
- current embed version hesaplama
- stale child chunk tespiti
- mevcut ARQ ingestion dispatcher üzerinden requeue
- worker cron tick ile periyodik scan

## Flow

1. Servis current embed version değerini `settings.embed_model + settings.embed_dimension` üzerinden hesaplar.
2. Repository sadece latest `indexed` document kayıtlarını döner.
3. Child chunk'lardan biri current version ile uyuşmuyorsa document stale kabul edilir.
4. Stale document mevcut kaynak bilgisiyle `mode=async` ingestion job olarak yeniden oluşturulur.
5. Dispatcher bunu mevcut ARQ `run_ingest_job` hattına gönderir.

## Notes

- Parent chunk'lar stale hesabına dahil edilmez.
- Son sürüm `indexed` değilse belge tekrar kuyruğa alınmaz; bu duplicate requeue riskini düşürür.
- İlk sürümde scan globaldir, endpoint gerekmez.
