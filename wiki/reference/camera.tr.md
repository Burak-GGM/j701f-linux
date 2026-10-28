# Kamera

!!! success "Durum: iki kamera da sıradan birer Linux kamerası (2026-10-10)"
    Ana hat çekirdeğinde Plasma Camera'da canlı önizleme, fotoğraf çekme ve arka/ön kamera arasında geçiş çalışıyor (enjekte dokunuşlarla denendi). Ön kamerada Auto çözünürlükte ve arka kamerada 540p'de kısa video kayıtları çalışıyor; arka kameranın Auto kaydı bellek baskısı altında hâlâ başarısız. Telefonun sahibi onunla fotoğraf çekti; fotoğraflar tepetaklak çıktı, döndürme düzeltildi ve düzeltmeyi doğrulayan bir fotoğraf hâlâ bekleniyor.

## Ne çalışıyor

İki sensör de libcamera'ya "Internal back camera" ve "Internal front camera" olarak görünüyor; libcamera üzerine kurulu uygulamalar - en başta Plasma Camera - onları görüyor. Sürücü açılışta yükleniyor.

| | Arka | Ön |
| --- | --- | --- |
| Sensör | Samsung S5K3L2, 13 MP | Samsung S5K5E3, 5 MP |
| Sunulan kip | 2072 × 1552 (3,2 MP), saniyede 30 kare | 1280 × 960 (1,2 MP), saniyede 30 kare |

Renk, pozlama ve beyaz dengesi libcamera'nın yazılımsal görüntü işlemesiyle işlemcide yapılıyor; arka kamerada kare başına yaklaşık 50 ms.

## Nasıl çalışıyor

Samsung'un kamera yazılımından hiçbir şey kullanılmıyor - ne sürücüsü ne de kapalı görüntü işlemci yazılımı.

1. **Sensör.** Üreticinin sırasıyla güç verilir ve I2C üzerinden üreticinin bir kipe ait yazmaç tablolarıyla programlanır.
2. **CSI-2 alıcısı.** Bu yonga setinin alıcısının kendi DMA çıkışı var; ham Bayer karelerini doğrudan belleğe yazıyor, paketlemesi kapatıldığında düz 16 bitlik örnekler olarak - standart bir V4L2 ham biçimi. Başka bir donanım bloğuna gerek yok.
3. **`tools/kmod/j701f_camera.c`.** Her sensör için bir medya aygıtı, bir sensör alt aygıtı (pozlama ve kazanç denetimleri) ve bir yakalama video düğümü. Alıcı sırayla iki arabelleğe yazar, küçük bir iş parçacığı biten her kareyi uygulamaya kopyalar.
4. **libcamera** (Alpine'in paketi, değiştirilmemiş): genel işlem hattı ve yazılımsal görüntü işleme; sonra uygulama.

## Bulunması gerekenler

- **Saatler.** Kamera bloğunun saat denetleyicisinin bizim ağacımızda sürücüsü yok ve önyükleyici seçicilerini 26 MHz osilatörde bırakıyor. Üç seçici gerçek saatlere çevrilene kadar kareler sağlama hatalarıyla geliyordu.
- **Bloğun IOMMU'su**, video çözücününki gibi, sayfa tablosu olmadan etkin başlıyor; sürücü yakalama sırasında onu adresleri geçirecek şekilde ayarlıyor.
- **Ön kameranın alıcısı**, sensör yayın yaptığı halde hiçbir şey görmüyordu: üreticinin PHY sürücüsü bir sistem yazmacında ana hat PHY sürücüsünün bilmediği bir bit daha kuruyor.
- **libcamera genel işlem hattında yalnızca bildiği platform sürücülerini kabul ediyor.** Bu yüzden medya aygıtı sürücü adını `qcom-camss` olarak veriyor; listede yazılımsal işlemesi açık olan bir giriş. Bunun dışında Qualcomm'la ilgisi yok; temiz seçenek, o listede bir satırı daha olan bir libcamera.
- **Bir dma-buf sağlayıcısı.** libcamera'nın yazılımsal işlemesi buna ihtiyaç duyuyor ve BOOT'taki çekirdekte yok; çekirdeğin `udmabuf` sürücüsü ayrı bir modül olarak derlendi, çekirdeğin dışa aktarmadığı bir işleve ihtiyaç duyan tek denetimi çıkarılarak.
- **GPU mu işlemci mi.** GPU yolunda libcamera'nın deneme programı bu telefonda yaklaşık her üç başlatmadan birinde durdu; oturum `LIBCAMERA_SOFTISP_MODE=cpu` ayarlıyor (`~/.config/plasma-workspace/env/j701f-camera.sh`; sürüm bunu 2026-10-27'den beri kuruyor. İlk sürümde eksikti: Plasma Camera kamera değiştirirken çöküyor ve takılıyordu).

## Yolda yapılan hatalar

- İki sensörün paylaştığı bir GPIO'yu iki aygıttan "paylaşımlı" istemek, modül yeniden yüklendikten sonra bozuldu ve çekirdeği çökertti. Anahtar artık aygıt ağacında bir regülatör.
- Paketsiz düzenin bir denemesi arabelleğinin 140 kB ötesine yazdı: boyut koruması piksel başına baytı değil sensör kipini denetliyordu. Telefon hemen yeniden başlatıldı; arabellekler artık düzene göre boyutlanıyor.
- Yüklü bırakılan bir deneme modülü, ilk anlık çekim başlatıcılarının telefon sahibinde "FileNotFoundError" vermesine yol açtı.

## Eksikler

- Tam çözünürlük (şimdilik sensör başına tek kip), otomatik odak (arka mercek odaklanmıyor, sabit bir konumda tutuluyor: DW9807 motoru `hsi2c@138b0000` üzerinde 0x0c adresinde, `j701f_camaf.ko` bu hattı çalışma anında açıyor; `j701f_camera` konumu modülün 0x58'deki EEPROM ayar verilerinden ya da `focus` parametresinden alıyor), çekim sırasında flaş.
- Arka mercek konumu elle: `echo 600 | sudo tee /sys/module/j701f_camera/parameters/focus` (`-2` = ayar verisinden hesaplanan varsayılan, sahibin telefonunda 528: sonsuz kodu 506'ya makro kodu 727'ye doğru onda bir eklenir; `-1` = sürülmez). Sahip kamerayı varsayılan konumla kullandı ve iyi buldu; keskinlik taraması yapılmadı.
- Sensör ayarı: renk matrisi ve mercek gölgeleme düzeltmesi yok; libcamera iki sensörü de tanımıyor ve bunu söylüyor.
- Otomatik pozlama yavaş tırmanıyor: loş bir odada resmin aydınlanması birkaç saniye sürüyor.
- Görüntü döndürmesi: arka kamera için ilk tahmin fotoğrafları tepetaklak verdi (telefon sahibinin bildirimi); şimdi 270°. Ön kameranın 90° değeri ayna varsayımıdır, denetlenmedi.
- Arka kamerada varsayılan Auto çözünürlükte video kaydı kullanılabilir belleği tüketip geçersiz MP4 bırakıyor; 540p kayıt yapıyor ama 4:3 görüntüyü 16:9'a esnetiyor.

## Video kaydı ve bellek

Plasma Camera 2.1.1 kayıt yaparken her önizleme görüntüsünü (bir `QImage`) QtMultimedia'nın `QVideoFrameInput`'una verir; `QMediaRecorder` MP4, H.264 ve MP3'e ayarlıdır ve varsayılan mikrofon da eklidir. `tools/camera/qt-recorder-probe.cpp` tam olarak bunu yapar; sürümün kendi AArch64 Qt 6.11.1'ine karşı derlenip bilgisayarda `qemu-aarch64` altında çalıştırıldı:

- **Yolun kendisi çalışıyor.** Mikrofonlu da mikrofonsuz da deneme programı geçerli bir MP4 (H.264 ve MP3) yazıyor. Qt 6.11 kayıtta V4L2 donanım kodlayıcılarını hiç kullanmıyor (kodlayıcı listesi `*_v4l2m2m` kodlayıcılarını kapatıyor); kodlayıcı her zaman varsayılan `medium` ayarlı yazılımsal `libx264`, Qt yalnızca kaliteyi (`crf`) ayarlıyor.
- **Renk biçimi.** RGB görüntülerden Qt YUV 4:4:4 seçiyor; dosya H.264 *High 4:4:4 Predictive* oluyor ve donanım çözücüleri (telefonun MFC'si de) ve pek çok oynatıcı bunu oynatamıyor. Düzlemsel YUV 4:2:0 kareler sıradan *High* profilini veriyor ve daha çok karenin geçmesini sağlıyor (kamera boyutunda 60 karenin 18'i yerine 56'sı).
- **Bellek.** Kayıt sürecinin en yüksek bellek kullanımı, 60 kare: 320 × 240'ta 195 MB, 960 × 540'ta 485 MB, 1280 × 720'de 622 MB, **2072 × 1552'de 1,07 GB** — arka kameranın kare boyutu; Plasma Camera'nın varsayılan "Auto" çözünürlüğü bu boyutta kaydediyor. Telefonda masaüstü çalışırken, kameranın kendi tamponlarından önce, yaklaşık 1,2 GB boş bellek var; bu noktada sistem yoğun biçimde takas alanına yazıyor ve `earlyoom` (`-m 4 -s 8`) en büyük süreci, yani kamera uygulamasını öldürüyor. İkisi de boş ya da yarım bir dosya bırakır.

Telefonda (2026-10-28) ön kamera Auto çözünürlükte 1276 × 960 boyutunda geçerli, 9,33 saniyelik MP4 üretti. Arka kamera Auto çözünürlükte `moov` atomu olmayan 48 baytlık MP4 bıraktı ve altı saniye sonra kamera süreci kapandı; kullanılabilir bellek 643 MB'tan 95 MB'a, boş takas alanı 889 MB'tan 647 MB'a düştü. Süreci sonlandıran sinyal yakalanmadı. Plasma Camera'nın 540p ayarında (`~/.config/plasmacamerarc` dosyasının `General` grubunda `videoResolution=1`) arka kamera 960 × 540 boyutunda geçerli, 6,92 saniyelik MP4 üretti. Süreç çalışmayı sürdürdü ve yerleşik belleği en çok 491 MB oldu. Bu, bellek sorununu telefonda doğruluyor; ancak 4:3 görüntü 16:9'a eziliyor: Plasma Camera yalnızca 16:9 ayarlar sunuyor. Bu yüzden 540p hâlâ deneme ayarı, varsayılan değil. Kalıcı çözüm, Plasma Camera'dan YUV 4:2:0 kareler göndermek, en-boy oranını bozmadan sensör boyutunun altında kaydetmek ve mümkünse daha hafif bir x264 ayarı kullanmak olur; Qt bu ayarı dışarı açmıyor. Denemeden sonra eski ayar geri getirildi ve videolar oynatılmadan silindi.
- Bloğun saatleri, güç alanı ve IOMMU'su için yazmaç yazımları yerine düzgün sürücüler; yoklama yerine alıcının kesmesi; kare başına kopyasız çalışma.
- libcamera yerine PipeWire'ın kamera kapısını ya da düz V4L2'yi kullanan uygulamalar denenmedi.

## Neresi nerede

| Yol | İçerik |
| --- | --- |
| `kernel/dts/exynos7870-j7velte-camera.dts` | iki sensör düğümü: hatlar, beslemeler, GPIO'lar, saatler, D-PHY'ler, yön |
| `tools/kmod/j701f_camera.c`, `s5k3l2-tables.h`, `s5k5e3-tables.h`, `gen-s5k3l2-tables.py` | sürücü ve dönüştürülmüş üretici tabloları |
| `tools/kmod/udmabuf-out-of-tree.patch` | çekirdeğin udmabuf sürücüsünü modül olarak derlemek için yapılan değişiklik |
| `system/camera/` | modüllerin açılış yükleme betiği, udev kuralı, oturum ortamı; `j701f-photo` (önceki anlık çekim aracı) |
| `tools/kmod/j701f_cam_probe.c`, `j701f_cam_frame.c`, `j701f_cam_stream.c` | devreye alma sırasındaki üç deneme modülü |
| `build/kernel/vendor-camera-reference/` | başvurulan üretici dosyaları (deponun parçası değil) |
