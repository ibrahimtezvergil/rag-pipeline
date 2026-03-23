# Rate Limiting Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ağır endpoint'lere project bazlı Redis sliding window rate limiting eklemek ve limit aşımında `429 + Retry-After` döndürmek.

**Architecture:** Yeni `rate_limit.py` servisi Redis sorted-set sliding window kontrolünü yapar. `deps.py` içinde route-level guard helper'ları tanımlanır ve sadece `/query`, `/chat`, `/ingest`, `/ingest/batch` endpoint'lerine uygulanır. Redis erişilemiyorsa fail-open davranışı korunur.

**Tech Stack:** Redis, FastAPI dependencies, Python time, pytest

---

## Chunk 1: Rate Limit Service

### Task 1: Sliding window servis testlerini yaz

**Files:**
- Create: `rag-service/app/services/rate_limit.py`
- Create: `rag-service/tests/test_rate_limit.py`

- [ ] Step 1: Limit altı isteği kabul eden failing testleri yaz
- [ ] Step 2: Limit üstü isteği reddedip `retry_after_seconds` dönen failing test ekle
- [ ] Step 3: Redis hata durumunda fail-open davranışını doğrulayan failing test ekle
- [ ] Step 4: Testleri çalıştır ve fail ettiğini doğrula
- [ ] Step 5: Minimal sliding window servis implementasyonunu yaz
- [ ] Step 6: `tests/test_rate_limit.py` dosyasını tekrar çalıştır ve geçir

## Chunk 2: Route Guards

### Task 2: Dependency/guard yüzeyini testle

**Files:**
- Modify: `rag-service/app/config.py`
- Modify: `rag-service/app/deps.py`
- Modify: `rag-service/tests/test_api_endpoints.py`

- [ ] Step 1: `/query` limit aşımında `429` ve `Retry-After` döndüğünü doğrulayan failing test ekle
- [ ] Step 2: `/chat` limit aşımında `429` döndüğünü doğrulayan failing test ekle
- [ ] Step 3: `/ingest` ve `/ingest/batch` için guard çağrısını doğrulayan failing test ekle
- [ ] Step 4: Hafif endpoint'lerin etkilenmediğini doğrulayan failing test ekle
- [ ] Step 5: Testleri çalıştır ve fail ettiğini doğrula
- [ ] Step 6: Config varsayılan limit alanlarını ekle
- [ ] Step 7: `deps.py` içine route-level rate limit guard helper'larını ekle
- [ ] Step 8: İlgili route'lara dependency ekle
- [ ] Step 9: API testlerini tekrar çalıştır ve geçir

## Chunk 3: Verification And Checklist

### Task 3: Hedef test paketini çalıştır

**Files:**
- Modify: `rag_service_checklist_v3.md`

- [ ] Step 1: `tests/test_rate_limit.py`
- [ ] Step 2: `tests/test_api_endpoints.py`
- [ ] Step 3: Gerekirse `tests/test_query_service.py` ile regresyon doğrula
- [ ] Step 4: Redis entegrasyon testi gerekiyorsa ek hedef test çalıştır; ortam izin vermiyorsa blokajı not et
- [ ] Step 5: Checklist'te `Rate limiting — Redis sliding window, project_id bazlı, 429 + Retry-After` maddesini işaretle
