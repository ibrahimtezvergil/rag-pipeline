# Ingestion Webhook Callback Design

## Amaç

Async ingest job tamamlandığında veya başarısız olduğunda dış sistemleri polling yapmadan haberdar etmek.

Hedef:

- `callback_url` verilmiş async ingest'ler için sonuç bildirimi göndermek
- callback güvenliğini HMAC-SHA256 ile sağlamak
- callback başarısızlığının ingest sonucunu bozmamasını garanti etmek

## Kapsam

Kapsam içi:

- `IngestRequest` içine `callback_url`
- async ingest payload'ına callback bilgisini taşımak
- worker sonunda callback POST etmek
- HMAC signature üretmek
- observability log

Kapsam dışı:

- sync ingest callback
- callback retry queue
- çoklu callback URL
- per-tenant secret yönetimi

## Current State

- ingest async modda ARQ job'ına dönüyor
- iş sonucu ancak `GET /ingest/{job_id}` ile polling yapılarak öğreniliyor
- callback mekanizması yok

## Seçilen Yaklaşım

İlk sürüm:

- sadece `mode=async`
- tek `callback_url`
- tek callback denemesi
- HMAC-SHA256 imzalı
- fail-open

## Tasarım

### 1. Request kontratı

`IngestRequest` içine yeni alan:

- `callback_url: HttpUrl | None`

Kurallar:

- `mode=async` ise kullanılabilir
- `mode=sync` ise yok sayılabilir veya validation ile reddedilebilir

Önerilen davranış:

- sync için kabul etme ama callback gönderme
- sade tutmak için ilk sürümde sync path'te callback yok

### 2. Dispatch payload

Async ingest enqueue edildiğinde job payload içine şunlar yazılır:

- `callback_url`
- `project_id`
- `source_type`

Worker final state oluştuğunda callback için yeterli context hazır olur.

### 3. Callback payload

`POST callback_url`

JSON body:

```json
{
  "document_id": "uuid",
  "ingestion_job_id": "uuid",
  "project_id": "uuid",
  "status": "completed|failed",
  "source_type": "pdf|web|structured|image|audio|db",
  "error_message": "optional"
}
```

### 4. Güvenlik

Header:

- `X-RAG-Signature`

İçerik:

- request body bytes üzerinde HMAC-SHA256

Secret kaynağı:

- ilk sürümde env tabanlı ortak secret
  - örnek: `INGEST_CALLBACK_SECRET`

Neden:

- hızlı ve production-ready başlangıç
- per-project secret yönetimi sonraki iterasyona bırakılır

### 5. Servis sınırları

Yeni servis:

- `app/services/callbacks.py`

Sorumluluk:

- payload oluşturma
- signature üretme
- callback POST etme
- hata halinde fail-open davranma

Worker entegrasyonu:

- `workers/tasks/ingest.py`
- ingest sonucu `completed` veya final `failed` olduğunda callback servisi çağrılır

### 6. Hata davranışı

- callback 4xx/5xx veya timeout:
  - ingest sonucu değişmez
  - sadece loglanır
  - worker job yeniden fail olmaz

Bu kritik çünkü callback hedefi dış sistemdir; ingest doğruluğunun parçası değildir.

## Observability

Event alanları:

- `callback_url_present`
- `callback_status_code`
- `callback_success`

Ham secret veya imza loglanmaz.

## Testing

Eklenecek testler:

- async ingest payload callback URL taşır
- worker completed durumunda callback çağrılır
- worker final failure durumunda callback çağrılır
- HMAC header doğru üretilir
- callback exception ingest sonucunu bozmaz

## Başarı Kriteri

- async ingest tamamlanınca callback POST gider
- final failure'da da callback POST gider
- HMAC signature header üretilir
- callback problemi ingest state'i bozmaz
