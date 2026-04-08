# RAG Pipeline

Bu depo, çok kiracılı ve uygulama bazlı çalışan bir multimodal RAG altyapısını içerir. Sistem; PDF, web, structured JSON, görsel ve ses kaynaklarını ingest edip PostgreSQL ve Qdrant üzerinde indeksler, sonra bu veriler üzerinden hybrid retrieval ve kaynak destekli cevap üretir.

Ana uygulama kodu [rag-service](/Users/ibrahim/Desktop/rag-pipeline/rag-service) altındadır. Kök seviye bu README, projenin ne yaptığını, nasıl çalıştırılacağını ve hangi kullanım senaryolarını hedeflediğini özetler.

## Ne Çözüyor?

- Farklı uygulamalardan gelen verileri tek bir RAG servisine toplar.
- `application_id` bağlamında izole ingest ve retrieval yapar.
- Kaynak referanslı cevaplar ve sohbet akışı üretir.
- Asenkron ingest, zamanlanmış re-index, evaluation ve feedback süreçlerini destekler.
- Operasyonel ihtiyaçlar için cache, rate limiting, circuit breaker ve tracing sunar.

Bu depo bir son kullanıcı paneli veya self-serve SaaS ürünü değildir. Esas odak, başka sistemlerin kullanacağı servis katmanını sağlamaktır.

## Çalışan Yetenekler

### 1. Ingestion

- PDF, web, `structured`, `db`, `image` ve `audio` kaynak tipleri
- `sync` ve `async` ingest modları
- toplu async ingest
- source-aware chunking ve parent-child chunk modeli
- document versioning, chunk hash karşılaştırma ve unchanged vector reuse
- semantic deduplication
- callback destekli ingest tamamlanma akışı

### 2. Retrieval ve Answering

- dense, sparse ve varsayılan hybrid retrieval
- RRF merge stratejisi
- Cohere rerank entegrasyonu
- query expansion
- confidence score ve confidence warning
- kaynak destekli tek turlu soru-cevap
- session tabanlı chat endpoint

### 3. Operasyonel Kabiliyetler

- Qdrant collection yönetimi
- cron tabanlı schedule oluşturma
- RAG evaluation run başlatma ve takip etme
- chunk seviyesinde retrieval feedback kaydı
- structured logging ve Langfuse tracing
- Redis tabanlı query cache ve rate limiting
- circuit breaker ve sağlık kontrolleri
- PgBouncer ile runtime DB connection pooling

## Mimari

Ana servis topolojisi [rag-service/docker-compose.yml](/Users/ibrahim/Desktop/rag-pipeline/rag-service/docker-compose.yml) içinde tanımlıdır:

- `api`: FastAPI tabanlı HTTP yüzeyi
- `worker`: ARQ worker, async ingest ve arka plan işleri
- `postgres`: uygulama verisi
- `pgbouncer`: transaction-pool DB bağlantı katmanı
- `qdrant`: dense ve sparse retrieval vektör deposu
- `redis`: queue, cache ve rate limit
- `langfuse_db` ve `langfuse`: gözlemlenebilirlik ve tracing

Uygulama giriş noktası [rag-service/app/main.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/main.py), API router tanımı [rag-service/app/api/router.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/api/router.py) altındadır.

## Hızlı Başlangıç

### Gereksinimler

- Docker ve Docker Compose
- Python sanal ortamı veya container içinde çalışma tercihi
- erişilebilir bir Gemini API anahtarı
- opsiyonel olarak Cohere API anahtarı

### 1. Ortam değişkenleri

Örnek değişkenler [rag-service/.env.example](/Users/ibrahim/Desktop/rag-pipeline/rag-service/.env.example) içinde yer alır.

Minimum kritik alanlar:

- `DATABASE_URL`
- `DATABASE_DIRECT_URL`
- `QDRANT_URL`
- `REDIS_URL`
- `GEMINI_API_KEY`
- `API_KEYS`
- opsiyonel: `COHERE_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`

### 2. Servisleri ayağa kaldırma

```bash
cd rag-service
docker-compose up -d --build
```

Staging benzeri akış için:

```bash
cd rag-service
docker-compose -f docker-compose.staging.yml up -d --build
```

### 3. Migration çalıştırma

```bash
cd rag-service
ENV_FILE=.env.example .venv313/bin/python -m alembic upgrade head
```

Yerel ortamda farklı bir env dosyası kullanıyorsanız `ENV_FILE` değerini buna göre değiştirin.

### 4. Sağlık kontrolü

```bash
curl -sS http://127.0.0.1:8000/health
```

Staging compose kullanıyorsanız runbook örneğinde port `18000` üzerinden ilerlenir.

## Kimlik Doğrulama Modeli

`/health`, `/docs` ve `/openapi.json` dışındaki endpoint'ler iki header bekler:

- `X-API-Key`
- `X-Application-ID`

`X-Application-ID` bir UUID olmalıdır ve servis içindeki tenant/application izolasyonunun temelidir.

Swagger arayüzü `http://127.0.0.1:8000/docs` altında açılır.

## Temel Kullanım Akışı

### 1. Collection oluştur

```bash
curl -sS -X POST http://127.0.0.1:8000/collections \
  -H 'X-API-Key: key1' \
  -H 'X-Application-ID: 11111111-1111-1111-1111-111111111111' \
  -H 'Content-Type: application/json' \
  -d '{"name":"rag_chunks"}'
```

### 2. Structured veri ingest et

```bash
curl -sS -X POST 'http://127.0.0.1:8000/ingest?mode=sync' \
  -H 'X-API-Key: key1' \
  -H 'X-Application-ID: 11111111-1111-1111-1111-111111111111' \
  -H 'Content-Type: application/json' \
  -d '{
    "source_type": "structured",
    "title": "crm snapshot",
    "records": [
      {
        "customer": "Acme",
        "invoice": "INV-1001",
        "status": "paid"
      }
    ]
  }'
```

### 3. Soru sor

```bash
curl -sS -X POST http://127.0.0.1:8000/query \
  -H 'X-API-Key: key1' \
  -H 'X-Application-ID: 11111111-1111-1111-1111-111111111111' \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "Which invoice was paid?",
    "retrieval_mode": "hybrid"
  }'
```

Yanıt içinde özetle şu alanlar döner:

- `answer`
- `confidence_score`
- `confidence_warning`
- `retrieval_context`
- `sources`

### 4. Sohbet akışı başlat

```bash
curl -sS -X POST http://127.0.0.1:8000/chat \
  -H 'X-API-Key: key1' \
  -H 'X-Application-ID: 11111111-1111-1111-1111-111111111111' \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "Summarize Acme payment history"
  }'
```

İlk çağrı size bir `session_id` döndürür. Sonraki çağrılarda aynı `session_id` ile devam edebilirsiniz.

## API Yüzeyi

Ana endpoint grupları:

- `GET /health`
- `GET /collections`
- `POST /collections`
- `POST /ingest`
- `POST /ingest/batch`
- `GET /ingest/{job_id}`
- `DELETE /ingest/{job_id}`
- `POST /query`
- `POST /chat`
- `POST /schedules`
- `POST /evaluations`
- `GET /evaluations/{run_id}`
- `POST /feedback`

Detaylı payload ve response şemaları şu dosyalardadır:

- [rag-service/app/schemas/ingest.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/schemas/ingest.py)
- [rag-service/app/schemas/query.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/schemas/query.py)
- [rag-service/app/schemas/schedules.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/schemas/schedules.py)
- [rag-service/app/schemas/evaluations.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/schemas/evaluations.py)
- [rag-service/app/schemas/feedback.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/schemas/feedback.py)

## Kullanım Senaryoları

### CRM veya ERP snapshot sorgulama

Structured JSON ingest ile müşteri, fatura, sipariş veya ticket kayıtları doğal dil özetine dönüştürülüp indekslenebilir. Böylece son kullanıcı veya destek ekipleri uygulama özelinde sorular sorabilir.

### İçerik sitesi veya help center araması

Web ve PDF ingest ile statik dokümanlar, yardım merkezleri veya ürün sayfaları indekslenebilir. Hybrid retrieval ve rerank sayesinde kaynak destekli cevaplar üretilebilir.

### Medya tabanlı arama

Görsel ve ses ingest akışları ile medya arşivleri vektörleştirilebilir. Özellikle ses tarafında clip bazlı embedding ve metadata akışı, içerik içinden semantik arama yapmayı mümkün kılar.

### Düzenli senkronizasyon ve yeniden indeksleme

`/schedules` ile cron tabanlı ingest işleri kurulabilir. Bu, dış sistemlerden gelen verinin belirli aralıklarla yeniden çekilmesi veya yeniden indekslenmesi için kullanılır.

### Kalite ölçümü ve geri besleme

`/evaluations` ile bir veri seti üzerinde faithfulness, answer relevancy ve context recall ölçülebilir. `POST /feedback` ile retrieval kalitesine ilişkin chunk bazlı insan geri bildirimi toplanabilir.

## Depo Haritası

- [rag-service](/Users/ibrahim/Desktop/rag-pipeline/rag-service): servis kodu, API, worker, migration ve docker dosyaları
- [docs/operations](/Users/ibrahim/Desktop/rag-pipeline/docs/operations): handbook ve staging runbook
- [docs/superpowers/specs](/Users/ibrahim/Desktop/rag-pipeline/docs/superpowers/specs): tasarım dokümanları
- [docs/superpowers/plans](/Users/ibrahim/Desktop/rag-pipeline/docs/superpowers/plans): uygulama planları

## İlgili Dokümanlar

- [docs/operations/rag-service-handbook.md](/Users/ibrahim/Desktop/rag-pipeline/docs/operations/rag-service-handbook.md)
- [docs/operations/rag-service-staging-runbook.md](/Users/ibrahim/Desktop/rag-pipeline/docs/operations/rag-service-staging-runbook.md)
- [rag-service/docker-compose.yml](/Users/ibrahim/Desktop/rag-pipeline/rag-service/docker-compose.yml)
- [rag-service/docker-compose.staging.yml](/Users/ibrahim/Desktop/rag-pipeline/rag-service/docker-compose.staging.yml)

## Testler

Testler [rag-service/tests](/Users/ibrahim/Desktop/rag-pipeline/rag-service/tests) altında bulunur. Yerel doğrulama için örnek komut:

```bash
cd rag-service
ENV_FILE=.env.test .venv313/bin/python -m pytest -q
```

Testlerin tamamı harici servisler ve uygun test env yapılandırması gerektirebilir; bu nedenle CI veya hazır local stack ile çalıştırılması daha güvenlidir.
