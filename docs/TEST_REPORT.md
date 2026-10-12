# Test ve kabul raporu

Tarih: 12 Ekim 2026. Çalıştırılan kaynak: teslim edilen 0.1.0.

## Otomatik test sonucu

`python -m pytest -q --junitxml=docs/test-results.xml`

**28 test geçti; 0 başarısız; 0 hata.** Son çalışma süresi 5.09 saniye. Test çıktısında 1 bağımlılık uyarısı vardı; test başarısızlığı değildi. Makine çıktısı: `test-results.xml`.

Kapsam: beyaz vektör, kapalı delik yasağı, açık U girintisi, 100 farklı poligonun 3 mm mesafesi, 37 kopya, serbest açı alan/ölçü koruması, 0/7/43/90/126/218/337 derece çıktı PDF geometrisi, PDF vektör sayısı, SVG birimleri/dönüş/clip, saldırgan SVG ve XXE reddi, raster reddi, CMYK renk komutu, SVG renk koruma engeli, HTTP yükleme/adet/çıktı, kullanıcı izolasyonu/CSRF, başarısız yükleme davranışı, pause/resume checkpoint, gömülü font, gömülmemiş font reddi, alpha kontur, beyaz arka planın korunması, gerçek PDF clip, yay, spot DTFWhite adı/komutu ve doğrudan iç içe kaynaklardaki desteklenmeyen blend reddi.

`npm run build --prefix frontend`: TypeScript kontrolü ve Vite production build başarılı. Derlenmiş frontend `frontend/dist/` içinde.

## Gerçek BRZ dosyası

Kaynak: kullanıcının `Brz deneme pdf.pdf` dosyası. Kaynak ölçüsü değiştirilmedi; PDF'de görüntü nesnesi yok, 44 vektör çizim nesnesi var. Boş sayfa alanı kırpıldı, beyaz logo silinmedi.

| Kontrol | Ölçülen sonuç |
|---|---:|
| Baskı adedi | 37 |
| Mürekkep kutusu | 99.9934 × 48.1878 mm |
| İlk dosya analizi | 0.233 s |
| İlk geçerli yerleşim | 3.188 s |
| Film genişliği | 580.0000 mm |
| Film uzunluğu | 366.5538 mm / 36.6554 cm |
| İstenen boşluk | 3 mm |
| Güvenlik geometrisinde en küçük mesafe | 3.1273 mm |
| PDF vektör çizim nesneleri | 1628 = 44 × 37 |
| PDF görüntü nesneleri | 0 |
| Bağımsız doğrulama | Geçti |

Örnek dosya: `examples/real-brz/BRZ_37_ADet_580mm.pdf`. Renkli/koyu zemin PDF'ye eklenmedi. Makine raporu ve yerleşim koordinatları aynı klasörde.

Çıktı ayrıca **Poppler pdftocairo** ile saydam PNG'ye render edilip yalnız inceleme için koyu griyle birleştirildi; son görünüm kontrol edildi. Bu inceleme PNG'si baskı dosyasına veya dışa aktarım hattına konmadı. Bu, gerçek RIP kabul testinin yerine geçmez.

## Ayrı süreçlerle gerçek HTTP akışı

Gerçek Uvicorn HTTP servisi ve ayrı worker başlatıldı. BRZ PDF HTTP ile yüklendi; adet 37 yapıldı; iş başladı; kısmi checkpoint kaydedildi; duraklatıldı; worker süreci kapatılıp yeniden açıldı; iş devam ettirildi; PDF HTTP ile indirildi.

- Son durum: completed; geometri geçerli.
- Duraklatma isteği öncesi görülen kopya: 19; worker'ın durduğu checkpoint: 19.
- Son çıktı: 37 baskı, 1628 vektör çizimi, 0 görüntü.
- En iyi uzunluk: 366.5538 mm.
- Derlenmiş arayüz HTTP 200 ile sunuldu.
- **Tarayıcı/gerçek iPad testi yapılmadı.** Bu sonuç HTTP + worker entegrasyon testidir.

Ayrıntı: `docs/http-e2e-results.json`; tekrar çalıştırma: `python -m tests.http_e2e /tam/yol/Brz.pdf docs/http-e2e-results.json`.

## Büyük iş benchmark

Bu testte 3 farklı basit şekilden tekrarlar kullanıldı; dönüşler kilitliydi. 1000 karmaşık müşteri logosu veya 1000 farklı logo testi değildir. Her iki işte bütün kopyalar ve 3 mm mesafe bağımsız doğrulandı.

| Baskı | Şekil türü | Yerleştirme | Doğrulama | Süreç tepe RSS | Film uzunluğu | Sonuç |
|---:|---:|---:|---:|---:|---:|---|
| 500 | 3 | 10.29 s | 0.075 s | 129.36 MiB | 486.826 mm | Geçti |
| 1000 | 3 | 41.71 s | 0.145 s | 129.74 MiB | 988.947 mm | Geçti |

Süreç RSS değeri Linux `resource.getrusage` ile ölçüldü; tüm Docker dağıtımı, frontend veya diğer süreçlerin toplam belleği değildir. Paylaşımlı çalışma ortamı sonuçlarıdır; donanım garantisi değildir. Açı araması ve karmaşık şekiller daha pahalıdır. Ham sonuçlar: `benchmark-results.json`.

## AST-663 referansı

`AST-663 09,10,2026 377 CM.pdf` incelendi. 1 sayfa, yaklaşık 4999,990 × 579,998 mm; 45.377 vektör çizim nesnesi; görüntü nesnesi yok. Dosya adındaki 377 cm sayfa ölçüsü değildir. Ham çizim sınırları clipping/çalışma yüzeyi nesneleri içerebildiği için bunları ölçülmüş baskı uzunluğu saymadık.

Ayrı orijinal logolar, doğru kopya adetleri ve ölçüleri bulunmadığından eşdeğer yeniden yerleştirme yapılmadı. 377 cm'den kısa sonuç iddiası yoktur. Referans dosya 25 MB web yükleme sınırını aşar; yalnız yerel salt-okunur incelemede kullanıldı. `reference-inspection.json` ayrıntıları içerir.

## Kabul kriterleri özeti

| Kullanıcı testi | Durum |
|---|---|
| 1 — Beyaz logo | Sentetik PDF ve gerçek BRZ ile geçti |
| 2 — İç boşluk | Geçti; delik dolduruluyor ve içine yerleşim reddediliyor |
| 3 — Dış girinti | Geçti; U girintisine küçük parça yerleşti |
| 4 — 100 farklı baskı / 3 mm | Geçti; 100 farklı sentetik poligon |
| 5 — Döndürme / ölçü | Geçti; keyfi açılar ve çıktı PDF geometrisi |
| 6 — 37 adet | Geçti; API + PDF vektör sayısı |
| 7 — Vektörel PDF | Geçti; yeniden açılıp vektörler kontrol edildi |
| 8 — Gerçek iPad Safari | YAPILMADI; cihaz/tarayıcı doğrulaması gerekli |
| 9 — 500–1000 baskı | Geçti; 3 şeklin tekrarları ile sınırlı benchmark |
| 10 — AST-663 adil karşılaştırma | YAPILMADI; ayrı orijinaller/adetler gerekli |

Docker build/Compose/TLS, gerçek Windows Chrome/Edge, Illustrator ve DTF RIP baskısı bu ortamda çalıştırılmadı. Bu nedenle tüm üretim kabul kriterleri tamamlanmış değildir. `LIMITATIONS.md` açık kalan özellik ve sınırları listeler.
