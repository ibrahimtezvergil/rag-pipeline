# Rate Limiting Design

## Goal

RAG servisinin maliyetli endpoint'lerine production-ready rate limiting eklemek. Hedef, tek bir proje üzerinden query/chat/ingest flood durumlarını Redis tabanlı sliding window ile sınırlamak ve limit aşımında standart `429 + Retry-After` davranışı sağlamaktır.

## Scope

Bu dilimde sadece ağır endpoint'ler korunur:
- `POST /query`
- `POST /chat`
- `POST /ingest`
- `POST /ingest/batch`

Kapsam dışı:
- tüm endpoint'lere global limit
- user/IP bazlı limit
- token-cost weighted quota
- circuit breaker

## Current State

- Auth middleware `X-Project-ID` ve `X-API-Key` başlıklarını doğruluyor ve `request.state` içine yazıyor.
- Redis zaten chat memory, queue ve health check tarafında kullanılıyor.
- Şu an project bazlı request limiting yok; maliyetli endpoint'ler limitsiz.

## Recommended Approach

Redis sorted-set tabanlı sliding window.

Neden:
- Gerçek sliding window davranışı verir.
- Basit counter+TTL yaklaşımındaki bucket edge sorunlarını yaşamaz.
- Project + endpoint kombinasyonu için yeterince hafif ve deterministik kalır.

## Endpoint Scope

İlk sürüm yalnızca ağır endpoint'lere uygulanır.

Neden:
- Maliyet baskısı burada oluşuyor.
- `GET /health` ve `GET /collections` gibi hafif endpoint'lere ilk sürümde limit koymak gereksiz.
- Operasyonel sürprizi azaltır.

## Key Strategy

Redis key formatı:
- `rate_limit:{project_id}:{route_name}`

Örnek:
- `rate_limit:proj-123:query`
- `rate_limit:proj-123:ingest_batch`

Bu dilimde limit birimi:
- project bazlı
- endpoint bazlı

## Default Limits

Başlangıç limitleri:
- `/query`: `60/dk`
- `/chat`: `60/dk`
- `/ingest`: `20/dk`
- `/ingest/batch`: `10/dk`

Bu değerler config'ten override edilebilir olmalı.

## Config Shape

İlk sürümde `Settings` ya da benzeri config üstünden varsayılanlar tanımlanır.

Örnek mantık:
- `rate_limit_query_per_minute`
- `rate_limit_chat_per_minute`
- `rate_limit_ingest_per_minute`
- `rate_limit_ingest_batch_per_minute`

Per-project override bu dilimde zorunlu değildir.

## Integration Strategy

Middleware yerine route-level dependency/guard kullanılmalı.

Neden:
- Sadece seçili endpoint'lere uygulanır.
- Path-based branching logic middleware içinde dağılmaz.
- Test etmesi daha nettir.

Önerilen yapı:
- `app/services/rate_limit.py`
  Redis sliding window check servisi
- `app/deps.py`
  Route bazlı rate-limit dependency helper
- `app/api/query.py`
  `/query` ve `/chat` endpoint'lerine guard eklenir
- `app/api/ingest.py`
  `/ingest` ve `/ingest/batch` endpoint'lerine guard eklenir

## Sliding Window Behavior

Her request için:
1. current timestamp al
2. window dışındaki eski kayıtları sil
3. mevcut count'u ölç
4. limit aşılmışsa reject et
5. değilse current timestamp'i yaz
6. key'e kısa TTL ver

Servis dönüşü:
- `allowed: bool`
- `retry_after_seconds: int | None`
- `remaining: int | None` opsiyonel

## Error Contract

Limit aşılırsa:
- status: `429 Too Many Requests`
- body: kısa sabit mesaj
- header: `Retry-After: <seconds>`

Örnek body:
- `{"detail": "Rate limit exceeded"}`

## Failure Strategy

Redis erişilemiyorsa:
- fail-open davranışı önerilir

Neden:
- Redis problemi yüzünden tüm query/ingest trafiğini kilitlemek ilk sürüm için fazla agresif olur.
- Bu durum observability log ile ayrıca görünür hale getirilebilir.

## Testing

- rate limit servisi sliding window kabul/reject testi
- `Retry-After` hesabı testi
- `/query` limit aşımında 429 + header testi
- `/chat` limit aşımında 429 testi
- `/ingest` ve `/ingest/batch` guard testi
- hafif endpoint'lerin (`/health`, `/collections`) bu dilimde etkilenmediği testi

## Rollout

Bu dilim sonunda checklist'te şu madde kapanır:
- `Rate limiting — Redis sliding window, project_id bazlı, 429 + Retry-After`

Sonraki mantıklı adım:
- `Circuit breaker`
