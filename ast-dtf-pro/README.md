# AST DTF NESTING PRO — 0.1.0

Türkçe, sunucu tarafında çalışan vektör DTF yerleştirme uygulaması.

**Durum: çalışan, otomatik testleri olan kontrollü geliştirme sürümü. Eksiksiz üretim onayı verilmiş bir ürün değildir.** Desteklenen dosyalarda gerçek PDF → adet → şekil yerleşimi → vektörel PDF akışı çalışır. Gerçek iPad Safari, Illustrator ve RIP baskı kabul testleri henüz yapılmamıştır. Ayrıntılar: `docs/LIMITATIONS.md`, `docs/TEST_REPORT.md`.

## Hızlı kurulum — Docker

Windows'ta Docker Desktop / Linux sunucuda Docker Engine + Compose gerekir. iPad'e kurulum yapılmaz; kurulmuş sunucunun adresi Safari'de açılır.

1. ZIP'i çıkarın; terminali bu klasörde açın.
2. `.env.example` dosyasını `.env` olarak kopyalayın.
3. Rastgele uygulama anahtarı üretin:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Üretilen değeri `.env` içindeki `AST_SECRET` değerine yapıştırın. Dosyayı paylaşmayın. Yerel testte `AST_SECURE_COOKIE=0`, `AST_ORIGIN=http://localhost:8000` kullanın.

4. Derleyin ve ilk hesabı oluşturun:

```sh
docker compose build api
docker compose run --rm --no-deps api python manage.py create-user ast
```

En az 12 karakterli parolanızı iki defa girin. Hazır/ortak parola yoktur.

5. Başlatın:

```sh
docker compose up -d api worker
```

Windows bilgisayarda `http://localhost:8000` açın. Yerel adres internet yayını değildir. iPad için aşağıdaki HTTPS sunucu kurulumunu tamamlayın.

## İnternetten / iPad'den erişim

Linux sunucuda Docker kurulu olmalı. Başlangıç için 4 CPU, 8 GB RAM ve en az 20 GB disk planlayın; karmaşık dosyalarda kapasiteyi ölçün. Bu kapasite bir performans garantisi değildir.

1. Projeyi sunucuya kopyalayın; Docker kurulum adımlarını uygulayın.
2. `dtf.firmaniz.com` gibi kendi alan adınızın DNS A kaydını sunucunun IP adresine yönlendirin.
3. Sunucuda TCP 80/443 ve tercihen UDP 443 açın. 8000 portunu internete açmayın.
4. `.env` dosyasını düzenleyin:

```dotenv
DOMAIN=dtf.firmaniz.com
AST_ORIGIN=https://dtf.firmaniz.com
AST_SECURE_COOKIE=1
AST_SECRET=YUKARIDA_URETTIGINIZ_GIZLI_ANAHTAR
```

5. Başlatın:

```sh
docker compose --profile internet up -d
```

Caddy, doğru DNS ve erişilebilir 80/443 koşullarında TLS sertifikasını otomatik alır. iPad Safari ve Windows Chrome/Edge aynı HTTPS adresini kullanır. Site parolalıdır; her kullanıcı yalnızca kendi işlerine erişir. Yeni kullanıcı eklemek için `create-user` komutunu başka adla çalıştırın.

**Bu teslimatta internete yayın yapılmadı. Docker burada çalıştırılamadı; yapılandırma sağlandı, Docker build/Compose/TLS uçtan uca doğrulanmış sayılmaz.**

## Kullanım

1. Yeni iş adı girin.
2. PDF / SVG / PDF uyumlu AI yükleyin. Her sayfa tek logo grubu olur; yanlış otomatik bölme yapılmaz.
3. Koyu arka plandaki logoyu kontrol edin. Her satırda **ADET** kutusu vardır; 1–1000 girilir. İş toplamı en fazla 1000.
4. Ölçüyü değiştirecekseniz genişlik girin; yükseklik aynı oranda değişir. Varsayılan yüklemede kaynak ölçüsü değiştirilmez. Gösterilen ölçü gerçek mürekkep sınırının vektör geometrisinden hesaplanır; yaklaşık 0,015 mm eğri düzleştirme toleransı vardır. Çakışma güvenlik payı ölçüden ayrı tutulur; logoya eklenmez.
5. “Bu sayfa tek bir bütün logo grubudur” onayını verin. Beyaz sayfa boyu dikdörtgen varsa ayrıca beyaz nesnenin baskıya dahil olduğu belirtilir. Nesne otomatik silinmez.
6. Film genişliği 580 mm; her kenarda 5 mm; baskılar arasında 3 mm varsayılandır. Ayar değişikliği eski yerleşimi sıfırlar.
7. Otomatik Diz'e basın. İlk geçerli tam yerleşim kaydedilir; sonraki denemeler daha kısa sonuç arar.
8. Duraklat: mevcut denemenin kopya listesi korunur. Devam et: bu durumdan devam eder. Durdur: yarım deneme atılır, en iyi tam sonuç korunur.
9. Önizlemede logoya dokunun; X, Y ve açı değerlerini düzenleyin. Çakışan değişiklik reddedilir. Görsel tutup sürükleyerek taşıma henüz yoktur; sayısal taşıma vardır.
10. PDF indir. Dosya indirilmeden önce adet, sınır ve geometriler arası mesafe yeniden doğrulanır.

CMYK/spot içeren işlerde SVG indirme engellenir. Böylece renkler sessizce RGB'ye dönüştürülmez. Üretimde PDF kullanın. Ekran önizlemesi RGB'dir.

## Geliştirici kurulumu

Python 3.12 ve Node 24 kullanın:

```sh
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.lock
npm ci --prefix frontend
npm run build --prefix frontend
```

`AST_SECRET`, `AST_SECURE_COOKIE=0` ve isteğe göre `AST_DATA` ortam değişkenlerini tanımlayın. `.env` yalnız Docker Compose tarafından otomatik okunur; yerel Python çalıştırmasında ortamınıza kendiniz aktarın.

```sh
python manage.py create-user ast
uvicorn backend.api:app --host 127.0.0.1 --port 8000 --workers 1
```

İkinci terminalde aynı ortam değişkenleriyle:

```sh
python -m backend.worker
```

**Backend/worker Linux içindir.** Unix `resource` ve `fcntl` kullanır. Windows'ta Docker veya WSL2 kullanın. Windows tarayıcı istemcisi destek hedefidir; native Windows Python worker değildir.

## Testler

```sh
python -m pytest -q
python -m tests.benchmark
python -m tests.real_file /tam/yol/tek-logo.pdf --output examples/real-file
npm run build --prefix frontend
```

İş verileri `data/ast.sqlite`, yüklenen orijinaller ve normalleştirilmiş sayfalar `data/jobs/` altındadır. Web API: `/docs`. Geometri motoru kendi dosyanızda test edilmeden baskıya göndermeyin.

## Yedekleme ve işletim

- Tek API ve tek worker çalıştırılır. SQLite WAL yerel diskte tutulur; NFS ve yatay ölçek desteklenmez.
- Docker `ast-data` hacmi kalıcıdır. `docker compose down -v` tüm işleri siler; normal durdurmada `-v` kullanmayın.
- Tutarlı yedek için API/worker'ı durdurup `ast-data` hacmini ve `.env` anahtarını şifreli yedekleyin, sonra başlatın. Yedekten dönüşü ayrıca deneyin.
- `docker compose logs -f api worker` ile hataları izleyin. Disk doluluğunu işletim sistemi üzerinden izleyin. Disk kotası ve otomatik iş saklama politikası bu sürümde yoktur.
- İndirilmiş geçici çıktılar istek sonunda silinir; çöken indirmelerden kalan 24 saatten eski dosyalar API başlangıcında temizlenir.
- Kullanıcı orijinal dosyaları saklanır; silinen logo satırlarının orijinalleri iş arşivinde kalır. Tam iş silme ve kullanıcı yönetim arayüzü henüz yoktur.
- Şifreler scrypt ile saklanır. Sunucu anahtarını değiştirmek mevcut oturumları geçersiz kılar.

## Lisans

Proje kaynak kodu bu teslimatın parçasıdır. Bağımlılık lisansları ayrıca geçerlidir. Özellikle PyMuPDF/MuPDF'nin AGPL veya ticari lisans koşulları dağıtım biçiminize göre değerlendirilmelidir; ticari lisansın satın alındığı iddia edilmez. Diğer bağımlılıkların lisans bildirimlerini dağıtımda koruyun.
