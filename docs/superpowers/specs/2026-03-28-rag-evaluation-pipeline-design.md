# RAG Evaluation Pipeline Design

## Status: COMPLETED

## Amaç

RAG sisteminin retrieval ve answer kalitesini ölçülebilir hale getirmek.

Hedef:

- örnek soru setleri üzerinde query pipeline'ı toplu çalıştırmak
- kalite metrikleri üretmek
- sonuçları saklamak ve raporlamak

## Kapsam

Kapsam içi:

- evaluation run başlatma API'si
- async evaluation worker job
- run ve sample sonuçlarının kalıcı saklanması
- temel metrikler:
  - `faithfulness`
  - `answer_relevancy`
  - `context_recall`

Kapsam dışı:

- gerçek zamanlı dashboard
- insan onayı arayüzü
- production request başına online scoring

## Current State

- query pipeline production-ready seviyede çalışıyor
- staging, callback, observability, rate limit, rerank ve hybrid retrieval mevcut
- ama kaliteyi toplu ve tekrar edilebilir şekilde ölçen bir evaluation sistemi yok

## Seçilen Yaklaşım

Merkezde async job, üstte API trigger.

Yani:

- `POST /evaluations` evaluation run başlatır
- iş ARQ kuyruğuna gider
- worker her sample için mevcut query pipeline'ı çalıştırır
- sonuçlar DB'ye yazılır

## Tasarım

### 1. Veri modeli

Yeni tablolar:

- `rag_evaluation_runs`
- `rag_evaluation_samples`

`rag_evaluation_runs`:

- `id`
- `application_id`
- `status`
- `dataset_name`
- `sample_count`
- `completed_count`
- ortalama metrik alanları
- `created_at`, `completed_at`

`rag_evaluation_samples`:

- `id`
- `run_id`
- `question`
- `ground_truth`
- `reference_context`
- `model_answer`
- `retrieved_context`
- `faithfulness_score`
- `answer_relevancy_score`
- `context_recall_score`
- `error_message`

### 2. API yüzeyi

Yeni endpoint:

- `POST /evaluations`

Payload:

- `dataset_name`
- `samples[]`

Her sample:

- `question`
- `ground_truth`
- `reference_context`

Opsiyonel ikinci endpoint:

- `GET /evaluations/{run_id}`

Bu ilk sürümde faydalıdır çünkü job sonucu polling ile izlenebilir.

### 3. Worker akışı

Run başlatıldığında:

1. run row açılır
2. worker job enqueue edilir
3. worker her sample için:
   - mevcut `QueryService.answer_question()` çalıştırır
   - answer ve retrieved context'i alır
   - metric evaluator ile skorlar
   - sample result row yazar
4. tüm sample'lar bitince run ortalamaları güncellenir

### 4. Metrik stratejisi

İlk production-ready sürümde iki katman önerilir:

- deterministic baseline
- opsiyonel LLM judge

İlk implementasyon:

- `answer_relevancy`
  - ground truth ile answer arasında basit lexical/semantic benzerlik yaklaşımı
- `context_recall`
  - reference context terimlerinin retrieved context içinde bulunma oranı
- `faithfulness`
  - answer terimlerinin retrieved context ile örtüşme oranına dayalı basit heuristic

Not:

Checklist'te RAGAS yazıyor, ama ilk production-ready sürümde tam RAGAS entegrasyonu zorunlu değil.
Önemli olan pipeline ve veri modeli doğru kurulmasıdır. Sonraki iterasyonda gerçek RAGAS evaluator ya da LLM judge eklenebilir.

### 5. Servis sınırları

Yeni servis:

- `app/services/evaluations.py`

Sorumluluk:

- run oluşturma
- sample bazlı query çalıştırma
- metric hesaplama
- run özetini güncelleme

Worker entegrasyonu:

- `workers/tasks/evaluations.py`

### 6. Observability

Log alanları:

- `evaluation_run_id`
- `dataset_name`
- `sample_count`
- `completed_count`
- ortalama metrikler

Tam question/ground_truth verisi loglanmaz.

## Hata davranışı

- tek sample hata verirse run tamamen çökmez
- sample row `error_message` ile yazılır
- run devam eder
- run sonunda başarısız sample'lar dahil özet çıkar

## Testing

Eklenecek testler:

- evaluation run oluşturma
- worker sample'ları işleyip result row yazıyor
- ortalama skorlar hesaplanıyor
- sample failure run'ı bozmaz
- status endpoint sonucu döndürüyor

## Başarı Kriteri

- API ile evaluation başlatılabiliyor
- worker mevcut query pipeline üzerinden dataset'i çalıştırabiliyor
- her sample ve run sonucu kalıcı olarak saklanıyor
- en az üç kalite metriği üretiliyor
