# Feedback Loop Plan

## Status: COMPLETED

1. Feedback DB model ve migration ekle.
2. Feedback schema, repository, service yaz.
3. `POST /feedback` endpointini router'a bagla.
4. Query source serialization'i `chunk_id` alanlarini client'a gecirecek sekilde ac.
5. Query service'e feedback aggregate okuyup source demotion uygula.
6. API ve query service testleri ekle.
7. Checklist satirini ref/akis notuyla kapa.
