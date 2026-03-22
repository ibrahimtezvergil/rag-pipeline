# Direct Query Pipeline Design

## Goal

`/query` akışını retrieval-only yapıdan çıkarıp production-ready, kaynak dayalı tek seferlik soru-cevap hattına dönüştürmek. Hedef, mevcut hybrid retrieval + rerank çıktısını güvenli bir prompt ile LLM'e verip kullanıcıya anlamlı cevap döndürmek.

## Scope

Bu dilimde sadece basit soru-cevap pipeline tamamlanır.

Kapsam içi:
- retrieval context'ten answer generation
- provider abstraction üstünden LLM cevap üretimi
- source-backed güvenli prompt
- kaynak yoksa güvenli fallback yanıt

Kapsam dışı:
- LangGraph orchestration
- self-RAG classify/rewrite/grade akışı
- streaming
- multi-turn agent davranışı

## Current State

- `QueryService` hybrid retrieval, sparse, rerank, ACL ve parent-child çözümlemesini yapıyor.
- `_compose_answer()` (`query.py:615`) snippet'leri string birleştirmesi ile cevap oluşturuyor — gerçek LLM çağrısı yok.
- `answer_question()` response'unda `query_embedding` (768-dim vektör) dönüyor; client'a gitmemeli.
- Gerçek answer generation katmanı yok; retrieval context doğrudan son kullanıcı cevabına dönmüyor.

## Recommended Approach

Mevcut `QueryService` üstüne ince bir generation katmanı eklemek.

Neden:
- Bugünkü servis sınırlarını bozmaz.
- Retrieval yatırımı korunur.
- Sonraki `LangGraph` geçişinde generate adımı yeni orchestration içine taşınabilir.

## Target Flow

`POST /query`
-> auth + project resolve
-> hybrid retrieve
-> optional rerank
-> source list + retrieval context
-> prompt build
-> LLM generate
-> answer + sources + retrieval metadata

Eğer retrieval sonucu boşsa:
- LLM çağrısı yapılmaz
- güvenli fallback cevap döner

## Prompt Contract

Prompt şu kuralları zorunlu taşır:
- yalnızca verilen kaynaklara dayan
- kaynakta olmayan bilgiyi uydurma
- cevap kısa ve doğrudan olsun
- mümkünse kaynak başlıklarını kullan
- yeterli bilgi yoksa bunu açıkça söyle

Prompt input'u:
- kullanıcı sorusu
- top retrieval context blokları
- kaynak başlığı ve metadata özeti

## Service Boundaries

- `app/services/query.py`
  Retrieval akışını korur, generation adımını çağırır. `_compose_answer()` → `_fallback_answer()` olarak rename edilir; normal yolda kullanılmaz, yalnızca `llm.generate()` exception fırlattığında devreye girer.
- `app/services/llm.py`
  Provider-agnostic text generation servisi eklenir. İlk sürümde tek metod: `async def generate(prompt: str) -> str`.
- `app/services/prompts.py`
  Query answer prompt builder burada tutulur. Hardcoded fallback mesajları da buraya taşınır (`"Bu proje icin..."` vb.).
- `app/schemas/query.py`
  `query_embedding` alanı response'dan kaldırılır — 768-dim vektör client'a gitmemeli.

İlk sürümde `QueryService` orchestration noktası olmaya devam eder. Ayrı `AnswerPipelineService` ancak bu dosya büyürse düşünülür.

## Provider Strategy

LLM çağrısı provider abstraction ile yapılır.

İlk production-ready hedef:
- varsayılan sağlayıcı: `settings.formatter_model` (`gemini-2.5-flash`) — mevcut config ayarı kullanılır, yeni config gerekmez
- arayüz: `async def generate(prompt: str) -> str` — provider-agnostic, tek metod
- timeout ve servis hatalarında retrieval-only fallback korunur

Bu dilimde Gemini ile başlanır. Diğer provider'lar (OpenAI, Anthropic, Ollama) aynı arayüz üstünden eklenebilir.

## Error Handling

- Retrieval boşsa: LLM çağrılmaz, `retrieval_mode="empty"`, sabit güvenli mesaj dön (`prompts.py`'den).
- LLM timeout veya provider hatasında: `_fallback_answer()` devreye girer (eski `_compose_answer()` mantığı). Retrieval context client'a döner, `answer` fallback text olur.
- Prompt budget aşımı: context blokları `settings.formatter_input_char_limit` (12000 char) sınırına kadar kırpılır; servis patlamaz. LLM çıktısı `settings.formatter_output_char_limit` (2000 char) ile sınırlanır.

## Testing

- `QueryService` retrieval context'ten `llm.generate()` çağrısı yapıyor
- Kaynak yoksa `llm.generate()` çağrılmıyor, `retrieval_mode="empty"` dönüyor
- `llm.generate()` hata fırlatırsa snippet fallback devreye giriyor
- `prompts.py` builder: kaynaklar ve soru doğru inject ediliyor, prompt 12000 char limitini aşmıyor
- API `/query` yanıtında `generated answer` + `sources` tutarlı; `query_embedding` alanı yok

## Rollout

Bu dilim sonunda:
- checklist'te `Direkt pipeline (basit soru-cevap)` kapanır
- `/query` gerçek answer generation yapar
- sonraki `LangGraph` işi için sağlam temel oluşur
