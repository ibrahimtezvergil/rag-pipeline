# Budget Enforcement Design

## Status: COMPLETED

## Amaç

`rag_applications.config` içindeki `latency_budget_ms` ve `token_budget` alanlarını çalışan query pipeline'a bağlamak.

Hedef:

- latency budget düşükse LLM generate aşamasına girmeden kontrollü fallback dönmek
- token budget düşükse retrieval context ve parent context'i kademeli kırpmak
- mevcut hybrid retrieval, rerank ve source-backed answer davranışını bozmamak

## Kapsam

Bu dilim sadece query ve chat cevap üretim akışını kapsar.

Kapsam içi:

- `QueryService.answer_question`
- `ChatService` üzerinden dolaylı query akışı
- application config'ten budget okuma
- observability alanları
- ilgili testler

Kapsam dışı:

- LangGraph budget orchestration
- model-specific gerçek tokenization
- streaming response budget yönetimi
- ingest pipeline budget enforcement

## Current State

- `rag_applications.config` içinde `latency_budget_ms` ve `token_budget` alanları için şema zemini var.
- Query akışı retrieval, rerank ve generate adımlarını çalıştırıyor ama bu budget'ları enforce etmiyor.
- Prompt bütçesi için formatter tarafında char limit yaklaşımı var; query tarafı bu mantığı doğrudan application config ile kullanmıyor.

## Yaklaşım

Seçilen model:

- hard latency budget
- soft token budget

Gerekçe:

- latency aşımı üretimde maliyet ve kullanıcı deneyimi açısından en kritik risk
- token budget için erken sert kesme yerine degrade etmek daha güvenli
- böylece retrieval ve sources korunur, sadece generate davranışı bütçeye göre uyarlanır

## Tasarım

### 1. Latency budget

`QueryService.answer_question` query başlangıcında `perf_counter()` ile zamanlamayı başlatır.

Akış:

1. retrieval ve rerank sonrası geçen süre hesaplanır
2. application config'ten `latency_budget_ms` alınır
3. generate'e girmeden önce kalan süre hesaplanır
4. kalan süre tanımlı minimum generate eşiğinin altındaysa LLM çağrısı yapılmaz
5. `_fallback_answer()` çalışır
6. sources ve retrieval_context korunur

İlk sürüm kuralı:

- `remaining_ms <= 0` ise doğrudan fallback
- opsiyonel güvenlik payı:
  - `remaining_ms < 250` ise de fallback

Response davranışı:

- `retrieval_mode` korunur
- response içine yeni bir alan eklenmez
- observability/tracing metadata budget hit bilgisini taşır

### 2. Token budget

`token_budget` application config'ten okunur.

İlk sürüm approx token hesabı:

- `estimated_tokens = len(text) // 4`

Akış:

1. sources ve parent context build edilir
2. generate öncesi prompt input yaklaşık token hesabına sokulur
3. budget aşılırsa aşağıdaki sırayla kırpma yapılır:
   - source sayısını azalt
   - her source için parent context'i kısalt
   - snippet uzunluklarını azalt
4. hala aşıyorsa sadece en iyi 1 source ile prompt kur
5. yine aşıyorsa fallback answer'a düşme yok; minimal prompt ile generate denenir

Bu yapı token budget'ı soft enforce eder.

### 3. Servis sınırları

- `app/services/query.py`
  - budget çözümleme
  - latency gate
  - token trimming
  - observability metadata
- `app/services/prompts.py`
  - mevcut prompt builder korunur
  - gerekirse kırpılmış sources ile aynı interface'i kullanır
- `app/services/chat.py`
  - doğrudan ek mantık taşımaz; query sonucu zaten budget'lı gelir

## Config kontratı

Project config örneği:

```json
{
  "latency_budget_ms": 1200,
  "token_budget": 2000
}
```

Yorum:

- alan yoksa mevcut davranış korunur
- `null` veya `<= 0` ise enforcement kapalı kabul edilir

## Observability

Query completed event ve trace metadata içine şu alanlar eklenir:

- `latency_budget_ms`
- `latency_budget_hit`
- `remaining_budget_ms`
- `token_budget`
- `token_trimmed`
- `prompt_estimated_tokens`

Ham prompt veya tam content loglanmaz.

## Hata ve fallback davranışı

- latency budget hit:
  - LLM çağrısı yok
  - `_fallback_answer()` döner
- token budget hit:
  - context kırpılır
  - generate yine denenir
- config parse sorunu:
  - güvenli biçimde enforcement yokmuş gibi davranılır

## Testing

Eklenecek testler:

- latency budget kalan süreyi aşınca `generate_text()` çağrılmaz
- latency budget hit olduğunda fallback answer döner
- token budget düşükse source listesi kırpılmış prompt ile generate edilir
- budget alanları yoksa mevcut davranış korunur
- query completed event budget metadata taşır
- chat akışı query tarafındaki budget enforcement'tan etkilenir

## Başarı Kriteri

- `latency_budget_ms` aktif project'te yavaş generate aşaması kontrollü biçimde atlanır
- `token_budget` aktif project'te prompt boyutu yaklaşık limit içine çekilir
- budget yoksa eski davranış korunur
- mevcut query/chat testleri bozulmadan yeni testler geçer
