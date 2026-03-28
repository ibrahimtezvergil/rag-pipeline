# Query Expansion Design

## Status: COMPLETED

## Goal

Retrieval öncesinde sorguyu kontrollü biçimde genişleterek synonym ve ifade varyasyonlarını daha iyi yakalamak. Hedef, dense/sparse/hybrid retrieval kalitesini artırmak ve bunu düşük riskli, production-ready bir akışla yapmak.

## Scope

Bu dilimde iki kademeli query expansion tasarlanır:
- deterministic synonym expansion
- opsiyonel LLM rewrite

Kapsam içi:
- expansion servisi
- synonym dictionary tabanlı terim genişletme
- config ile açılıp kapanabilen LLM rewrite
- retrieval input'una expanded query verme

Kapsam dışı:
- çok adımlı self-RAG rewrite
- tenant bazlı özel synonym yönetim UI'ı
- kullanıcıya expansion detayını response'ta gösterme
- ayrı expansion observability dashboard'u

## Current State

- `QueryService.answer_question()` retrieval için doğrudan kullanıcının verdiği `question` değerini kullanıyor.
- Dense embedding, sparse encoding, metadata fallback ve prompt generation aynı ham soru üzerinden ilerliyor.
- Query tarafında synonym veya rewrite katmanı yok.
- `answer` prompt'unda orijinal soru kullanılıyor; bu davranış korunmalı.

## Recommended Approach

Synonym-first, LLM rewrite optional model.

Neden:
- deterministic expansion ucuz, hızlı ve öngörülebilir
- LLM rewrite kaliteyi artırabilir ama hata/maliyet riski taşır
- varsayılanı synonym-only tutarak production güvenliği korunur
- aynı servis sınırı içinde ikinci aşama sonradan açılabilir

## Target Flow

`question`
-> normalize
-> synonym expansion
-> optional LLM rewrite
-> `expanded_query`
-> dense embed + sparse encode + metadata fallback retrieval
-> rerank
-> answer generation

Önemli kural:
- answer generation için prompt builder'a hâlâ orijinal kullanıcı sorusu gider
- expanded query sadece retrieval input'udur

## Expansion Contract

Yeni servis:
- `app/services/query_expansion.py`

Arayüz:
- `async def expand(question: str, *, use_llm: bool = False) -> ExpandedQuery`

Örnek çıktı modeli:
- `original_question`
- `expanded_query`
- `synonyms_applied`
- `rewrite_applied`

İlk sürümde bu model internal olabilir; response'a açılması zorunlu değildir.

## Synonym Expansion

Deterministic dictionary tabanı:
- küçük, sabit, kod içi sözlük
- sadece yüksek güvenli business/search terimleri

Örnek:
- `invoice -> billing, payment`
- `renewal -> extension, contract renewal`
- `customer -> client, account`

Kurallar:
- duplicate terimler kaldırılır
- original term korunur
- maksimum ek terim sayısı düşük tutulur, örn. `5`
- query çok büyürse truncation uygulanır

## LLM Rewrite

LLM rewrite varsayılan kapalıdır.

Config önerisi:
- `query_expansion_use_llm: bool = False`
- `query_expansion_max_terms: int = 5`

Davranış:
- synonym expansion sonrası kısa rewrite prompt'u çalışır
- amaç: anlamı koruyarak retrieval için daha aranabilir bir alternatif ifade üretmek
- çıktı tek satır kısa arama cümlesi olur

Fallback:
- LLM timeout / provider / circuit breaker hatasında synonym-only query ile devam edilir

## Service Boundaries

- `app/services/query_expansion.py`
  Expansion mantığı burada tutulur.
- `app/services/query.py`
  Retrieval öncesi expansion servisini çağırır; dense/sparse/metadata fallback için expanded query kullanır.
- `app/services/llm.py`
  Yeni provider katmanı açılmaz; mevcut generate servisi kısa rewrite prompt'u için yeniden kullanılabilir.
- `app/config.py`
  Expansion config alanları eklenir.

## Error Handling

- synonym sözlüğünde eşleşme yoksa:
  - expanded query = original question
- LLM kapalıysa:
  - synonym-only devam
- LLM hata verirse:
  - synonym-only devam
- expansion sonucu boş veya anlamsızsa:
  - original question korunur

## Testing

- synonym expansion belirlenen terimleri ekler
- duplicate ve aşırı uzun expansion temizlenir
- `QueryService` dense/sparse retrieval için expanded query kullanır
- answer prompt hâlâ orijinal kullanıcı sorusunu alır
- LLM rewrite hata verirse synonym-only fallback olur

## Rollout

Bu dilim sonunda checklist'te şu madde kapanır:
- `Query expansion — sinonim sözlüğü + LLM genişletme`

Sonraki mantıklı adım:
- `Langfuse @observe` veya retrieval kalite iyileştirmeleri
