# Kök README Tasarımı

## Amaç

Depo kökünde, projeyi ilk kez gören birinin neyin inşa edildiğini, hangi kabiliyetlerin hazır olduğunu, sistemi nasıl ayağa kaldıracağını ve hangi gerçek kullanım senaryolarını desteklediğini hızlıca anlayabileceği bir ana `README.md` oluşturmak.

## Yaklaşım

Önerilen yapı, yönetici özeti ile hızlı başlangıcı aynı belgede birleştirir:

- projenin amacı ve kapsamı
- çalışan kabiliyetlerin özet haritası
- sistem mimarisi ve servis topolojisi
- yerel kurulum ve staging benzeri ayağa kaldırma akışı
- örnek API kullanımları
- kullanım senaryoları
- depo haritası ve ileri dokümantasyon bağlantıları

## Tasarım Kararları

- Belge dili Türkçe olacak. Mevcut operasyon belgeleri Türkçe ve hedef kullanıcıyla daha uyumlu.
- README, operasyon handbook'un yerini almayacak; onu özetleyip doğru detay belgelerine yönlendirecek.
- İçerik doğruluğu koddan ve mevcut çalışma dokümanlarından türetilecek; spekülatif roadmap maddeleri eklenmeyecek.
- Kurulum örnekleri depo kökünden başlayacak, ancak gerçek çalışma dizini olarak `rag-service/` açıkça belirtilecek.

## Başarı Kriterleri

- Yeni bir geliştirici 5-10 dakikada sistemin ne yaptığını anlayabilmeli.
- README tek başına temel local/staging akışını çalıştırmak için yeterli olmalı.
- Örnek istekler doğrudan mevcut endpoint ve şemalarla uyumlu olmalı.
