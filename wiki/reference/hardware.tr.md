# Donanım ve durum

## Cihaz

| | |
| --- | --- |
| Model | Samsung SM-J701F, kod adı `j7velte` |
| Yonga seti | Exynos 7870 (`S5E7870`), 8 × Cortex-A53, 14 nm |
| GPU | Mali-T830 MP1 (Midgard) |
| RAM | 2 GB (Linux yaklaşık 1,6 GB görüyor) |
| Depolama | 16 GB eMMC |
| Ekran | 720 × 1280 AMOLED, EA8061S panel, DECON ekran denetleyicisi + MIPI DSI |
| PMIC | Samsung S2MPU05 (regülatörler, RTC, ses kodeği) |
| Şarj / pil ölçer / USB anahtarı | Samsung S2MU005 |
| Wi-Fi / Bluetooth | Broadcom BCM43430A1 (SDIO + UART) |
| Dokunmatik ekran | Melfas MIP4 |
| Dokunmatik tuşlar | Coreriver TC360 |
| İvmeölçer | ST LIS2HH12 |

## Mainline'da durum (Linux 7.1.13)

| Bileşen | Durum | Notlar |
| --- | --- | --- |
| Açılış | ✅ | S-BOOT → U-Boot ara katmanı → Linux |
| CPU, 8 çekirdek | ✅ | 546–1586 MHz frekans ölçekleme, yerel sürücü |
| eMMC | ✅ | DDR52, 60–80 MB/sn sıralı okuma (eski kipte 22 MB/sn idi). HS200 denendi ve kararsız (yazma hataları); açılmadı |
| USB | ✅ | Yalnızca gadget: seri kabuk ve MTP dosya erişimi (ev klasörü ve SD kart); ilk aşamalardan kalan USB ağ işlevi 2026-10-13'ten beri kapalı. MUIC anahtarını initramfs'teki bir betik ayarlıyor, şarj modülü yeniden denetliyor ve kablo türünü de okuyor. Ana makine (host) kipi yok |
| Ekran | ✅ | 2026-10-10'dan beri yerel sürücü: DECON + DSIM + EA8061S paneli; her açılışta masaüstü başlamadan önce geçilir (modüller ve aygıt ağacı eklentisi kök dosya sisteminden yüklenir; önyükleyicinin çerçeve belleği yedek yoldur, Ses Kısma tuşu basılı tutularak da seçilir). Saniyede 59,6 kare, gerçek panel parlaklığı, ekran karartma, uykudan dönüş. Bkz. [Ekran](display.md) |
| GPU | ✅ | Panfrost; 343–1001 MHz frekans ölçekleme |
| Dokunmatik ekran | ✅ | Üç küçük yama |
| Wi-Fi | ✅ | `brcmfmac`, sabit yerel yönetimli MAC adresi |
| Bluetooth | ⚠️ | Denetleyici yama yazılımı ve sabit adresle açık, BlueZ çalışıyor, tarama aygıtları buluyor. Eşleştirme ve Bluetooth ses sınanmadı |
| Ses | ⚠️ | Hoparlörden çalma ve ana mikrofondan kayıt çalışıyor. İkinci mikrofon ve kulaklık mikrofonu girişleri, kulaklık ve ahize yazıldı ama doğrulanmadı. Kulaklık takılması bildiriliyor (gerçek bir fişle henüz görülmedi) ama çıkış kendiliğinden değişmiyor. Arama sesi yok |
| Pil göstergesi | ⚠️ | Yüzde, gerilim, akım. Yonga, üretici çekirdeğinin yaptığı gibi akım ve gerilim kipleri arasında değiştirilmezse kayıyor; bunu bir betik yapıyor (`system/battery/`), şimdilik elle çalıştırılıyor, henüz açılış hizmeti değil |
| Şarj | ⚠️ | Donanım kendi kendine şarj ediyor; sürücü kabloyu, kablo türünü, şarj durumunu ve sağlığı bildiriyor iki akım sınırını kablo türüne göre ayarlıyor ve şarjı kapatıp açabiliyor (`charge_behaviour`). Sınırlar: bilgisayar girişi 500 mA giriş / 450 mA pile (önyükleyicinin değerleri), şarj girişi 1000/1000, duvar şarjı 1200/1000 (üretici: 1550/2150). Pil yardımcı betiği, pil 15 ile 41 °C arasındayken duvar şarjı değerlerini 1550/1500'e yükseltir, pil soğuk ya da sıcakken akımı düşürür. Duvar şarjı durumu yazıldı ve benzetilmiş bir sistemle sınandı, ama henüz gerçek bir duvar şarjıyla denenmedi. Dolum gerilimi ve bitiş akımı önyükleyicinin ayarı |
| Sıcaklık | ✅ | İşlemci: yerel salt okunur sürücü; 70 °C'de kısma, 105 °C'de kapanma. Pil ve kart termistörleri: SoC'nin ADC'si üzerinden küçük bir modülle (`j701f_adc`, bir hwmon aygıtı) okunuyor, açılışta yükleniyor |
| Watchdog | ✅ | 30 sn, açılıştan itibaren kurulu |
| Home tuşu, dokunmatik tuşlar | ✅ | Ana ekran, görev değiştirici ve geri'ye eşli. Son uygulamalar tuşu, sürümün `kglobalshortcutsrc` bağlamasını gerektirir; geri tuşu, uygulamanın dönecek bir yeri olduğunda çalışır (Kirigami uygulamaları, uygulama çekmecesi, klasörler), ana ekranda bir şey yapmaz |
| İvmeölçer | ✅ | `iio-sensor-proxy` okuyor ve KWin ekranı döndürüyor; yerleşim matrisi düzeltildikten sonra dört yönün hepsini telefonun sahibi doğruladı |
| Titreşim motoru | ⚠️ | `regulator-haptic`; 2026-10-13'ten beri masaüstünün titreşim hizmeti (feedbackd) kurulu ve onu sürüyor - bir geri bildirim olayı sırasında motorun beslemesi açılıyor. Elle henüz doğrulanmadı |
| microSD yuvası | ✅ | Yüksek hız kipi, yaklaşık 22 MB/sn; açılışta `/media/sdcard` altına bağlanır ve MTP ile sunulur; UHS kipleri ve tak-çıkar sınanmadı |
| Yakınlık sensörü | ⚠️ | `vcnl4000` sürücüsüyle CM36672P; okunabiliyor, `iio-sensor-proxy` görüyor, bir nesneyle doğrulanmadı, masaüstü kullanmıyor. Telefonda ortam ışığı sensörü yok, dolayısıyla otomatik parlaklık da yok |
| Donanımsal video çözme | ⚠️ | Çözücü çalışıyor: 720p bir H.264 dosyası, yazılımsal çözmeye göre yaklaşık 24 kat daha az işlemci zamanıyla çözülüyor. Açılışta yükleniyor; 360p'den 1080p'ye H.264, HEVC ve VP8 doğru çözülüyor (yazılımla bit düzeyinde aynı), MPEG-2 çalışıyor, MPEG-4 çalışmıyor. `mpv` onu kullanacak şekilde ayarlı; tarayıcılar değil |
| Modem (arama, SMS, veri) | ❌ | Başlanmadı |
| Kamera | ⚠️ | İki sensör de (arka S5K3L2, ön S5K5E3), Samsung'un FIMC-IS'ini atlayan yerel bir sürücüyle ham kare veriyor; libcamera bunları yazılımla işliyor. Plasma Camera önizleme gösteriyor, fotoğraf çekiyor ve kamera değiştiriyor. Düşük çözünürlük (arka 2072×1552), otomatik odak yok, renkler yalın, video kaydı çalışmıyor. Bkz. [Kamera](camera.md) |
| Fener | ✅ | Arka ve ön flaş LED'leri fener kipinde iki LED aygıtı olarak (arka altı kademede 25–150 mA, ön 25–50 mA); telefonun sahibi doğruladı. Plasma'nın fener kutucuğu arkadakini, "Ön flaş" uygulaması (`j701f-front-flash`) öndekini açıp kapatıyor |
| Güç alanları | ⚠️ | Sürücü yok. Dördü de açılışta açık ve açık kalıyor (kamera alanını kapatan modül, kamera kullanılmaya başlandığından emekliye ayrıldı). Video alanını elle kapatıp açmak, çözücüyü yeniden başlatmaya kadar bozdu |
| Uyku | ⚠️ | Boşta uyku çalışıyor ve yarım saniyede uyanıyor (60 saniyeye kadar saat alarmıyla uyandırarak doğrulandı). Yalnızca saat alarmıyla uyanıyor (tuşla uyandırma yeniden kaldırıldı, uygulama açılışını yavaşlatıyordu); hiçbir şey telefonu kendiliğinden uyutmuyor; güç kazancı ölçülmedi ([ayrıntılar](kernel.md#uyku)) |

## Önemli bölümler

| Ad | Aygıt | Boyut | Bu projedeki kullanımı |
| --- | --- | --- | --- |
| `BOOT` | `mmcblk0p10` | 32 MiB | Mainline çekirdek imajı |
| `RECOVERY` | `mmcblk0p11` | 38 MiB | Projenin grafik kurtarma ortamı (2026-10-10'dan beri); yerini aldığı üretici 3.18 imajı dosya olarak saklanıyor |
| `SYSTEM` | `mmcblk0p18` | 3 GiB | Dokunulmadı |
| `USERDATA` | `mmcblk0p24` | 11,1 GiB | Alpine kök dosya sistemi (ext4) |

Bölüm numaraları bu telefondaki gözlemlerdir. Araçlar bölümleri yalnızca numarayla değil; ad, boyut ve içerikle tanır.

## Bilinmeye değer adresler

| Ne | Nerede |
| --- | --- |
| Önyükleyici çerçeve belleği | `0x67000000`, 720 × 1280, 32 bpp |
| GPU | `0x11400000`; saatler `0x11460000`'daki `CMU_G3D`'den; besleme `BUCK2` |
| CPU saat denetleyicileri | küme 0 `0x10900000`, küme 1 `0x10800000`; besleme `BUCK1` |
| Sıcaklık sensörü | `0x10130000` |
| Watchdog | `0x10170000` |
| Ses: I²S / mikser / DMA / sıfırlamalar | `0x148a0000` / `0x14880000` / `0x14890000` / `0x148f0000` |
| Ses ve ekran saatleri (`CMU_DISPAUD`) | `0x148d0000` |
| PMIC | `0x10510000`'daki I²C veri yolu, adres `0x66`; ses kodeği aynı yolda `0x04` |
| USB anahtarı (MUIC) | `0x13870000`'daki I²C veri yolu, adres `0x3d` |

## Ölçülen değerler

**Frekansa göre CPU gerilimi** (`BUCK1` regülatörü, üretici çekirdeği altında okundu; sürücü 12,5 mV ekler):

| MHz | 546 | 676 | 757 | 839 | 902 | 1014 | 1144 | 1248 | 1352 | 1482 | 1586 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mV | 625,00 | 668,75 | 693,75 | 712,50 | 737,50 | 781,25 | 825,00 | 868,75 | 906,25 | 956,25 | 1006,25 |

**GPU kademeleri:** 343, 450, 545, 676, 728, 845, 1001 MHz. Mainline tablosu 775 mV'un (açılıştaki değer) altına hiç inmez, çünkü `BUCK2` GPU'dan fazlasını besliyor olabilir; 845 MHz 850 mV, 1001 MHz 943,75 mV kullanır.

**Mainline'da başarım ölçümleri:**

| Sınama | Sonuç |
| --- | --- |
| `sysbench cpu`, 1 iş parçacığı, 1586 MHz | 741 olay/sn (902 MHz'de 421) |
| `sysbench cpu`, 8 iş parçacığı, 1586 MHz | 5146 olay/sn |
| `es2gears_wayland`, vsync kapalı, GPU 1001 MHz | yaklaşık 730–820 FPS (343 MHz'de yaklaşık 250) |
| 4 dakika, tüm çekirdekler ve GPU en yüksekte | 54 → 60 °C |
