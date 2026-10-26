# Tarayıcı kaydırmasını ölçmek

`bench/scroll/`, Angelfish'i aynı iş yükü altında karşılaştırmak için sabit bir
yerel sayfadır. 96 kartında metin, renkli desenler ve gölgeler bulunur. Dış
kaynak, ses veya video yoktur. İçerik güvenliği politikası da sayfanın medya
oynatmasını ve bağlantı kurmasını engeller.

Sayfa saniyede 700 CSS pikseli kayar, iki saniye ısınır ve on iki saniye ölçüm
yapar. `requestAnimationFrame` aralıklarını, bunların ortancasını, yüzde 95 ve
99 değerlerini, 25 veya 50 ms'yi aşan aralıkları kaydeder. Tahmini kaçırılan
60 Hz aralıkları, callback boşluklarından hesaplanır; ölçülmüş ekran flip'leri
değildir. **Tap response** düğmesi, çalışma sırasında olaydan işleyiciye ve
işleyiciden sonraki callback'e kadar geçen süreleri kaydeder.

## Neyi gösterebilir?

Aynı görüntü alanı, ölçek, kernel, tarayıcı seçenekleri ve geri yüklenen
sekmelerle en az üç çalışma karşılaştırılmalıdır. CPU/GPU frekanslarını,
sıcaklığı, bellek ve swap kullanımını, kernel uyarılarını da kaydedin. Her
seferinde tek değişken değiştirin. Varsayılan olarak görüntü alanı veya ölçek
değişikliği, sekmenin gizlenmesi ya da zaman sınırının aşılması çalışmayı geçersiz kılar.
İptal edilen çalışma saklanır fakat ölçüm sayılmaz.

Angelfish kaydırırken üst çubuğu gizleyebilir; bu yalnızca sayfa yüksekliğini
değiştirir. Bu durumda **Allow browser toolbar height changes** seçeneğini veya
denetleyicide `--viewport toolbar` kullanın. Bu açık seçenek, başlangıç
yüksekliğinin %25'i içindeki yükseklik değişimlerini kabul eder, kaydırma sınırını
günceller ve her değişikliği, ölçüm aşamasını ve yükseklik aralığını `viewport`
alanına kaydeder. Genişlik/ölçek veya daha büyük yükseklik değişimi yine geçersizdir.
Seçenek değişikliğin nedenini belirleyemez; yalnızca üst çubuğun hareket ettiğini
kanıtlamaz. Aynı seçenekle ve benzer yükseklik aralığı/olaylarıyla yapılan
çalışmaları karşılaştırın. Boyut değişiminin maliyeti ölçümde kalır, yavaş kareler
silinmez. `--viewport fixed` katı varsayılan davranışı korur.

Tarayıcı callback'leri fiziksel panelin kare hızını veya dokunmadan görünür
tepkiye kadar geçen süreyi göstermez. Programla kaydırma, parmakla kaydırmadan
farklıdır. İyi bir zamanlama sonucu veya compositor ekran görüntüsü, telefonda
siyah alan olmadığını kanıtlamaz; bunlar ayrı fiziksel kontrol gerektirir.
Sayfa ağ hızını veya uygulamanın soğuk açılışını da ölçmez.

## Elle çalıştırmak

Laptopta yalnızca benchmark dizinini sunun:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory bench/scroll
```

Mevcut sabitlenmiş SSH bağlantısı üzerinden sunucuyu telefona yönlendirin:

```sh
ssh -N -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=build/phone-ssh-known-hosts \
  -R 127.0.0.1:8765:127.0.0.1:8765 \
  burak-alpine@192.168.1.158
```

Koordinasyonun `phone` kilidi sizdeyken Angelfish'te
`http://127.0.0.1:8765/` adresini açın. Ön planda tutup Start'a basın ve JSON'u
kaydedin. Laptop sunucusu ve SSH tüneli çalışıyor olmalıdır. Test bitince ikisini
de durdurun; kalıcı sunucu veya açılış ayarı gerekmez.

## Otomatik toplamak

`tools/scroll-benchmark.mjs`, loopback Chrome DevTools Protocol uç noktasıyla
**önceden açılmış** tam bir benchmark sekmesine bağlanır. Başka sekme açmaz,
adreslerini değiştirmez. Node 22+ veya `--experimental-websocket` ile Node 20
kullanın. Qt WebEngine'in hata ayıklama uç noktası Angelfish başlamadan
etkinleştirilmiş olmalıdır. Tarayıcıyı yeniden başlatmak veya ortamını
değiştirmek koordineli bir telefon işlemidir. Uç noktayı ağa açmak yerine
loopback üzerinde tutup tünelleyin.
Qt, [`QTWEBENGINE_REMOTE_DEBUGGING`](https://doc.qt.io/qt-6/qtwebengine-debugging.html)
için adres ve port biçimini belgeler.

Laptopun 9222 portunda loopback uç noktası hazır olduğunda:

```sh
tools/coord.sh lock phone codex "Angelfish scroll baseline" 15
node --experimental-websocket tools/scroll-benchmark.mjs \
  --scope phone --worker codex --seconds 12 --warmup 2 --viewport toolbar \
  --out build/bench/phone-baseline-01.json
tools/coord.sh unlock phone codex
```

Başka çalışanın aktif kullandığı kilidi almayın. Telefon çalışması, yeterli
süresi kalan güncel ve eşleşen kilit gerektirir. Araç mevcut sonuç dosyasının
üzerine yazmaz. JSON'da user agent, görüntü alanı, tek tek aralıklar, toplu
istatistikler ve denetleyicinin beklediği dosya hash'leri bulunur. Hash'ler yerel
kaynakları tanımlar; tarayıcı önbelleğini doğrulamaz. Değişiklikten sonra sayfayı
yenileyin. Masaüstü işlev kontrolünde `--scope host-check` kullanın; bunu telefon
performansı kanıtı saymayın.

## Çalışmaya eşlik eden sayaçlar

`tools/phone-perf-sample.py`, sabitlenmiş SSH bağlantısıyla sınırlı sayıda salt
okunur örnek toplar. Aynı çalışanın telefon kilidini gerektirir. Tarayıcı
çalışmasından hemen önce laptopta başka bir terminalde başlatın:

```sh
python3 tools/phone-perf-sample.py --worker codex --samples 24 \
  --out build/bench/phone-baseline-01-counters.json
```

İki program da bitene kadar kilidi tutun. Telefona dosya kurulmaz. Araç toplam
CPU sayaçlarını toplam ve çekirdek başına, bildirilen CPU/devfreq frekanslarını, sıcaklık bölgelerini,
kullanılabilir belleği, swap'ı ve seçili VM geri kazanım/hata sayaçlarını okur.
Bu kayıtta telefonda olduğu gibi `/proc/pressure` yoksa PSI açıkça erişilemez
olarak işaretlenir. Yeniden açılış veya sayaç sıfırlanması toplu hesabı geçersiz
kılar. Kesilen çıktının tamamlanmış örnekleri saklanır, ancak geçerli çalışma
sayılmaz. Mevcut JSON dosyasının üzerine yazılmaz.

Örneklerde telefonun uptime'ı ve saniye hassasiyetli duvar saati; tarayıcı
raporunda duvar saati ve performance zaman kökü bulunur. Bunlar yaklaşık
eşleştirme sağlar, tek bir kareye kesin neden atamaz. Örnekler arasında bir
saniye beklenir ve okuma süresi kaydedilir: ölçüm yük ekler ve tam 1 Hz değildir.
CPU meşgul yüzdesi tüm çekirdeklerin ortalamasıdır, iowait'i içermez; tek bir
meşgul iş parçacığını dışlayamaz. Yalnızca frekanslar darboğazı kanıtlamaz.
Toplama maliyeti önemliyse aynı koşulu sayaç kaydıyla ve kayıtsız karşılaştırın.

## Şimdiye kadarki doğrulama

2026-10-10'da ayrı bir masaüstü Chromium örneği sınırlı süreli çalışmayı
tamamladı. Yedi tarayıcı kontrolü geçti: sayfa kimliği, sınır denetimi, tekrar
çalıştırmada geometri, iptal, gönderilmiş dokunma örneği, boyut değişiminde ve
gizlenme yaşam döngüsünde geçersizlik. Sayfanın görüntüsü incelendi.
Ardından 13 kontrollü Chromium çalışması sınırlı üst çubuk boyut değişimini ve
geometrinin geri gelmesini, katı yükseklik reddini, büyük yükseklik değişiminin
reddini, ölçek/genişlik reddini ve önceki yaşam döngüsü/girdi kontrollerini doğruladı.
Kanıt: `build/bench/host-toolbar-browser-checks.json`.
Diğer kanıtlar `build/bench/host-*` altında.
**Bu araçla henüz telefon sonucu toplanmadı.**

Sayaç toplayıcının sekiz bütünlük testi CPU guest hesabını, birimleri, çekirdek
başına hesap/hotplug'ı, eksik PSI'yi, boşluklu sıcaklık adlarını, kesilmiş çıktıyı,
yeniden açılışı ve sayaç sıfırlanmasını kapsar. Gerçek kabuk betiği laptopta iki örneği de tamamladı
(`build/bench/host-telemetry-functional.json`). Bu, bilgisayardaki bütünleşme
kontrolüdür; telefon benchmark'ı değildir.

Ölçümler belgelenmiş
[requestAnimationFrame API'sini](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame)
ve [CDP Runtime API'sini](https://chromedevtools.github.io/devtools-protocol/tot/Runtime/)
kullanır.
