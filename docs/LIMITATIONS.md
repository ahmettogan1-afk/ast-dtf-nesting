# Teknik sınırlamalar ve üretim kabul durumu

Bu sürüm, istenen 23 başlığın tamamını eksiksiz karşılamaz. Çalışan uygulama ve kaynak kod teslim edilmiştir; “eksiksiz üretim yazılımı tamamlandı” iddiası yoktur.

| Alan | Gerçek durum |
|---|---|
| PDF/SVG içe aktarma | Desteklenen vektör alt kümesi gerçek kodla çalışır. Bilinmeyen/tehlikeli özellikler reddedilir. |
| Beyaz logo | Desteklendi ve gerçek BRZ PDF'siyle test edildi. Sayfa zemini baskı sayılmaz; boyanmış beyaz nesne korunur. |
| Arka plan çıkarma | Tek tıkla beyaz dikdörtgen silme YOK. Beyaz sayfa boyu nesne işaretlenir, dahil olduğu onaylanır; çıkarmak için kaynak dosya düzeltilmeli. |
| Çok logolu tek sayfa | Otomatik anlamlı logo ayrıştırma/grup önerisi YOK. Sayfa bir bütün grup olarak kullanıcıya onaylatılır. Birden çok logo için ayrı sayfalar/dosyalar gerekir. |
| Çok sayfalı PDF | En fazla 30 sayfa; her sayfa ayrı grup, toplam 100 grup. |
| AI | Yalnız PDF uyumlu kaydedilmiş AI. Native PostScript AI reddedilir. |
| EPS | Dönüştürücü kurulmadı; açık hata ile reddedilir. |
| Raster PDF/SVG | Algılanır ve reddedilir; vektörmüş gibi sunulmaz. Karışık vektör+raster iş akışı yok. |
| SVG metni | SVG kaynakta canlı text desteklenmez; kontura çevrilmeli. Gömülü fontlu PDF metni desteklenir. |
| PDF fontları | Gömülü fontlar; standart font dahil gömülmemiş fontlar güvenlik için reddedilir. Type3 reddedilir. |
| Clipping | SVG userSpaceOnUse clip, affine dönüşümler ve PDF'nin vektör SVG karşılığı desteklenir. objectBoundingBox clip reddedilir. |
| Saydamlık | Normal alpha destekli. Soft mask, özel blend/knockout, filtre, pattern ve shading reddedilir. |
| Kontur | Sabit pozitif genişlik; hairline reddedilir. Kesikli çizgi için tüm kontur muhafazakâr ayrılır. Yuvarlatılmış SVG rect köşeleri dikdörtgen olarak ayrılabilir. |
| Renk | PDF kaynak CMYK/spot kaynak nesnelerini taşır. CMYK ve sentetik DTFWhite spot renk adı korunması otomatik test edildi. Gerçek spot mürekkep/RIP ayrımı sahada doğrulanmadı. |
| SVG renk | CMYK/spot/ICC içeren işlerde SVG indirme engellenir; PDF önerilir. RGB'ye sessiz dönüşüm yapılmaz. |
| OutputIntent/PDF-X | Profil kopyalama yok; bu tür kaynaklar reddedilir. PDF/X uyumluluk garantisi yok. |
| DTF beyaz kanalı | Beyaz vektör korunur. RIP'e özel spot “White” üretimi, underbase, choke/spread ve mirror otomasyonu yok. |
| Şekil nesting | Gerçek poligon mesafesi, delik kapama, dış girinti ve açı araması var. Eksiksiz NFP/Minkowski, genetik algoritma veya global optimum garantisi yok. |
| Sadeleştirme | Mürekkep vektörünü değiştirmez. Geometri toleransları `ARCHITECTURE.md` içinde. |
| Çok parçalı logo | Bütün parçalar aynı kopyanın içinde sabit kalır. Kapalı iç boşluklar yasak, parçalar arasında dışa açık boşluklar kullanılabilir. |
| Ölçü | İlk yüklemede kaynak fiziksel ölçek korunur. İstenen genişlik, gerçek mürekkep geometrisinin kutusundan oranlı ölçeklenir; eğri toleransı yaklaşık 0,015 mm. |
| Döndürme | Serbest sayısal açı; çoklu optimizasyonda tam daire boyunca adaylar. 0,25° aday fazı var; her açı / her yerleşim kombinasyonu taranmaz. |
| Film uzunluğu | Hesapta şerit uzar; PDF dışa aktarmada en fazla 5080 mm. Otomatik çok sayfa veya UserUnit yok. |
| Adet | Grup başına ve iş toplamında en fazla 1000. Yüz binlerce baskı hedeflenmedi. |
| Pause/Resume | Gerçek kısmi deneme checkpoint'i; süreç yeniden başlatma ile gerçek HTTP testinde doğrulandı. |
| Manuel düzenleme | Önizlemede seçme, X/Y/açı kutularından düzenleme ve doğrulama var. Doğrudan logoyu sürükleme yok. |
| iPad hareketleri | Pointer tabanlı pinch/pan kodu var; gerçek Safari/WebKit testi YAPILMADI. |
| Tarayıcı testi | TypeScript/Vite build ve HTTP statik teslim test edildi. Görsel tarayıcı QA, iPad, Chrome, Edge uçtan uca testi YAPILMADI. |
| UI biçimi | React + TypeScript + Vite + yerel CSS. Tailwind yerine bağımlılığı azaltan düz CSS. |
| Çok kullanıcı | Parolalı ayrı sahiplik var; API izolasyon testi geçti. Kullanıcı yönetim paneli yok; CLI hesabı oluşturur. |
| Sunucu | Tek Linux sunucu, tek API, tek worker. SQLite WAL; HA/yatay ölçek yok. |
| Güvenlik | Kaynak sınırları ve SVG/PDF kontrolleri var; bağımsız penetrasyon testi, disk kotası veya müşteri başına sandbox yok. |
| Docker | Dockerfile, Compose ve TLS proxy yapılandırması hazır. Bu ortamda Docker bulunmadığı için image/Compose/TLS çalıştırılması YAPILMADI. |
| Yayın | İnternete yayın yapılmadı; çalışan URL sağlanmadı. Sunucu/alan adı kurulumu README'de. |
| Referans 377 cm | Ayrı logo kaynakları ve adetler bulunmadığı için adil yeniden dizilim karşılaştırması yapılmadı. Daha kısa sonuç iddia edilmez. |

## Üretim onayı öncesi kalan somut işler

1. Hedef Linux sunucuda Docker build + Compose + TLS kurulumunu çalıştırmak; yedekten dönüşü doğrulamak.
2. Gerçek iPad Safari'de upload → adet → başlat → pinch/pan → PDF indir; Windows Chrome/Edge'de aynı akışı test etmek.
3. Illustrator'da 0°, 7°, 43°, 90°, 218° örneklerinin fiziksel ölçülerini ve görünümünü açıp kontrol etmek.
4. Kullanılan DTF RIP'te CMYK/spot/beyaz mürekkep separasyonlarını ve gerektiğinde aynalamayı doğrulamak; küçük filmde gerçek baskı ölçmek.
5. Çok logolu tek PDF otomatik grup önerisi ve beyaz arka planı güvenle seçerek çıkarma özelliklerini eklemek.
6. EPS dönüşümünü izole, sürümü sabitlenmiş dönüştürücü ile eklemek; lisans ve güvenliği incelemek.
7. AST-663'ün ayrı logo dosyaları, gerçek en-boyları ve adetleriyle karşılaştırma yapmak.

Bu maddeler tamamlanmadan nihai üretim kabulü açık kalır.
