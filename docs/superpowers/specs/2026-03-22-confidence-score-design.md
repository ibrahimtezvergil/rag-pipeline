# Confidence Score Design

## Status: COMPLETED

## Goal

`/query` ve buna bağlı cevap akışına basit ama production-ready bir güven sinyali eklemek. Hedef, retrieval sonucunun ne kadar güçlü göründüğünü sayısal olarak döndürmek ve düşük güven durumunda UI katmanının kullanabileceği kısa bir uyarı sağlamaktır.

## Scope

Bu dilimde yalnızca response seviyesinde confidence alanları eklenir.

Kapsam içi:
- `confidence_score` response alanı
- `confidence_warning` response alanı
- mevcut source skorlarından confidence türetme
- düşük güven eşiği altında warning üretimi

Kapsam dışı:
- answer metnine otomatik warning prefix eklemek
- LLM tabanlı confidence
- calibration / offline evaluation
- observability event payload'ına confidence yazmak

## Current State

- `QueryService` final source listesinde `score` alanı taşıyor.
- score kaynağı retrieval moduna göre değişiyor:
  - dense: Qdrant dense score
  - sparse/hybrid: sparse veya RRF türevi score
  - rerank: Cohere relevance score
- query observability log'unda `top_chunk_score` var, ama API response'ta confidence özeti yok.
- UI bugün düşük güven ile yüksek güven cevabı ayırt etmek için ek backend sinyal almıyor.

## Recommended Approach

Response-only confidence alanları eklemek.

Neden:
- backend answer içeriğine sunum kararı gömmez
- farklı istemciler aynı alanı farklı biçimde kullanabilir
- mevcut retrieval skorlarını yeniden kullanır; düşük riskli ve hızlı

## Response Contract

`app/schemas/query.py`

`QueryResponse` ve `ChatResponse` alanları:
- `confidence_score: float | None`
- `confidence_warning: str | None`

Davranış:
- hesaplanabilir skor varsa `confidence_score` dolar
- düşük güven durumunda `confidence_warning` kısa sabit mesaj döner
- yeterli skor yoksa iki alan da `None` olabilir

## Confidence Calculation

İlk sürümde confidence, final `sources` içindeki skorların ortalamasından türetilir.

Adımlar:
1. `final_sources` içinden numeric `score` alanları toplanır
2. her skor helper ile normalize edilir
3. normalize skorların ortalaması alınır
4. sonuç `0.0 .. 1.0` aralığında döner

Normalize yaklaşımı:
- `0.0 <= score <= 1.0` ise aynen kullan
- `score > 1.0` ise retrieval family farklarını fazla büyütmemek için saturating dönüşüm uygulanır:
  - öneri: `score / (score + 1.0)`

Bu yaklaşım:
- dense / rerank skorlarını bozmadan korur
- sparse / RRF gibi `>1` ya da dağılımı farklı skorları güven sinyaline daraltır
- ilk production sürümü için yeterince stabil ve açıklanabilir kalır

## Warning Policy

İlk sürümde tek eşik yeterlidir:
- `confidence_score < 0.35` ise warning döner

Örnek warning:
- `"Bu yanit dusuk guvenle olusturuldu; kaynaklari kontrol edin."`

Kurallar:
- warning yalnızca structured field olur
- `answer` metni değiştirilmez
- `retrieval_mode="empty"` ise warning yerine mevcut empty flow korunur

## Service Boundaries

- `app/services/query.py`
  Confidence hesaplama ve warning üretimi burada yapılır; final response oluşturulurken eklenir.
- `app/schemas/query.py`
  Response modellerine yeni alanlar eklenir.
- `app/services/prompts.py`
  Bu dilimde değişmez; confidence warning prompt katmanına taşınmaz.

## Error Handling

- source skorlarının hiçbiri numeric değilse:
  - `confidence_score = None`
  - `confidence_warning = None`
- retrieval boşsa:
  - mevcut empty response korunur
  - confidence alanları `None`
- LLM fallback yolunda:
  - source varsa confidence yine hesaplanır

## Testing

- `QueryService` numeric source skorlarından normalize confidence hesaplar
- `score > 1.0` durumunda saturating normalize uygulanır
- düşük confidence eşiğinde warning döner
- empty response'ta confidence alanları `None`
- API response şeması yeni alanları içerir

## Rollout

Bu dilim sonunda checklist'te şu madde kapanır:
- `Confidence score — top chunk score ortalaması, düşükse uyarı`

Sonraki mantıklı adım:
- `Query expansion`
