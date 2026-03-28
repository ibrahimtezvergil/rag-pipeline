# Audio Metadata Pipeline Design

## Amaç

Mevcut audio ingest akışına transcript ve segment metadata eklemek, ancak audio embedding ana yolunu kırmamak.

Hedef:

- audio ingest sonrası anlamlı transcript metadata üretmek
- mümkünse speaker/segment bilgisi taşımak
- metadata pipeline devre dışıysa veya bağımlılıklar yoksa ingest'in yine başarıyla tamamlanması

## Kapsam

Kapsam içi:

- audio ingest sırasında metadata enrichment
- transcript ve segment metadata üretimi
- chunk/document metadata alanlarına yazım
- config ile aç/kapat davranışı
- best-effort fallback

Kapsam dışı:

- ayrı mikroservis
- zorunlu diarization
- video metadata pipeline
- retrieval tarafında transcript-specific yeni skor modeli

## Current State

- audio ingest bugün clip window bazlı çalışıyor
- `load_audio_source` audio byte, mime type, duration ve clip aralıklarını çıkarıyor
- `IngestionService` her clip için audio embedding alıyor
- chunk content şu an sentetik clip özeti düzeyinde
- transcript veya speaker metadata yok

## Seçilen Yaklaşım

Opsiyonel yan kanal.

Ana kural:

- audio embed ana akış
- audio metadata enrichment best-effort

Yani:

- metadata pipeline çalışırsa document/chunk metadata zenginleşir
- çalışmazsa ingest başarısız olmaz

## Tasarım

### 1. Audio metadata service

Yeni servis:

- `app/services/audio_metadata.py`

Sorumluluk:

- audio bytes alır
- transcript üretmeye çalışır
- segment listesi döner
- opsiyonel diarization sonucu varsa speaker label ekler

İlk sürüm API:

```python
async def extract_audio_metadata(
    audio_bytes: bytes,
    *,
    filename: str | None = None,
) -> dict[str, object]
```

Dönüş örneği:

```json
{
  "status": "ok",
  "provider": "whisper",
  "transcript": "Customer called about invoice INV-1001.",
  "segments": [
    {
      "segment_index": 0,
      "start_second": 0,
      "end_second": 18,
      "text": "Customer called about invoice INV-1001.",
      "speaker_label": null
    }
  ]
}
```

Başarısız veya unavailable:

```json
{
  "status": "unavailable",
  "provider": "whisper",
  "transcript": null,
  "segments": []
}
```

### 2. Provider stratejisi

İlk production-ready strateji:

- transcript için Whisper benzeri provider interface
- diarization interface hazır ama zorunlu değil

Config:

- `audio_metadata_enabled: bool`
- `audio_diarization_enabled: bool`

Davranış:

- `audio_metadata_enabled=false` ise servis çağrılmaz
- `audio_metadata_enabled=true` ama provider hazır değilse `status=unavailable`
- `audio_diarization_enabled=true` ama diarization bağımlılığı yoksa transcript yine döner, speaker boş kalır

## 3. Ingestion entegrasyonu

Akış:

1. `load_audio_source` mevcut gibi audio bytes + clip metadata döner
2. audio metadata servisi çalışır
3. document metadata içine transcript özeti ve segmentler yazılır
4. clip chunk'lar üretilirken segmentler ilgili clip aralıklarına dağıtılır
5. chunk content sentetik clip özetinden daha anlamlı hale gelir:
   - transcript segment text varsa buna öncelik verilir
   - yoksa mevcut clip summary fallback kullanılır

Document metadata alanları:

- `audio_metadata.status`
- `audio_metadata.provider`
- `audio_metadata.transcript`
- `audio_metadata.segments`

Chunk metadata alanları:

- `audio_segments`
- `speaker_labels`
- `start_second`
- `end_second`

## 4. Retrieval etkisi

İlk sürüm retrieval değişikliği sınırlı olacak:

- chunk `content` artık transcript segment text taşıyabildiği için retrieval doğal olarak iyileşir
- ek retrieval algoritması eklenmez

Bu önemli çünkü ana kazanç zaten daha anlamlı chunk text üretmektir.

## 5. Fallback ve hata davranışı

- metadata extraction exception:
  - ingest fail etmez
  - `audio_metadata.status = "error"` yazılabilir
  - mevcut clip summary ile devam edilir
- provider unavailable:
  - `status = "unavailable"`
  - ingest normal tamamlanır

## 6. Observability

İsteğe bağlı log alanları:

- `audio_metadata_status`
- `audio_metadata_provider`
- `audio_segment_count`

Ham transcript tam metnini loglamayız.

## 7. Testing

Eklenecek testler:

- metadata extraction başarılıysa transcript ve segments document metadata'ya yazılır
- clip chunk content transcript segmentlerinden üretilir
- metadata unavailable ise mevcut clip summary fallback korunur
- metadata exception ingest'i fail etmez
- diarization yoksa speaker_label alanı boş kalır ama transcript devam eder

## Başarı Kriteri

- mevcut audio ingest bozulmadan çalışır
- metadata provider mevcutsa transcript/segment metadata oluşur
- provider yoksa ingest yine başarıyla `indexed` olur
- audio chunk text semantik olarak daha anlamlı hale gelir
