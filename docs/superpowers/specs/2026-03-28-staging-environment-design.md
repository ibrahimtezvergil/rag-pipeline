# Staging Environment Design

## Amaç

Production deploy öncesi migration, ingest, query ve sağlık kontrollerini gerçek servislere yakın ama izole bir ortamda doğrulamak.

Hedef:

- production ile aynı servis topolojisini staging için ayrı ayaklandırmak
- production verisinden tamamen ayrılmış bir data plane kurmak
- smoke test ve migration doğrulama alanı sağlamak

## Kapsam

Kapsam içi:

- staging compose katmanı
- staging env örneği
- ayrı port/volume/database isimleri
- kısa runbook

Kapsam dışı:

- Kubernetes manifestleri
- gerçek cloud secret yönetimi
- otomatik CI/CD deploy

## Current State

- repo içinde production-benzeri compose topolojisi var
- bu topoloji tek environment olarak çalışıyor
- ayrı staging compose/env/runbook yok

## Seçilen Yaklaşım

Aynı repo içinde ikinci compose/env katmanı.

Neden:

- mevcut Docker Compose yaklaşımıyla uyumlu
- en düşük operasyonel sürtünme
- local, VM veya Dokploy benzeri ortamlarda kolay uygulanır

## Tasarım

### 1. Dosyalar

Yeni dosyalar:

- `rag-service/docker-compose.staging.yml`
- `rag-service/.env.staging.example`
- opsiyonel runbook:
  - `docs/operations/rag-service-staging-runbook.md`

### 2. Servis topolojisi

Staging de şu servisleri içerir:

- `api`
- `worker`
- `postgres`
- `pgbouncer`
- `redis`
- `qdrant`
- `langfuse_db`
- `langfuse`

### 3. İzolasyon kuralları

Staging ve mevcut ortamın birbirine değmemesi gerekir.

Bu yüzden:

- ayrı Postgres DB/volume
- ayrı Qdrant volume
- ayrı Redis instance
- ayrı Langfuse DB
- ayrı port mapping

Örnek port önerisi:

- API: `18000`
- Langfuse: `13000`
- Postgres: `15432`
- PgBouncer: `16432`
- Qdrant: `16333`

### 4. Env stratejisi

`.env.staging.example` içinde en az şu alanlar net olmalı:

- `DATABASE_URL`
- `DATABASE_DIRECT_URL`
- `DATABASE_USE_PGBOUNCER`
- `QDRANT_URL`
- `REDIS_URL`
- `API_KEYS`
- `GEMINI_API_KEY`
- `COHERE_API_KEY`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_HOST`

İlk sürümde secret değerler örnek/placeholder olur.

### 5. Migration ve smoke akışı

Runbook akışı:

1. staging compose ayağa kaldır
2. `alembic upgrade head`
3. `/health`
4. `POST /collections`
5. sample ingest
6. sample query
7. rate limit doğrulaması

### 6. Production ile ilişki

Bu ortam production replacement değildir.

Kullanım amacı:

- deploy öncesi son doğrulama
- migration rehearsal
- feature smoke test
- callback/langfuse/pgbouncer gibi entegrasyon doğrulaması

## Testing

Eklenecek testler:

- staging compose dosyası ayrı port/volume kullanıyor mu
- `.env.staging.example` gerekli anahtarları içeriyor mu
- runbook temel komutları içeriyor mu

## Başarı Kriteri

- staging topolojisi production stack ile aynı bileşenleri barındırır
- mevcut ortamla port ve volume çakışması yoktur
- staging ayağa kaldırma ve smoke test adımları dokümante edilmiştir
