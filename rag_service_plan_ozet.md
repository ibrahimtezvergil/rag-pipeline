# RAG Pipeline Mimari Tasarımı ve Uygulama Planı Özeti

Bu belge, **RAG (Retrieval-Augmented Generation) Pipeline Mimari Tasarımı ve Uygulama Planını** detaylı bir şekilde açıklayan, teknik kararların ve sistem altyapısının belirlendiği kapsamlı bir dokümandır. 

Belgenin genel yapısı ve alınan kritik kararlar şu başlıklar altında özetlenmiştir:

## 1. Temel Altyapı ve Veritabanı Seçimleri
- **Vector Store:** Sektör standartlarında olan ve güçlü filtreleme imkânı sunan **Qdrant (Docker)** seçilmiştir.
- **Registry / Metadata Veritabanı:** Kurulum kolaylığı ve taşınabilirlik amacıyla başlangıçta **SQLite** kullanılacağı, sistemin büyümesi ve 10K+ dokümana ulaşılması durumunda kilitlenmelerin (lock issues) önüne geçmek için ileride **PostgreSQL**'e geçileceği, bu geçişle birlikte connection pooling için **PgBouncer** kullanılacağı planlanmıştır.
- **Queue / Asenkron İşlemler:** FastAPI ile uyumlu çalışan **ARQ + Redis** tercih edilmiştir.

## 2. Embedding, Arama ve Sıralama (Search & Ranking) Stratejisi
- **Embedding Modeli:** Ana model olarak **Gemini (`gemini-embedding-exp-03-07`, 768 boyut)**, yedek (fallback) olarak ise **`text-embedding-004`** belirlenmiştir. Boyut sabit (768) tutularak dokümanların model bağımsız çalışması hedeflenmiştir.
- **Chunking (Parçalama):** Bağlamın (context) kaybolmaması için *Source-aware* ve *parent-child* chunking yapısı benimsenecektir. PDF'ler ile vizyonel entegrasyonlar (Vision-RAG) yapmak için `bbox` (piksel koordinatları) ve `page_number` metadataları da chunk'lara dahil edilecektir.
- **Arama Motoru:** Türkçe metinlerde başarı oranını artırmak için Keyword (BM25) ve Semantic (Dense) aramaların birleştiği **Hybrid (RRF)** arama stratejisi kullanılacaktır.
- **Reranker (Yeniden Sıralama):** Düşük gecikme süresi ve maliyet etkinliği nedeniyle **Cohere Rerank-3** kullanılacaktır.

## 3. Ölçeklenebilirlik, Multi-Tenant ve Gelecek (SaaS) Planları
- **Tenant Mimarisi:** Sistem izole projeler için `project_id`, `tenant_id` tabanlı tasarlanmıştır. 100K altı partition'lar paylaşımlı (shared) tutulurken, büyük tenant'lar otomatik olarak kendi özel alanlarına (dedicated) alınacaktır.
- **SaaS Geçişi:** 4 aşamalı eklemeli (incremental) bir süreç izlenerek önce kendi projelerinizde kullanılacağı, sonrasında streaming (SSE), webhook bildirimleri, multimodal RAG gibi özelliklerin ekleneceği karar kılınmıştır.
- **Performans & Güvenlik:** Limit aşımlarını engellemek için LangGraph pipeline'ına `latency_budget_ms` ve `token_budget` uygulanacak, böylece LLM maliyetlerinin kontrolden çıkması (ör. sonsuz self-RAG döngüleri) önlenecektir. Rate limiting (Redis sliding window) devreye alınacaktır.

## 4. Gelişmiş Veri Modeli ve Takip Mekanizmaları
- **Tablolar:** Geleneksel RAG yapılarının bir adım ötesine geçilerek doküman ve chunk yapısına ek olarak, versiyonlama (`version`), delta audit (`rag_chunk_diff_log`), senkronizasyon kontrolleri (`rag_sync_checkpoints`) ve arka plandaki job'lar (`rag_ingestion_jobs`) için ek loglama/checkpoint tabloları eklenmiştir.
- **Erişim Kontrolü (ACL):** Chunk seviyesinde bile rol bazlı (`acl[]`) erişim denetimi mevcuttur.

**Özetle;**
Belge, sadece anlık ihtiyacı çözen bir RAG denemesi değil, üretime (production) hazır, gerektiğinde SaaS ürününe dönüşebilecek, maliyet ve request/token metriklerinin kontrol altında tutulduğu, performans odaklı (Hetzner, Redis, Qdrant vb. tercihleri bulunan) gayet ileri seviye bir altyapı tasarım dökümanıdır.
