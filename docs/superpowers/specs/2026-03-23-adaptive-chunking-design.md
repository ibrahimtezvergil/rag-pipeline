# Adaptive Chunking Design

## Goal

İçerik yoğunluğu ve yapısına göre chunk split penceresini otomatik ayarlamak.

## Scope

- `app/services/chunking.py`
- text/web ağırlıklı heuristik pencere seçimi
- mevcut PDF layout chunk davranışını bozmamak

## Flow

1. Raw chunk normalize edilir.
2. Basit yoğunluk sinyalleri hesaplanır:
   - noktalama oranı
   - satır/list yoğunluğu
   - ortalama cümle uzunluğu
3. Bu sinyallerden `adaptive_max_tokens` türetilir.
4. `_filter_and_split` sabit `max_tokens` yerine chunk-bazlı pencere kullanır.

## Notes

- İlk sürümde sadece split penceresi adaptiftir; overlap eklenmez.
- Heuristikler deterministik kalır.
- PDF `metadata["chunks"]` korunur; sadece son split aşaması adaptif olur.
