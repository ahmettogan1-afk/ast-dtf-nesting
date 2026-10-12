# Teknik mimari ve doğruluk sınırları

## Veri yolları

İçe aktarma ile geometri ve çıktı birbirinden ayrıdır:

1. HTTP isteği kimlik doğrulamasından geçer; kullanıcı sahipliği iş kaydında doğrulanır.
2. 25 MB sınırlı dosya geçici klasöre alınır. Ayrı Linux alt süreci en fazla 50 CPU saniyesi / 60 duvar saati saniyesi / 2 GB sanal bellek ile analiz eder.
3. PDF kaynak nesneleri pikepdf ile ön kontrolden geçer. Yalnız tümü görünür, koşulsuz katmanlar vektör korunarak sabitlenir; koşullu/gizli katmanlar reddedilir.
4. PDF sayfası MuPDF ile **vektörel SVG komutlarına** dönüştürülür. Piksel görüntüsü üretilmez. Bu yol yalnız geometri ve ekran görünümü içindir.
5. SVG path/rect/circle/ellipse/line/polyline/polygon, affine dönüşümler, local `use`, userSpaceOnUse clipping ve konturlar Shapely poligonlarına çevrilir. Dolgu nonzero/evenodd kuralları winding testiyle uygulanır.
6. Bézier eğrileri kontrol poligonu üzerinden adaptif bölünür; dönüşüm matrisinin en büyük tekil değeri yerel toleransı belirler. Yaylar eğrilik üst sınırına göre örneklenir. Varsayılan düzleştirme toleransı 0,015 mm, muhafazakâr geometri payı 0,04 mm'dir. Ölçek değiştirilirse bu pay da fiziksel ölçekle değişir.
7. Bütün grubun boyanan parçaları birleştirilir; birleşim poligonlarının kapalı delikleri doldurulur. Açık dış girintiler korunur. Bu geometri baskı çizimi değildir; yalnız yerleştirme için kullanılır.
8. Kaynak PDF'nin vektör sayfa içeriği ayrı normalleştirilmiş PDF'ye `show_pdf_page` ile Form XObject olarak taşınır. Boş sayfa kenarları kırpılır; mürekkep nesneleri yeniden çizilmez. Logo mürekkep sınırı, sayfa kutusu ve yerleştirme güvenlik payı ayrı tutulur.

## Optimizasyon

Sonsuz uzunluklu şerit: `film_width - 2*margin`; bütün doğrulanmış geometriler sınır içinde olmalıdır. Üst ve alt uçta da aynı kenar payı kullanılır.

- İlk geçerli yerleşim: alana göre büyükten küçüğe, 0°/90°.
- Şekillerin dış köşe temaslarından X adayları ve yayılı örnekleme oluşturulur.
- Bounding box yalnız aday daraltmak ve mekânsal hash için kullanılır; kabul kararı gerçek poligon mesafesine dayanır.
- Dış girintiye, bounding box'lar örtüşse bile gerçek şekiller 3 mm ayrılıyorsa yerleşilebilir.
- Sonraki denemeler deterministik tohumla sıra önceliklerini değiştirir; 0–360° boyunca 13° kaydırmalı ve bazı denemelerde 0,25° fazlı açı kümeleri denenir.
- Yerleştirme hesabı için ayrıca 0,06 mm sadeleştirme ve 0,061 mm dışa genişletme kullanılır. Son kontrol tam geometriyi yeniden yükler; sadeleştirilmiş önbelleği kullanmaz.
- Daha uzun sonuçlar en iyi sonucu değiştirmez. İlk uzunluk ve en iyi uzunluk arasındaki fark gerçek tasarruftur.
- Kullanıcı sayısal açı girişinde 0,1° gibi değerlerle serbest döndürme yapabilir; 90° kısıtı yoktur.

**Bu algoritma eksiksiz NFP/Minkowski optimum çözümcüsü değildir.** Sürekli temas uzayının tamamını taramaz; yukarı sıçrama sezgiseli bazı girintileri kaçırabilir. Sonuç geçerliliği ile optimal sonuç bulma farklı şeylerdir. % tasarruf, manuel iş değil aynı işteki ilk geçerli yerleşimle kıyaslanır.

## Bağımsız doğrulama

`validation.py`, yerleştiricinin çakışma indeksini, dönmüş şekil önbelleğini veya aday skorunu kullanmaz:

- Kaydedilen vektör geometrisini yeniden yükler; bütün ölçek/dönüş/ötelemeleri yeniden uygular.
- İstenen ve gerçek kopya sayılarının çokluklarını karşılaştırır; kopya kimliklerinin tekilliğini denetler.
- Döndürme kilitleri ve film sınırlarını denetler.
- Y taramasıyla yakın çiftleri seçer, GEOS gerçek mesafesini ve alan kesişimini hesaplar.
- Ayrıca bağımsız STRtree nearest sorgusuyla bütün yerleşimin minimum komşu mesafesini raporlar.
- Geçersiz sonuç dışa aktarılamaz; manuel düzenleme işlemi geri alınır.

Bu kontrol geometri algoritmasından bağımsızdır, fakat **aynı vektör çıkarımına dayanır**. İkinci bir bağımsız PDF rasterizer/RIP tarafından tam mürekkep sınırı doğrulaması yapılmamıştır. Tanınmayan PDF/SVG özelliklerinin reddedilmesi bu yüzden önemlidir.

## Çıktı

PDF çıktısı özgün vektör Form XObject'lerini affine dönüşümle yerleştirir. CMYK komutları, fontlar, clip ve desteklenen normal alpha korunur. Mürekkep piksellere dönüştürülmez. Preview arka planı veya geometri yardımcı çizgileri çıktıya eklenmez.

SVG çıktısı, MuPDF'nin vektörleştirilmiş sayfa görünümünden referanslanan gruplarla üretilir. PDF metinleri glyph yolları olur. Standart tarayıcı SVG'si CMYK/spot kaynakla eşdeğer üretim dosyası değildir; non-RGB işlerde indirme engellenir. PDF/X OutputIntent kaynakları da profil aktarımı uygulanmadığı için reddedilir.

PDF sayfa yüksekliği en fazla 5080 mm ile sınırlıdır; otomatik bölme ve UserUnit uygulanmamıştır. Kullanıcı daha büyük işleri daha küçük partilere ayırmalıdır. Boyutu sessizce ölçekleme yapılmaz.

## Kalıcılık / süreçler

- FastAPI: tek HTTP süreci; statik React build aynı origin altında sunulur.
- Worker: `fcntl` dosya kilidiyle tek süreç; birden fazla açık işi deneme sınırlarında sırayla işler.
- SQLite WAL: işler, sahiplik, ayarlar, kopyalar, en iyi yerleşim, doğrulama, yarım deneme, geçen süre ve snapshot JSON içinde saklanır.
- İşlem başına `BEGIN IMMEDIATE` güncellemesi kullanıcı eylemi ile worker'ın birbirini ezmesini önler.
- Worker her saniye kadar bir tamamlanmış-kopya checkpoint'i yazar. Aniden kapanırsa o saniyeden beri yapılmış çalışma yeniden hesaplanabilir; son kalıcı checkpoint korunur.
- Pause/stop kontrolü aday döngüsünde yaklaşık 200 ms aralıkla yapılır; tek uzun GEOS çağrısı bu sürenin aşılmasına neden olabilir.
- SSE saniyelik durum iletir; tarayıcının açık olmasına bağımlılık yoktur.
- Redis/Celery yerine bu basit tek sunucu iş kuyruğu seçildi. PostgreSQL yerine SQLite, tek işletme ve düşük eşzamanlı kullanım için kurulum yükünü azaltır. Yatay ölçek vaat edilmez.

## Güvenlik

- Parolalar scrypt; oturum HMAC imzalı, HttpOnly, SameSite Strict, internette Secure.
- Bütün iş/asset/export erişimi sahiplikle denetlenir. Önizlemeler de parolalıdır.
- Değiştiren API isteklerinde özel başlık ve origin kontrolleri; CORS açılmaz.
- Defused XML, SVG etiket/özellik kontrolleri; JavaScript, harici kaynaklar, DTD/XXE, filtre ve maskeler reddedilir.
- PDF etkin içerik, raster, form, annotations, link, güvenilemeyen katman ve desteklenmeyen boya işlemleri reddedilir.
- Docker: nonroot, salt okunur kök dosya sistemi, CPU/RAM/PID sınırı, capability drop; API/worker internet çıkışı olmayan özel Docker ağı üzerindedir.
- Dosya işleme alt süreci ayrı güvenlik kernel sandbox'ı değildir; API ile aynı konteyner kullanıcısıdır. Kullanıcılar arasında veri tabanı yetki ayrımı vardır, kernel seviyesinde müşteri başına izole container yoktur.
- API giriş denemesi sınırlaması tek sürecin belleğindedir. İnternet yayını öncesinde ağ seviyesinde ek brute-force koruması ve izleme önerilir.
- Disk kotası, kullanıcı başına CPU kotası, otomatik yedekleme, antivirüs taraması, bağımsız güvenlik incelemesi yapılmadı.

## Kaynaklar

Tasarımda yararlanılan birincil kaynaklar:

- https://pymupdf.readthedocs.io/en/latest/page.html — `get_svg_image`, `get_drawings`, `show_pdf_page`.
- https://pymupdf.readthedocs.io/en/latest/recipes-images.html — vektör SVG ile raster pixmap ayrımı.

Gerçek davranış bu teslimatta sabitlenen bağımlılık sürümleriyle otomatik test edildi; sürüm güncellemelerinde aynı kabul testleri yeniden çalıştırılmalı.
