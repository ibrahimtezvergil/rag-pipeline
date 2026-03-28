# RAG Service P1 Foundation Design

## Status: ARCHIVED — SUPERSEDED

**Date:** 2026-03-15

## Goal

`rag-service/` adında ayrı bir FastAPI servisi kurmak. Bu ilk fazda çalışan servis iskeleti, altyapı konteynerleri, PostgreSQL şeması, API anahtarı tabanlı kimlik doğrulama ve servis durumunu raporlayan `/health` endpoint'i sağlanacak.

## Scope

- FastAPI uygulama iskeleti
- `pydantic-settings` ile ortam değişkeni yönetimi
- Docker Compose ile PostgreSQL, Redis, Qdrant, Langfuse ve API servisleri
- SQLAlchemy async modelleri ve Alembic initial migration
- `X-API-Key` ve `X-Project-ID` header zorunluluğu
- PostgreSQL, Redis ve Qdrant erişimini raporlayan `/health`
- Temel auth ve health testleri

## Architecture

Servis `app/config.py`, `app/db/`, `app/models/`, `app/middleware/` ve `app/api/` ayrımıyla küçük sorumluluklara bölünecek. Veritabanı erişimi SQLAlchemy 2.x async stack ile sağlanacak; migration'lar Alembic üzerinden yönetilecek.

Auth kontrolü middleware katmanında yapılacak. Route handler'lar auth detayını bilmeyecek; geçerli proje ve anahtar bilgisi `request.state` üzerinden taşınacak. `/health` endpoint'i bağımlı servisleri ayrı ayrı kontrol ederek birleşik durum döndürecek.

## Data Model

İlk migration aşağıdaki tabloları oluşturacak:

- `rag_tenants`
- `rag_projects`
- `rag_documents`
- `rag_chunks`
- `rag_ingestion_jobs`
- `rag_chunk_diff_log`
- `rag_sync_checkpoints`
- `tenant_secrets`

Şema, `rag_service_checklist_v3.md` içindeki P1 foundation alanlarıyla uyumlu olacak; ileride ingestion ve query fazları aynı temel üstüne eklenecek.

## Error Handling

- Eksik auth header'ları `401`
- Geçersiz API key `403`
- `/health` içinde erişilemeyen servisler `degraded` durumuyla raporlanacak
- Health endpoint'i genel olarak JSON dönecek; exception zinciri istemciye sızdırılmayacak

## Testing

Önce auth ve health davranışı için failing test yazılacak. Ardından minimal uygulama kodu eklenip testler yeşile getirilecek. Health kontrollerinde dış servislere gerçek bağlantı yerine override edilebilir checker fonksiyonları kullanılacak.
