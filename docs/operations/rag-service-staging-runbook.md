# RAG Service Staging Runbook

Bu runbook staging ortamını ayağa kaldırmak ve production öncesi temel smoke testleri doğrulamak içindir.

## 1. Ayağa Kaldırma

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service
docker-compose -f docker-compose.staging.yml up -d --build
```

Beklenen servisler:

- api
- worker
- postgres
- pgbouncer
- redis
- qdrant
- langfuse_db
- langfuse

## 2. Migration

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service
ENV_FILE=.env.staging.example .venv313/bin/python -m alembic upgrade head
```

## 3. Sağlık Kontrolü

```bash
curl -sS http://127.0.0.1:18000/health
```

Beklenen durum:

- postgres up
- redis up
- qdrant up
- embedder up

## 4. Smoke Test

Önce collection oluştur:

```bash
curl -sS -X POST http://127.0.0.1:18000/collections \
  -H 'X-API-Key: staging-key-1' \
  -H 'X-Application-ID: <application-id>' \
  -H 'Content-Type: application/json' \
  -d '{"name":"rag_chunks"}'
```

Sonra sample ingest:

```bash
curl -sS -X POST 'http://127.0.0.1:18000/ingest?mode=sync' \
  -H 'X-API-Key: staging-key-1' \
  -H 'X-Application-ID: <application-id>' \
  -H 'Content-Type: application/json' \
  -d '{
    "source_type": "structured",
    "title": "staging snapshot",
    "records": [{"customer":"Acme","invoice":"INV-1001","status":"paid"}]
  }'
```

Sonra sample query:

```bash
curl -sS -X POST http://127.0.0.1:18000/query \
  -H 'X-API-Key: staging-key-1' \
  -H 'X-Application-ID: <application-id>' \
  -H 'Content-Type: application/json' \
  -d '{"question":"Which invoice was paid?"}'
```

## 5. Minimum Kontrol Listesi

1. `docker-compose -f docker-compose.staging.yml up -d --build`
2. `alembic upgrade head`
3. `/health`
4. `/ingest`
5. `/query`

Bu beş adım geçiyorsa staging ortamı deploy öncesi doğrulama için hazırdır.
