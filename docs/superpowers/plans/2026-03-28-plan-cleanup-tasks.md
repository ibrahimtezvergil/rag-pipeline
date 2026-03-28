# Plan Cleanup Tasks Implementation Plan

## Status: COMPLETED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** docs/superpowers altındaki eski ve tamamlanmış plan/spec dokümanlarını archive, status ve terminology açısından güncel repo durumuyla hizalamak.

**Architecture:** Önce dosya sınıflandırması netleştirilecek: orphan legacy planlar archive'a taşınacak, meta-planlar archive veya index olarak işaretlenecek, tamamlanan aktif plan/spec dosyalarına completed status eklenecek, son olarak application terminology cleanup yapılacak. Değişiklikler yalnızca doküman yüzeyinde kalacak; kod veya migration dokunulmayacak.

**Tech Stack:** Markdown docs, git mv, rg, pytest yok (docs-only verification + git diff)

---

## Chunk 1: Archive ve index temizlikleri

### Task 1: Orphan legacy planları archive'a taşı
- [x] `docs/superpowers/plans/archive/` klasörünü oluştur.
- [x] 7 legacy planı archive altına `git mv` ile taşı.
- [x] Gerekirse archive README/notu ekleme ihtiyacını değerlendir.

### Task 2: Meta-planları archive veya index olarak işaretle
- [x] `2026-03-22-p2-ingestion-pipeline.md` ve `2026-03-22-p3-query-pipeline.md` için karar uygula.
- [x] En düşük riskli yol olarak dosyaları yerinde bırakıp başlarına superseded/index notu ekle veya archive'a taşı.

## Chunk 2: Completed status güncellemeleri

### Task 3: Completed plan dosyalarını işaretle
- [x] Cleanup listesinde tamamlanmış görünen plan dosyalarına status başlığı ekle.
- [x] Kısa ve tek satırlık `COMPLETED` formatı kullan.

### Task 4: Completed spec dosyalarını işaretle
- [x] Matching spec dosyalarına aynı status başlığını ekle.
- [x] Header yapısını bozmadan yalnızca minimal ekleme yap.

## Chunk 3: Terminology cleanup

### Task 5: Aktif referans verilen doc'larda application terminology düzelt
- [x] `project_id`, `rag_projects`, `project config` gibi aktif kalan terimleri tarayıp yalnızca aktif plan/spec setinde değiştir.
- [x] Legacy/archive adaylarında zorunlu rename yapma.

### Task 6: Cleanup plan dosyasını son duruma göre güncelle ve doğrula
- [x] `docs/superpowers/plan-cleanup-tasks.md` içinde sayıları/aksiyonları son gerçek durumla hizala.
- [x] `rg`, `git diff`, basit içerik kontrolleri ile doğrula.
