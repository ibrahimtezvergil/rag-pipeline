# Direct Query Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/query` için retrieval context üstünden gerçek LLM answer generation eklemek ve güvenli fallback davranışını tamamlamak.

**Architecture:** Mevcut `QueryService` retrieval, rerank ve source assembly akışını korur. Yeni `prompts.py` prompt/fallback metinlerini üretir, yeni `llm.py` provider-agnostic generate katmanını sağlar, `QueryService` normal yolda `llm.generate()` çağırır ve yalnızca hata durumunda `_fallback_answer()` ile degrade olur. `query_embedding` response yüzeyinden kaldırılır.

**Tech Stack:** FastAPI, SQLAlchemy, Gemini HTTP API, pytest

---

## Chunk 1: Prompt And LLM Boundaries

### Task 1: Prompt builder testlerini yaz

**Files:**
- Create: `rag-service/app/services/prompts.py`
- Create: `rag-service/tests/test_prompts.py`

- [ ] Step 1: Soru, source başlığı ve retrieval context'i prompt içine taşıyan failing testleri yaz
- [ ] Step 2: Prompt budget için `formatter_input_char_limit` kesmesini doğrulayan failing test ekle
- [ ] Step 3: Testleri çalıştır ve beklenen şekilde fail ettiğini doğrula
- [ ] Step 4: Minimal `build_query_answer_prompt()` ve fallback mesaj helper'larını yaz
- [ ] Step 5: `tests/test_prompts.py` dosyasını tekrar çalıştır ve geçir

### Task 2: LLM servis sınırını testle

**Files:**
- Create: `rag-service/app/services/llm.py`
- Create: `rag-service/tests/test_llm_service.py`

- [ ] Step 1: `generate(prompt: str) -> str` arayüzü için failing test yaz
- [ ] Step 2: Varsayılan modelin `settings.formatter_model` olduğunu doğrulayan test ekle
- [ ] Step 3: Testleri çalıştır ve fail çıktısını doğrula
- [ ] Step 4: Minimal Gemini text generation client'ını implement et
- [ ] Step 5: `tests/test_llm_service.py` dosyasını tekrar çalıştır ve geçir

## Chunk 2: Query Service Generation Flow

### Task 3: QueryService normal generate yolunu testle

**Files:**
- Modify: `rag-service/app/services/query.py`
- Modify: `rag-service/tests/test_query_service.py`

- [ ] Step 1: Retrieval source'ları varken `llm.generate()` çağrıldığını doğrulayan failing test ekle
- [ ] Step 2: `query_embedding` alanının response'ta olmadığını doğrulayan test ekle
- [ ] Step 3: Testleri çalıştır ve fail ettiğini doğrula
- [ ] Step 4: `QueryService` içine prompt builder + llm servisi enjeksiyonunu ekle
- [ ] Step 5: Başarılı generation yolunda `answer`, `sources`, `retrieval_context` döndürmeyi tamamla
- [ ] Step 6: İlgili query service testlerini tekrar çalıştır ve geçir

### Task 4: Empty ve fallback yolunu testle

**Files:**
- Modify: `rag-service/app/services/query.py`
- Modify: `rag-service/tests/test_query_service.py`

- [ ] Step 1: Kaynak yoksa `llm.generate()` çağrılmadığını ve `retrieval_mode="empty"` döndüğünü test et
- [ ] Step 2: `llm.generate()` exception fırlattığında `_fallback_answer()` devreye girdiğini test et
- [ ] Step 3: Testleri fail olarak çalıştır
- [ ] Step 4: `_compose_answer()` fonksiyonunu `_fallback_answer()` olarak rename et ve sadece hata yoluna bağla
- [ ] Step 5: Boş sonuç mesajını `prompts.py` helper'ı üzerinden dönecek şekilde düzelt
- [ ] Step 6: Query service testlerini tekrar çalıştır ve geçir

## Chunk 3: API Surface

### Task 5: `/query` response yüzeyini testle

**Files:**
- Modify: `rag-service/app/schemas/query.py`
- Modify: `rag-service/app/api/query.py`
- Modify: `rag-service/tests/test_api_endpoints.py`

- [ ] Step 1: API response'unda `query_embedding` alanının bulunmadığını doğrulayan failing test ekle
- [ ] Step 2: Generated answer ile sources uyumunu doğrulayan failing test ekle
- [ ] Step 3: Testleri çalıştır ve fail ettiğini doğrula
- [ ] Step 4: Query response schema'sını ve endpoint dönüşünü güncelle
- [ ] Step 5: API testlerini tekrar çalıştır ve geçir

## Chunk 4: Verification And Checklist

### Task 6: Hedef test paketini çalıştır

**Files:**
- Modify: `rag_service_checklist_v3.md`

- [ ] Step 1: `tests/test_prompts.py`
- [ ] Step 2: `tests/test_llm_service.py`
- [ ] Step 3: `tests/test_query_service.py`
- [ ] Step 4: `tests/test_api_endpoints.py`
- [ ] Step 5: Gerekirse `tests/test_chat_service.py` ile query surface regresyonunu doğrula
- [ ] Step 6: Ortam izin veriyorsa ilgili integration testleri çalıştır; izin vermiyorsa blokajı not et
- [ ] Step 7: `Direkt pipeline (basit soru-cevap)` maddesini checklist'te işaretle
