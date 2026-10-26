# Araçlar ve iş akışı

`tools/` içindeki her şey, aksi belirtilmedikçe geliştirme bilgisayarında çalışır. Araçlar bilerek katıdır: girdileri özetle sabitler, sonuçları denetler ve tahmin yürütmek yerine durur.

## Gündelik döngü

```sh
# 0. Yalnızca çekirdek kaynakları, yamalar ya da yapılandırma değiştiyse: çekirdeği derle
python3 tools/build-kernel.py panfrost --jobs 11

# 1. Bir imaj derle ve doğrula (telefona hiçbir şey dokunmaz)
tools/build-mainline-image.sh AD kernel/dts/exynos7870-j7velte-camera.dts "--allow-audio --allow-sd --allow-mfc"

# 2. Gerçekten bir imaj ürettiğinden emin ol
ls build/kernel/boot-update-AD/boot-mainline.img

# 3. Kur ve telefonu onunla yeniden başlat
tools/run-recovery-update.sh AD
```

`AD`, kademe için kısa bir etikettir (`gpufreq`, `audio4`, …). Her kademe `build/kernel/` altında kendi dizinlerini tutar; böylece daha önceki herhangi bir imaj yeniden kurulabilir.

!!! warning "2. adımı atlamayın"
    1. adımın çıktısı `tail` ya da `grep`'e yönlendirilirse kabuk, derlemenin değil o son komutun çıkış durumunu bildirir. Başarısız bir derleme iki kez bu yüzden fark edilmedi ve telefon, var olmayan bir güncelleme için boşuna yeniden başlatıldı.

!!! warning "1. adım çekirdeği derlemez"
    `build-mainline-image.sh`, en son derlenmiş çekirdek neyse onu paketler. Bir yama değişikliğinden sonra 0. adımı atlamak, içinde eski çekirdek olan tamamen geçerli bir imaj üretir. Bu bir kez oldu: imaj kuruldu ve "düzeltme" basitçe orada değildi.

!!! note "Bilgisayar yeniden başladıktan sonra"
    Çekirdek çalışma ağacı `/tmp` içindedir ve bilgisayar yeniden başlayınca boşalır. 0. adım onu yeniden kurar; derleme yinelenebilir olduğundan aynı çekirdek yapı kimliğini verir, böylece telefondaki modüller uyumlu kalır. Ayrı derlenen modüller (`tools/kmod/`, şarj sürücüsü, ekran modülleri) ayrıca `Module.symvers` ister ve 0. adım bunu yalnızca istenirse üretir: bunlardan birini derlemeden önce 0. adımı `python3 tools/build-kernel.py panfrost --jobs 11 --modules` olarak çalıştırın (yoksa her çekirdek simgesi tanımsız diye bildirilir).

1. adımda adı geçen aygıt ağacı zincirin tepesidir (`camera.dts` ötekilerin hepsini içerir); zincirdeki daha eski bir dosyadan kurulan imaj açılır, ama sonraki dosyaların eklediklerinden yoksun olur. 3. adım telefonu projenin kurtarma ortamına yeniden başlatır (dosya sistemlerini temiz kapatan `system/reboot-recovery.sh` ile), `BOOT`'u kurtarma ortamına yazdırıp geri okutur ve yeni imajla yeniden başlatır; kurtarma ortamı sistemle aynı Wi-Fi adresini ve ana makine anahtarını kullanır. `J701F_PHONE_IP=192.168.x.y` başka bir adres verir. Üretici sistemi üzerinden giden eski `run-boot-update.sh`, üretici imajı artık `RECOVERY`'de olmadığından çalışmayı reddeder.

`BOOT`'ta o an bulunan imaj, hazırlanmış bir güncellemenin beklediği imaj değilse (örneğin eski bir imaja geri dönüldükten sonra), güncellemeyi yeniden hazırlayın:

```sh
python3 tools/prepare-boot-update.py --handoff-dir build/kernel/handoff-AD \
    --output-dir build/kernel/boot-update-AD \
    --phone-dir /home/burak-alpine/j701f-boot-update-AD
```

## Derleme araçları

| Araç | Amaç |
| --- | --- |
| `build-kernel.py` | Çekirdeği indir, yamala, yapılandır ve derle; kaynağı, yamaları ve yapılandırmayı özetle sabitler |
| `build-j701f-dtb.py` | Kart aygıt ağacını derle ve doğrula; `--allow-emmc`, `--allow-gpu`, `--allow-wifi`, `--allow-audio`, `--allow-sd` |
| `build-mainline-initramfs.py` | initramfs'i yardımcılar ve Wi-Fi yazılımıyla kur |
| `build-mainline-fit.py` | Çekirdek, aygıt ağacı ve initramfs'i bir FIT imajında topla |
| `build-j701f-uboot.py` | Yamalı U-Boot'u, FIT imajı gömülü olarak derle |
| `package-embedded-mainline-diagnostic.py` | U-Boot'u S-BOOT'un kabul ettiği Android imajına sar |
| `validate-embedded-ramboot-guards.py` | Yükleyicinin sağlam imajları kabul ettiğini ve 15 tür bozuk imajı reddettiğini denetle |
| `trace-j701f-uboot.py` | Yükleyiciyi QEMU'da Linux'a atlama noktasına kadar çalıştır |
| `build-mainline-image.sh` | Yukarıdakilerin hepsi sırayla, artı birim testleri ve güncelleme hazırlığı |
| `prepare-boot-update.py`, `run-boot-update.sh` | `BOOT`'a korumalı bir yazmayı hazırla ve gerçekleştir |
| `run-recovery-update.sh` | Aynı güncellemeyi üretici sistemi yerine projenin kendi kurtarma ortamı üzerinden yapar: imajı hazırla, kurtarma ortamına yeniden başlat, BOOT'u SSH üzerinden onun `flash-boot.sh` betiğine yazdırıp doğrulat, yeniden başlat. Kurtarma ortamı kurulduğundan (2026-10-10) beri BOOT'u güncellemenin yolu; `restore-vendor-recovery.sh` üretici sistemini RECOVERY'ye geri koyar (henüz çalıştırılmadı) |

## Telefonla konuşmak

| Araç | Amaç |
| --- | --- |
| `usb-console.py` | USB üzerinden seri kabuk (`/dev/ttyACM0`); iki çekirdekte ve initramfs içinde çalışır |
| SSH | `ssh burak-alpine@<telefon adresi>`; MAC adresi sabit olduğu için mainline'da adres sabittir. Ana makine araçları adresi depo kökündeki `.phone-ip` dosyasından (tek satır, git yok sayar) ya da `J701F_PHONE_IP` değişkeninden okur |
| `i2c-peek.c` | Telefonda tek bir I²C yazmacını okuyan ya da yazan minik statik program |
| `reboot-recovery-static.c` | `RECOVERY` bölümüne yeniden başlat |
| `kmod/j701f_pdinfo.c` | Dört güç alanının durumunu yazdıran minik çekirdek modülü — yazmaç dökümü almanın güvenli alternatifi. `off=AD` / `on=AD` ile tek bir alanı açıp kapatır |
| `kmod/j701f_cam0_off.c` | Yüklüyken kullanılmayan kamera güç alanını kapalı tutar |

### Sağlık denetimi

`tools/phone-health.sh` çalışan telefona bağlanır ve bu projede en az bir kez sessizce bozulmuş her şey için birer satır yazar: hangi sistemin çalıştığı, çekirdek yapı kimliği, gerçekten kullanılan ekran sürücüsü, masaüstü, geride kalmış açılış koruma damgaları, frekans sınırları, modüller, pil (yüzdenin ölçülen gerilime göre inandırıcı olup olmadığı dahil), pil yardımcısı, pil sıcaklığı, saat ve donanım saati, SD kart, MTP, Wi-Fi, çekirdek günlüğündeki hatalar, bellek ve disk alanı. Telefonda hiçbir şeyi değiştirmez; satırlar `ok`, `WARN` ya da `FAIL` ile başlar ve bir şey başarısızsa çıkış durumu 1 olur. Her çalışma oturumunun ilk komutu olmaya uygundur.

### Paket güncellemeleri

`tools/phone-update.sh` hangi Alpine paketlerinin güncellemesi olduğunu gösterir ve hiçbir şeyi değiştirmez; `--apply` ile sıradan olanları yükseltir, "hassas" olanları - grafik yığını ve masaüstü (Mesa, KWin, Plasma, Qt, SDDM), ses ve kamera (PipeWire, libcamera), ve telefonun açılıp erişilebilir olması için gerekenler (musl, BusyBox, OpenRC, udev, D-Bus, NetworkManager, OpenSSH, aygıt yazılımları) - `--include-sensitive` verilene dek bekletir; böylece bunlar, sonrasında ekrana bakabilecek biri varken yükseltilir. Bir şeyi değiştirmeden önce kurulu sürümleri telefonda `~/j701f/updates/` altına kaydeder, sonrasında sağlık denetimini çalıştırır. Otomatik bir geri dönüş yoktur: Alpine'ın kararlı deposu eski sürümleri tutmaz; bu yüzden hassas paketler dahil edilecekse önce yedek alın.

### Uygulama profili

`system/apps/setup.sh` **Alpine çalışan telefonda** yürütülür. Varsayılan olarak günlük uygulama paketlerini yalnızca ön izler; `--apply` onları kurar, `--prune` ayrıca listelenen isteğe bağlı uygulamaları kaldırır, `--development` ise derleyici ve tanı araçlarını ekler. Sahibinin geliştirme araçları kurulu kalmıştır. Uygulama için aygıt ağacında `samsung,j7velte` uyumu gerekir. Ön izleme ve tekrar uygulama 2026-10-26'da çalışan telefonda denendi; ek paket değişikliği olmadı. Betik BOOT/RECOVERY derlemez ya da flashlamaz, DATA'yı taşımaz ve Wi-Fi'yi yapılandırmaz; herkese açık tam kurucu sonraki iştir. Kullanım için `system/apps/README.md` dosyasına bakın.
Ayrıca mobil Kirigami düzeniyle resim açarken yaşanan çökmeyi önlemek için `/usr/local/bin/koko` konumuna yalnız Koko'yu etkileyen bir sarmalayıcı kurar.

### Yedek

`tools/phone-backup.sh` - bkz. [Yedek ve telefonu yeniden kurma](userspace.md#yedek-ve-telefonu-yeniden-kurma).

## Ekranı uzaktan görmek ve ona dokunmak

| Araç | Amaç |
| --- | --- |
| `phone-screenshot.sh CIKTI.png` | Ekranı uyandır, oturumun kilidini aç, KWin üzerinden yakala, PNG'ye çevir |
| `kwin-screenshot.c`, `raw-to-png.py` | Betiğin kullandığı iki yarı |
| `inject-swipe.py AYGIT X0 Y0 X1 Y1` | Bir dokunmatik aygıta tek parmaklı kaydırma (başlangıç ve bitiş aynıysa dokunuş) yaz |
| `inject-key.py` | Bir girdi aygıtına tuş basışı yaz |

Ekran görüntüsünden ya da grafik sınamasından önce çıkışı uyandırın — karartılmış bir ekran her grafik ölçümünü anlamsız kılar. Ekran görüntüsü masaüstünün mantıksal boyutundadır; bu da ekran ölçeğine bağlıdır (%160'ta 450 × 800).

## Kanıt ve testler

| Araç | Amaç |
| --- | --- |
| `panfrost-render-probe.c` | GPU'da ekran dışı çiz ve her pikseli doğrula |
| `j701f-gpu-evidence.py`, `j701f-board-evidence.py` | Canlı telefondan alınan kayıtları doğrulayıcıların kullandığı JSON dosyalarına çevir |
| `scroll-benchmark.mjs`, `bench/scroll/` | Sabit yerel tarayıcı iş yükü ve süreli zamanlama kaydı; [yöntem ve sınırlar](scroll-benchmark.md) |
| `phone-perf-sample.py` | Sabitlenmiş SSH ile süreli CPU/frekans/bellek/sıcaklık kaydı; eşleşen telefon kilidi gerekir |
| `tests/` | Birim testleri: `python3 -m unittest discover -s tests -p "test_*.py"` |

## İlk aşamalardan kalanlar

`recovery.py`, `flash-system.py`, `build-system.py`, `alpine-ram-test.py`, `ondevice-terminal.c` ve diğer erken araçlar kurtarma ortamını ve ilk Alpine kurulumunu yaptı ([2. ve 3. bölümler](../journey/02-recovery-linux.md)). Telefonu sıfırdan yeniden kurmanın yolu hâlâ onlar.

## Kurtarma ortamı (geliştiriliyor)

RECOVERY bölümü için grafik arayüzlü bir kurtarma ortamı yapılıyor; kendi sayfası var: [Grafik arayüzlü kurtarma](recovery.md).

## Aynı anda çalışmak

| Araç | Amaç |
| --- | --- |
| `coord.sh` | Aynı anda çalışan iki yardımcı ya da kişi için kilitler (`phone`, `kbuild`), bir iş panosu ve bir mesaj kutusu; kurallar `docs/coordination/README.md` içinde |

## Ne nerede

| Yol | İçerik |
| --- | --- |
| `kernel/` | Aygıt ağaçları, yamalar, yapılandırma, initramfs betikleri, sabitlenmiş girdiler |
| `system/` | Alpine sistemine kurulan dosyalar |
| `tools/` | Yukarıdaki araçlar |
| `docs/` | Çalışma notları ve ayrıntılı günlük (`j701f-mainline.md`) |
| `wiki/` | Bu wiki |
| `build/` | Üretilen her şey: imajlar, günlükler, ölçümler, ekran görüntüleri. Kaynak değildir |

## Gerçek ekran GPU aktarım denemesi

`run-native-display-trial.py --prime-probe`, mevcut kilit/BOOT/watchdog korumaları
altında `native-display-prime.c` aracını ekler. GBM/libdrm başlıkları gerekir. GPU ve ekran GBM ayırıcıları ayrı denenir;
ilk yolun reddedilmesi tek başına IOMMU gerekliliğini kanıtlamaz.
`prime.log` GPU tamponunun Exynos'a aktarılmasını ve FB nesnesi oluşturulmasını
ayrı kaydeder; görünür scanout ve masaüstü FPS ölçülmez. Telefondaki deneme render-node aktarımını reddetti, ekran GBM FB nesnesini
kabul etti; GPU render hâlâ doğrulanmadı. Dosyalar
`~/j701f/display-runtime/LABEL` altında. [Ekran yöntemi](display.md).

Aynı seçenek artık `native-display-egl.c` (iki aygıtta renderer kimliği) ve
`native-display-dmabuf.c` (ekran DMA-BUF tamponuna Panfrost shader çizimi,
GPU/CPU piksel doğrulaması, ayrı Exynos FB oluşturma) araçlarını da ekler.
EGL/GLES2 ve Linux DMA-BUF başlıkları gerekir; derleme watchdog kurulmadan yapılır.
Günlükler `egl-render.log`, `egl-display.log` ve `shared-render.log` dosyalarıdır.
Alt sürece bu araçlarla 150 saniye ayrılır; her aracın daha kısa zaman aşımı var.
Bu iki araç kareyi ekrana vermez. `native-dsimpll2-01` telefonda geçti: iki EGL
context'i Panfrost/T830,4096 ortak tampon pikseli GL/CPU ile doğrulandı, Exynos FB
kabul edildi. Context kimliği, ortak tampona çizim ve FB oluşturma ayrı sonuçlardır;
hiçbiri tek başına günlük native masaüstü performansını kanıtlamaz.
`pll_initialization` ilk denemenin completion ve register durumunu ayrıca
denetler; sonradan başarılı olan tekrar ilk zaman aşımını gizlemez.
`panel_power_mode` ham yanıtı saklar (bu denemede0x1c); native kontrol yalnız
başarılı okumayı değil, temel güç bitleri2..6=0x1c olmasını ister. Önceki0x9c
ile bit7 farkı yorumlanmaz; fiziksel görünüm ayrı doğrulamadır.
