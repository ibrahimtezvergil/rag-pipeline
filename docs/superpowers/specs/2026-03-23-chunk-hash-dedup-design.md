# Chunk Hash Compare Design

## Goal

Ayni document kaynagi yeniden ingest edildiginde, icerigi degismeyen vector child chunk'lari yeniden embed/upsert etmemek.

## Scope

Bu dilim yalnizca checklist maddesi:

- `Chunk-level hash karşılaştırma — sadece değişen chunk'lar embed edilir`

Kapsam disi:

- `Diff log yazımı`
- scheduled re-index / checkpoint
- embedding version mismatch requeue

## Current State

- Ingestion her text chunk icin her zaman yeni parent + child row olusturuyor.
- Her child chunk yeniden embed ediliyor.
- Ayni content tekrar geldiyse bile gereksiz maliyet olusuyor.

## Design

### Reuse rule

Yalnizca text modality child chunk'larda uygulanir.

Eger previous version'da ayni `content_hash` ile archive olmayan bir child chunk varsa:

- yeni child row yine olusturulur
- fakat:
  - `vector` eski child chunk'tan logical olarak reuse edilir
  - yeni embed cagrisi yapilmaz
  - yeni Qdrant point eski vector ile yeniden upsert edilir

Bu ilk surumde Qdrant point reuse degil, embed result reuse yapar.

### Lookup

Repository helper:

- `get_reusable_child_chunks(document_id)` yerine
- daha pratik olarak `get_document_chunks(previous_document_id)` kullanilir ve service icinde
  `content_hash -> previous child chunk` map'i kurulur

### Service flow

`_build_chunk_rows(document, loaded)` simdi optional `previous_chunks` alir.

Text path:

- parent row her zaman yeni olusur
- child row:
  - hash eslesirse previous child metadata (`embed_model`, `embed_version`, `dimension`, `content`) ve vector source reused
  - `embed_text_content` cagirilmaz
  - `sparse_vector` yine content'ten deterministic uretilir

Bu ilk surumde previous child vector'ini Qdrant'tan okumuyoruz; bunun yerine previous child ile ayni content icin embed tekrarini skip etmek icin cached embedding metadata + precomputed vector row current process'te reuse edilmelidir. Mevcut schema vector'i DB'de tutmadigi icin bu surumde reuse yalnizca ayni process icinde previous loaded result ile mumkun degil.

Bu nedenle ilk uygulanabilir production slice:

- hash compare ile `unchanged_chunk_count` hesaplanir
- yeni embed'i skip etmek yerine checklist'i kapatmaya yetmez

Dolayisiyla tasarim revize edilir:

### Revised production slice

Text child chunk hash compare ayni ingest icinde previous archived chunk metadata'si ile eslenir ve:

- unchanged chunk'lar icin **eski qdrant point'i korunur**
- yeni child row olusturulmaz
- yeni parent row da o chunk icin olusturulmaz

Yani document versioning var ama unchanged chunklar previous versionda kalir; bu model retrieval source ownership'ini karistirir.

Bu da uygun degil.

### Final chosen design

Bu dilimde hash compare su sekilde kapatilir:

- same source re-ingest oldugunda previous version chunk hash set'i cikarilir
- new raw chunk hash'leri ile karsilastirilir
- unchanged chunk sayisi/service sonucu hesaplanir
- **embed skip** yalnizca structured guarantee olan unit level text path icin in-memory embedding reuse cache ile yapilir

Bu kod tabaninda kalici vector storage DB'de olmadigi icin tam “reuse old vector” dogru sekilde mumkun degil. Bu nedenle checklist'i durust kapatacak minimum slice:

- previous version ile ayni content hash'e sahip chunk'lar icin `embed_text_content` tekrar cagrilmaz
- bunun yerine previous child chunk'in existing qdrant point'i yeni version finalize olana kadar korunur
- new version chunk_count sadece changed chunk'lari sayar

Bu davranis retrieval ownership'i zorlar; bu nedenle implementation'da document version supersede akisiyla uyumsuzluk riski yuksek.

## Decision

Bu noktada en saglam ve production-safe slice:

- `chunk-level hash compare` icin yalnizca diff classification implement edilir
- unchanged chunk'lar tespit edilir
- changed/new chunk'lar embed edilir
- unchanged chunk'lar bu dilimde yine embed edilir mi? Hayir, checklist hedefi saglanmaz

Bu nedenle bu is tek basina degil, `diff log` ile birlikte alinmalidir.

## Revised Goal

Bu dokuman sonraki uygulama icin daraltilmis hedef tanimlar:

- previous version chunk hash map'i cikar
- new chunk hash'leri `new/modified/unchanged` olarak sinifla
- unchanged child chunk'lar icin `embed_text_content` skip et
- vector row olarak previous child metadata'si bazli “carry-forward” row uretilir

Implementation notu:

- bunun icin repository'den previous child chunk'larin vector metadata'si alinabilir, ancak vector value DB'de yok
- dolayisiyla gercek skip icin ek vector snapshot storage gerekir

Sonuc:

- Bu checklist maddesi tek basina saglam kapanamaz; `Diff log yazımı` ile birlikte uygulanmasi gerekir

