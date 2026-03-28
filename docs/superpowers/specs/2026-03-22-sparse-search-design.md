# Sparse Search Design

## Status: COMPLETED

## Goal

`/query` akışına production-ready sparse retrieval eklemek. Hedef, dense aramadan bağımsız olarak Qdrant üzerinde keyword ağırlıklı arama çalıştırmak ve sonraki `RRF fusion` adımı için doğru temeli hazırlamak.

## Scope

Bu dilimde sadece `Sparse search — BM25 → Qdrant` tamamlanır.

Kapsam dışı:
- Dense + sparse birleştirme
- Reranker
- Multi-collection query
- ACL genişletmeleri

## Current State

- Dense retrieval zaten `QueryService` içinde `embed_query_text` + `QdrantVectorStore.search_chunks` ile çalışıyor.
- Metadata fallback halen basit keyword eşleşmesi ile yapılıyor.
- Qdrant collection şu an yalnızca dense vector alanı ile oluşturuluyor.
- Ingestion sırasında chunk upsert payload'ına text metadata gidiyor ama sparse index girişi üretilmiyor.

## Recommended Approach

Qdrant üzerinde named dense + sparse vector kullanmak.

Neden:
- Dense ve sparse aynı motor üzerinde filtrelenir.
- Sonraki `RRF fusion` ve rerank adımları daha temiz eklenir.
- PostgreSQL FTS ya da uygulama içi BM25 gibi ikinci bir retrieval sistemi yaratılmaz.

## Data Model

Collection iki vektör alanı taşıyacak:
- `dense`: mevcut 768 boyutlu cosine dense vector
- `sparse`: text chunk için sparse vector

Upsert sırasında her text chunk için:
- dense vector mevcut embedder çıktısından gelir
- sparse vector, chunk text'inden tokenizer ile üretilir

Image/audio gibi text taşımayan chunk'larda sparse vector yazılmaz.

## Sparse Encoding

İlk production-ready sürüm için harici model bağımlılığı eklenmeden deterministik bir sparse encoder kullanılacak:
- normalize: lowercase
- tokenize: alfanumerik token çıkar
- stopword temizliği
- token frequency hesapla
- vocab id üretimi: stabil hash tabanlı integer mapping
- sparse vector formatı: `indices[]`, `values[]`

Bu gerçek BM25'in tüm ayrıntılarını taşımaz; fakat Qdrant sparse retrieval için production kullanılabilir bir lexical temel sağlar. Checklist metnindeki BM25 beklentisi için sonraki iterasyonda IDF/length normalization eklenebilir. Bu dilimde hedef, stable sparse lexical retrieval altyapısıdır.

## Query Flow

`QueryService.answer_question()` içinde:
- dense embedding alınmaya devam eder
- yeni sparse query encoder soru metninden sparse vector üretir
- query parametresi ya da servis seçimi ile sparse retrieval çağrılır
- sparse sonuçlar `retrieval_mode="sparse_qdrant"` ile döner

Bu dilimde mevcut `/query` endpoint davranışı bozulmamalı. Varsayılanı dense olarak bırakıp servis içinde sparse retrieval için ayrı method eklenecek. API yüzeyinde retrieval seçimi küçük bir parametre ile açılabilir.

## API Shape

`QueryRequest` içine opsiyonel alan eklenir:
- `retrieval_mode`: `dense | sparse`

Varsayılan: `dense`

Bu sayede:
- mevcut istemciler kırılmaz
- sparse retrieval ayrı test edilebilir
- sonraki `hybrid` ya da `rrf` modu aynı alana eklenebilir

## Service Boundaries

- `app/services/sparse_encoder.py`
  Sparse tokenization ve vector üretimi.
- `app/services/vector_store.py`
  Named dense+sparse collection setup, sparse upsert ve sparse query desteği.
- `app/services/ingestion.py`
  Text chunk upsert payload'ına sparse vector ekleme.
- `app/services/query.py`
  Sparse retrieval branch ve cevap üretimi.
- `app/schemas/query.py`
  Yeni request enum alanı.

## Error Handling

- Sparse query oluşturulamıyorsa boş sparse vector ile sorgu atılmaz; metadata fallback'a düşülür.
- Qdrant sparse query HTTP hatasında servis çökmek yerine mevcut fallback davranışını korur.
- Text olmayan chunk'lar sparse index dışında bırakılır.

## Testing

- Sparse encoder tokenization ve deterministik output testleri
- Qdrant collection payload'ında named vector + sparse_vectors konfigürasyonu testi
- Qdrant upsert payload'ında sparse vector alanı testi
- Qdrant sparse query payload testi
- QueryService sparse mode testi
- API `/query` sparse mode geçiş testi

## Rollout

Bu dilim sonunda:
- checklist'te `Sparse search` kapanır
- `RRF fusion` açık kalır
- dense varsayılan davranış korunur
- sparse retrieval production akışında çağrılabilir hale gelir
