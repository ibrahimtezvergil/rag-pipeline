# Application Domain Refactor Design

## Problem

Mevcut sistemde `tenant -> project` dili teknik olarak çalışıyor, ancak ürün modeline tam uymuyor.

Gerçek kullanım modeli şu:

- `tenant` = şirket
- `application` = CRM / Diet / Support gibi ürün instance'ı
- `user` = tenant içindeki kullanıcı
- `knowledge_scope` / `dataset` = application içindeki alt veri alanı

`project` adı, ekip içinde "ürün/platform instance" ile "bilgi havuzu" kavramlarını birbirine karıştırıyor. Bu karışıklık aşağıdaki alanlarda problem üretiyor:

- API header ismi (`X-Project-ID`)
- DB şeması (`rag_projects`, `project_id`)
- cache / rate-limit / observability terminolojisi
- checklist ve operasyon dokümantasyonu
- ileride eklenecek user-membership ve application-scope modeli

Amaç, domain dilini production-safe biçimde `project`ten `application`a taşımaktır.

## Goal

Refactor sonrası hedef model:

- `tenant` = şirket
- `application` = tenant altındaki ürün instance'ı
- `user` = tenant içi kullanıcı
- `knowledge_scope` / `dataset` = application içindeki alt veri segmenti

Bu refactor şu sonucu vermelidir:

- iç modeller ve DB şeması `application` dili kullanır
- dış API yüzeyi `X-Application-ID` ve `application_id` dili kullanır
- retrieval / ingest / cache / evaluation / feedback / schedules tek bir terim etrafında tutarlı hale gelir
- kısa geçiş süresinde eski istemciler tamamen kırılmaz

## Non-Goals

- `user` modeli eklemek
- membership / RBAC implement etmek
- knowledge scope veri modelini yeniden tasarlamak
- multi-tenant auth mantığını değiştirmek
- retrieval algoritmasını değiştirmek

Bu iş yalnızca yanlış domain terimini düzeltir.

## Current State

Bugünkü mapping:

- `rag_tenants` şirketi temsil ediyor
- `rag_projects` pratikte application instance gibi kullanılıyor
- `scope_type/scope_id/entity_id/tags` alt veri alanı gibi kullanılıyor

Yani uygulama mantığı zaten `application` gibi davranıyor; sadece isimlendirme geriden geliyor.

## Proposed Domain Model

Yeni domain modeli:

- `RagTenant`
- `RagApplication`
- `application_id`

Alt scope yapısı korunur:

- `scope_type`
- `scope_id`
- `entity_id`
- `tags`
- `snapshot_date`

Bu yüzden retrieval üst bağlamı:

- `tenant_id + application_id`

alt bağlamı:

- `scope_type + scope_id + entity_id + tags`

## Rename Scope

### Database

- `rag_projects` -> `rag_applications`
- tüm `project_id` kolonları -> `application_id`
- FK / index / constraint isimleri yeni terime çekilir
- ilgili migration zinciri Alembic ile yönetilir

Beklenen etkilenen tablolar:

- `rag_documents`
- `rag_schedules`
- `rag_evaluation_runs`
- `rag_chunk_feedback`
- `rag_projects` tablosunun kendisi

### Models and Repositories

- `RagProject` -> `RagApplication`
- repository method adları:
  - `get_project()` -> `get_application()`
  - `get_project_chunks()` -> `get_application_chunks()`
  - benzeri çağrılar yeni ada taşınır

### API Surface

- `X-Project-ID` -> `X-Application-ID`
- `request.state.project_id` -> `request.state.application_id`
- request/response payload alanları `application_id` olarak güncellenir

### Services

Refactor edilecek ana servisler:

- auth / deps
- ingest
- query
- chat
- schedules
- evaluations
- feedback
- callbacks
- query cache
- rate limit
- tracing / observability

### Docs and Tests

- handbook
- staging runbook
- checklist v3
- API test fixture ve assertion'lar
- deployment / migration testleri

## Compatibility Strategy

Production geçişi için dış API’de kısa süreli compatibility bırakılır.

Auth middleware kuralı:

1. Önce `X-Application-ID` oku
2. Yoksa `X-Project-ID` fallback olarak kabul et
3. İç state'te sadece `application_id` set et

Bu fallback geçici olacaktır ve checklist / handbook içinde deprecated olarak not edilir.

İçeride çift isim tutulmaz:

- kod içinde `project_id` değişkeni bırakılmaz
- model / servis / repo katmanı yalnızca `application_id` kullanır

## Migration Strategy

Tek Alembic migration paketi ile rename yapılır.

Beklenen adımlar:

1. `rag_projects` tablo rename
2. ilgili FK kolon rename
3. constraint ve index rename
4. gerekiyorsa view / trigger yoksa doğrudan tamamla

Migration veri taşıma yapmaz; mevcut veriyi yerinde rename eder.

Temiz deploy doğrulaması:

- `alembic upgrade head`
- API smoke
- ingest smoke
- query smoke
- schedule / evaluation / feedback smoke

## Retrieval and Vector Payload

Qdrant payload tarafında üst izolasyon `application_id` olur.

Not:

- `scope_type` alanı generik kalır
- `project` string literal'ı scope amacıyla kullanılıyorsa yeni durum yeniden değerlendirilir
- önerilen yaklaşım:
  - üst bağlam: `application_id`
  - alt bağlam: `scope_type/scope_id`

Yani application, scope_type ile temsil edilmez; ayrı üst bağlam anahtarı olur.

## Risks

### Migration Risk

Tablo/kolon rename tüm repository ve testleri etkiler. Eksik rename durumunda runtime hataları çıkar.

Azaltma:

- migration + full test suite + staging smoke birlikte koşulmalı

### API Client Risk

Eski istemciler yalnızca `X-Project-ID` gönderiyorsa deploy sonrası kırılabilir.

Azaltma:

- bir sürüm boyunca fallback desteği bırak
- handbook ve checklist'e deprecated notu ekle

### Observability / Cache Drift

Bazı log, cache key veya Redis anahtarı eski terimi taşımaya devam edebilir.

Azaltma:

- query cache, rate limit, tracing, observability kapsamı refactor listesine dahil edilir

## Rollout Plan

1. DB/model rename
2. auth/API rename
3. servis/repository rename
4. cache/rate-limit/observability rename
5. docs/checklist update
6. full verification

## Acceptance Criteria

- kod tabanında yeni iş mantığı için `project_id` yerine `application_id` kullanılır
- `RagProject` / `rag_projects` artık aktif domain modeli değildir
- `X-Application-ID` ana header olarak çalışır
- `X-Project-ID` geçici fallback olarak çalışır
- full relevant pytest suite geçer
- handbook ve checklist refactor gerekçesini açıkça yazar

## Why This Refactor Now

Bu refactor bugünkü ürün modeli artık netleştiği için yapılıyor:

- tenant = şirket
- application = ürün instance'ı
- user = tenant kullanıcısı
- knowledge_scope = application içi veri alanı

Bugün yapılmazsa:

- yeni `user/membership` modeli yanlış temel üstüne kurulur
- `DB loader` ve future SaaS auth dili daha da karışır
- dokümantasyon ile kod dili ayrışır

Bu yüzden refactor, yeni özellikten önce domain temizliği olarak ele alınmalıdır.
