# Circuit Breaker Design

## Goal

RAG servisinin dış bağımlılık çağrılarına production-ready circuit breaker eklemek. Hedef, tekrar eden provider/Qdrant hatalarında sistemi gereksiz dış çağrılarla zorlamamak, cooldown süresince hızlı fail etmek ve mümkün olan yerlerde kontrollü fallback davranışı korumaktır.

## Scope

Bu dilimde process-local circuit breaker uygulanır.

Kapsanan servisler:
- `qdrant`
- `gemini_embed`
- `gemini_llm`
- `cohere_rerank`

Kapsam dışı:
- Redis-backed distributed breaker
- admin dashboard / breaker inspection UI
- manuel reset endpoint'i

## Current State

- Dış servis çağrıları doğrudan `httpx` ile yapılıyor.
- Retry bazı yerlerde mevcut (`embedder.py`), fakat tekrar eden hata dalgalarında global kısa devre mekanizması yok.
- Query tarafında fallback davranışları var, ama bunlar sürekli hata veren upstream'leri susturmuyor.

## Recommended Approach

Process-local state tutan hafif circuit breaker servisi.

Neden:
- İlk production sürümü için en düşük riskli yol bu.
- Yeni runtime bağımlılığı eklemez.
- Tek instance veya düşük paralelli dağıtımda yeterli koruma sağlar.
- Sonraki iterasyonda Redis-backed sürüme taşınabilir.

## State Model

Her servis adı için breaker state tutulur:
- `closed`
- `open`
- `half_open`

Ek alanlar:
- `failure_count`
- `opened_at`

Davranış:
1. `closed`
   - çağrılar normal akar
   - ardışık hata eşiği aşılırsa `open`
2. `open`
   - dış çağrı yapılmaz
   - cooldown süresi bitene kadar kısa devre
3. `half_open`
   - tek deneme çağrısı geçer
   - başarılıysa `closed`
   - başarısızsa tekrar `open`

## Config

İlk sürümde global config yeterlidir:
- `circuit_breaker_failure_threshold`
- `circuit_breaker_recovery_timeout_seconds`

Servis bazlı override bu dilimde zorunlu değildir.

## Service Boundaries

- `app/services/circuit_breaker.py`
  Breaker state ve karar mantığı burada tutulur.
- `app/services/vector_store.py`
  `qdrant` breaker entegrasyonu.
- `app/services/embedder.py`
  `gemini_embed` breaker entegrasyonu.
- `app/services/llm.py`
  `gemini_llm` breaker entegrasyonu.
- `app/services/reranker.py`
  `cohere_rerank` breaker entegrasyonu.

## Error Contract

Yeni kontrollü exception:
- `CircuitOpenError(service_name)`

Davranış:
- breaker `open` ise dış çağrı hiç yapılmadan bu hata fırlatılır
- çağrı başarılıysa breaker resetlenir
- çağrı hata verirse breaker failure sayacı artar

## Fallback Integration

`cohere_rerank`
- breaker açık ise rerank atlanır
- query mevcut hybrid sıra ile devam eder

`gemini_llm`
- breaker açık ise `_fallback_answer()` kullanılır

`qdrant`
- breaker açık ise mevcut fallback davranışı korunur
- query metadata/empty yoluna düşebilir

`gemini_embed`
- ingestion/job tarafında kontrollü hata ile fail olur
- mevcut retry + job failure akışı korunur

## Testing

- breaker state geçiş testi (`closed -> open -> half_open -> closed`)
- open durumda dış çağrı yapılmadan kısa devre testi
- recovery timeout sonrası half-open denemesi testi
- `QueryService` içinde `gemini_llm` breaker açıkken fallback answer testi
- reranker breaker açıkken rerank skip testi

## Rollout

Bu dilim sonunda checklist'te şu madde kapanır:
- `Circuit breaker — Qdrant/Gemini/Cohere/LLM per-service kurallar`

Sonraki mantıklı adım:
- `Confidence score`
