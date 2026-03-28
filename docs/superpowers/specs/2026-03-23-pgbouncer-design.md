# PgBouncer Design

## Status: COMPLETED

## Goal

Runtime API/worker PostgreSQL bağlantılarını PgBouncer üzerinden geçirmek, asyncpg + transaction pooling uyumunu sağlamak ve migration akışını doğrudan PostgreSQL'e bağlı tutmak.

## Current State

- `api` ve `worker` container'ları doğrudan `postgres:5432`'ye bağlanıyor.
- `app/db/session.py` SQLAlchemy async engine'i varsayılan pool ile açıyor; PgBouncer arkasında double-pooling riski var.
- Alembic `settings.database_url` üstünden çalışıyor; PgBouncer transaction mode üzerinden migration çalıştırmak doğru varsayılan değil.
- Docker Compose içinde PgBouncer servisi yok.

## Approach

1. Runtime için yeni PgBouncer servisi eklenecek.
2. `DATABASE_URL` runtime'da PgBouncer'a bakacak.
3. `DATABASE_DIRECT_URL` migration/doğrudan Postgres işleri için eklenecek.
4. `DATABASE_USE_PGBOUNCER=true` olduğunda:
   - SQLAlchemy `NullPool` kullanacak.
   - `pool_pre_ping=True` açık olacak.
   - asyncpg URL'sine `prepared_statement_cache_size=0` eklenecek.
5. Alembic mümkünse `DATABASE_DIRECT_URL`, yoksa `DATABASE_URL` kullanacak.

## Service Boundaries

- `app/config.py`
  Yeni runtime/direct DB ve PgBouncer ayarlarını taşır.
- `app/db/session.py`
  Runtime DB URL'sini normalize eder, engine kwargs üretir.
- `migrations/env.py`
  Migration URL seçimini doğrudan DB lehine yapar.
- `docker-compose.yml`
  PgBouncer servisinin ve runtime env wiring'inin ana referans noktası olur.
- `docker/pgbouncer/*`
  Container build ve config template/entrypoint dosyaları burada tutulur.

## Runtime Rules

- `api` ve `worker` yalnızca PgBouncer üzerinden bağlanır.
- `langfuse` ve `postgres` doğrudan PostgreSQL kullanmaya devam eder.
- Runtime pool mode: `transaction`
- Varsayılan PgBouncer kapasitesi:
  - `default_pool_size=20`
  - `max_client_conn=50`
  - `reserve_pool_size=5`

## Error Handling

- PgBouncer devre dışıysa runtime servisleri DB'ye bağlanamaz; compose bağımlılığı bunu erken görünür kılar.
- `DATABASE_DIRECT_URL` verilmezse migration mevcut `DATABASE_URL`'den türetilir; bu backward-compatible fallback'tır.
- URL zaten `prepared_statement_cache_size` içeriyorsa tekrar yazılmaz.

## Testing

- `app/db/session.py`
  - PgBouncer açıkken runtime URL `prepared_statement_cache_size=0` ekler.
  - Mevcut query param'ları korur.
  - PgBouncer açıkken engine kwargs `NullPool` döner.
- `migrations/env.py`
  - direct URL varsa onu seçer.
- `docker-compose.yml`
  - `pgbouncer` servisi vardır.
  - `api` ve `worker` `DATABASE_URL` olarak `pgbouncer:6432` kullanır.
