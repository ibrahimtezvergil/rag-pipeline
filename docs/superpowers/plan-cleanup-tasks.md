# Plan & Spec Dosyaları — Temizlik Görevleri

**Tarih:** 2026-03-28
**Kaynak:** 38 plan, 29 spec, checklist v3 review

---

## 1. Orphan Planları Archive'a Taşı

7 legacy plan dosyası aktif spec→plan modelinin dışında kaldı. Mart 15 tarihli eski phase/slice yaklaşımından kalma; Mart 22'den itibaren bireysel spec→plan modeline geçildi. Hepsi ya superseded ya da bireysel spec+plan çiftleri tarafından absorbe edildi.

**Hedef:** `docs/superpowers/plans/archive/` altına taşı.

| Dosya | Neden Orphan |
|---|---|
| `2026-03-15-p1-foundation.md` | P1 tamamlandı, checklist'te 83 [x] |
| `2026-03-15-rag-service-ingest-slice.md` | p2-ingestion-pipeline + bireysel planlar ile absorbe edildi |
| `2026-03-15-rag-service-loaders-slice.md` | web-image-audio-loaders ile absorbe edildi |
| `2026-03-15-rag-service-queue-slice.md` | p2-ingestion-pipeline Task 8 ile absorbe edildi |
| `2026-03-15-rag-service-web-image-audio-loaders.md` | Loader'lar implement edildi (image, audio, web) |
| `2026-03-15-structured-ingest.md` | SummaryFormatter implement edildi |
| `2026-03-15-structured-llm-formatter.md` | LLM semantic path implement edildi |

---

## 2. Meta-Planları Archive'a Taşı veya Index'e Dönüştür

`p2-ingestion-pipeline.md` (10 task) ve `p3-query-pipeline.md` (9 task) meta-plan olarak yazıldı. Aynı scope'un her parçası bireysel spec+plan çifti olarak mevcut ve implement edilmiş.

**Hedef:** Archive'a taşı veya içlerini "bu task şu plan ile tamamlandı" referanslarına dönüştür.

| Dosya | Durum |
|---|---|
| `2026-03-22-p2-ingestion-pipeline.md` | 10 task — hepsi bireysel planlarda karşılığı var |
| `2026-03-22-p3-query-pipeline.md` | 9 task — hepsi bireysel planlarda karşılığı var |

**P2 task → bireysel plan eşleştirmesi:**
- Task 4 (Sparse Encoder) → `sparse-search` spec+plan
- Task 2 (Chunker) → `adaptive-chunking` spec+plan
- Task 7 (Vector reuse) → `chunk-diff-and-reuse` spec+plan
- Task 6-7 (Versioning) → `document-versioning` spec+plan
- Task 7 (Embed version) → `embedding-versioning` spec+plan
- Task 6 (Checkpoints) → `sync-checkpoints` spec+plan
- Task 5-7 (Dedup) → `semantic-deduplication` spec+plan

**P3 task → bireysel plan eşleştirmesi:**
- Task 5 (LLM answer) → `direct-query-pipeline` spec+plan
- Task 2-3 (Sparse query) → `sparse-search` spec+plan
- Task 4-6 (Circuit breaker) → `circuit-breaker` spec+plan
- Task 5-7 (Confidence) → `confidence-score` spec+plan
- Task 5 (Expansion) → `query-expansion` spec+plan
- Task 5-7 (Cache) → `query-cache` spec+plan
- Task 5-6 (Logging) → `observability-logging` spec+plan
- Task 5-7 (Tracing) → `langfuse-observe` spec+plan

---

## 3. Tamamlanan Planları COMPLETED Olarak İşaretle

Checklist'te `[x]` olan maddeler implement edilmiş ama plan dosyalarında task'lar hâlâ `[ ]` PENDING. Tutarsızlık oluşturuyor.

**Hedef:** Her tamamlanan plan dosyasının başına `## Status: COMPLETED — 2026-03-XX` ekle.

| Plan Dosyası | Checklist Durumu |
|---|---|
| `2026-03-22-sparse-search.md` | [x] L88-89 |
| `2026-03-22-direct-query-pipeline.md` | [x] L98 |
| `2026-03-22-observability-logging.md` | [x] L127-130 |
| `2026-03-22-rate-limiting.md` | [x] L135 |
| `2026-03-22-circuit-breaker.md` | [x] L136 |
| `2026-03-22-confidence-score.md` | [x] L137 |
| `2026-03-22-query-expansion.md` | [x] L138 |
| `2026-03-23-langfuse-observe.md` | [x] L106 |
| `2026-03-23-query-cache.md` | [x] L116-117 |
| `2026-03-23-document-versioning.md` | [x] L120 |
| `2026-03-23-chunk-hash-dedup.md` | [x] (feasibility lock, merged) |
| `2026-03-23-chunk-diff-and-reuse.md` | [x] L121-122 |
| `2026-03-23-sync-checkpoints.md` | [x] L124 |
| `2026-03-23-scheduled-reindex.md` | [x] L123 |
| `2026-03-23-embedding-versioning.md` | [x] L130 |
| `2026-03-23-semantic-deduplication.md` | [x] L145 |
| `2026-03-23-adaptive-chunking.md` | [x] L146 |
| `2026-03-23-qdrant-post-filtering-fetch.md` | [x] L151 |
| `2026-03-23-pgbouncer.md` | [x] L153 |
| `2026-03-23-production-smoke-blockers.md` | [x] (Deploy dogrulama notu L378+) |
| `2026-03-27-budget-enforcement.md` | [x] L110-111 |
| `2026-03-28-application-domain-refactor.md` | [x] Terminology refactor merge edildi |
| `2026-03-28-audio-metadata-pipeline.md` | [x] L143 |
| `2026-03-28-document-relationship.md` | [x] L164 |
| `2026-03-28-feedback-loop.md` | [x] L158 |
| `2026-03-28-ingestion-webhook-callback.md` | [x] L144 |
| `2026-03-28-rag-evaluation-pipeline.md` | [x] L157 |
| `2026-03-28-staging-environment.md` | [x] L170 |

**Aynı şekilde matching spec dosyaları da:**

| Spec Dosyası | Durum |
|---|---|
| `2026-03-22-sparse-search-design.md` | COMPLETED |
| `2026-03-22-direct-query-pipeline-design.md` | COMPLETED |
| `2026-03-22-observability-logging-design.md` | COMPLETED |
| `2026-03-22-rate-limiting-design.md` | COMPLETED |
| `2026-03-22-circuit-breaker-design.md` | COMPLETED |
| `2026-03-22-confidence-score-design.md` | COMPLETED |
| `2026-03-22-query-expansion-design.md` | COMPLETED |
| `2026-03-23-langfuse-observe-design.md` | COMPLETED |
| `2026-03-23-query-cache-design.md` | COMPLETED |
| `2026-03-23-document-versioning-design.md` | COMPLETED |
| `2026-03-23-chunk-hash-dedup-design.md` | COMPLETED |
| `2026-03-23-chunk-diff-and-reuse-design.md` | COMPLETED |
| `2026-03-23-sync-checkpoints-design.md` | COMPLETED |
| `2026-03-23-scheduled-reindex-design.md` | COMPLETED |
| `2026-03-23-embedding-versioning-design.md` | COMPLETED |
| `2026-03-23-semantic-deduplication-design.md` | COMPLETED |
| `2026-03-23-adaptive-chunking-design.md` | COMPLETED |
| `2026-03-23-qdrant-post-filtering-fetch-design.md` | COMPLETED |
| `2026-03-23-pgbouncer-design.md` | COMPLETED |
| `2026-03-23-production-smoke-blockers-design.md` | COMPLETED |
| `2026-03-27-budget-enforcement-design.md` | COMPLETED |
| `2026-03-28-application-domain-refactor-design.md` | COMPLETED |
| `2026-03-28-audio-metadata-pipeline-design.md` | COMPLETED |
| `2026-03-28-document-relationship-design.md` | COMPLETED |
| `2026-03-28-feedback-loop-design.md` | COMPLETED |
| `2026-03-28-ingestion-webhook-callback-design.md` | COMPLETED |
| `2026-03-28-rag-evaluation-pipeline-design.md` | COMPLETED |
| `2026-03-28-staging-environment-design.md` | COMPLETED |

---

## 4. Terminology Cleanup

`project -> application` refactor kod ve checklist seviyesinde tamamlandı. Bu temizlikte aktif referans verilen plan/spec setindeki kalan `project_id`, `rag_projects`, `project config` terimleri de düzeltildi.

**Kapsanan dosyalar:**

| Dosya | Düzeltilen Terminoloji |
|---|---|
| `2026-03-27-budget-enforcement-design.md` | `rag_projects.config`, `project config` |
| `2026-03-28-feedback-loop-design.md` | `project_id`, `project disi chunk` |
| `2026-03-28-ingestion-webhook-callback-design.md` | payload içinde `project_id` |
| `2026-03-28-rag-evaluation-pipeline-design.md` | `project_id` |
| `2026-03-23-langfuse-observe-design.md` | metadata alanlarında `project_id` |
| `2026-03-22-rate-limiting-design.md` | `rate_limit:{project_id}`, checklist metni |

**Not:** Mart 15 ve bazı Mart 22 legacy planlarında `project` terimi korunabilir; archive altına taşınan dosyalarda toplu rename yapılmadı.

---

## 5. Detay Tutarsızlıkları

### 5a. p1-foundation duplicate

`2026-03-15-p1-foundation.md` ve `2026-03-15-rag-service-p1-foundation.md` ayni hedefe yonelik iki farkli dokumandi. Ikinci dosyanin matching spec'i de vardi: `2026-03-15-rag-service-p1-foundation-design.md`. Bu cift archive altina tasindi; duplicate/superseded olarak ele alindi.

### 5b. loaders-slice vs web-image-audio-loaders

Sequential plan'lar (Phase 1: basic web/pdf, Phase 2: crawl4ai + multimodal). Duplicate degil ama ikisi de superseded kabul edilip archive altina tasindi.

### 5c. chunk-hash-dedup feasibility lock

`chunk-hash-dedup` plan'i bir feasibility lock olarak yazildi ve `chunk-diff-and-reuse` ile merge edildi. Ikisi de COMPLETED; archive/index notunda bu iliski korunmali.

---

## Ozet

| Aksiyon | Dosya Sayisi / Not |
|---|---|
| Archive'a tasi (orphan planlar) | 7 |
| Archive'a tasi veya index'e donustur (meta-planlar) | 2 |
| Archive notu ekle (duplicate foundation cifti) | 2 plan + 1 spec |
| COMPLETED olarak isaretle (plan) | 28 |
| COMPLETED olarak isaretle (spec) | 28 |
| Terminology cleanup | 6 aktif doc duzeltildi |
