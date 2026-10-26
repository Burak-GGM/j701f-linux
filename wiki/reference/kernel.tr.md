# Çekirdek, yamalar, aygıt ağacı

## Hangi çekirdekler

| Çekirdek | Nerede | Amaç |
| --- | --- | --- |
| **Linux 7.1.13** (`7.1.13-BURAK-PANFROST-01`) | `BOOT` | Günlük kullanılan sistem |
| Aynı Linux 7.1.13, kurtarma ortamının initramfs'iyle | `RECOVERY` | Projenin [grafik kurtarma ortamı](recovery.md): yedek ve yeni imajların yazıldığı yer (2026-10-10'dan beri) |
| Samsung 3.18.140 ("SIMPLE" özel ROM derlemesi) | dosya olarak saklı | 2026-10-10'a dek yedek olarak `RECOVERY`'deydi; bölümün tamamı saklandı ve geri yazılabilir |
| Linux 6.15 + exynos7870-mainline ağacı | kurulu değil | İlk mainline tabanı; derleme girdisi `panfrost-6.15` olarak saklı |

7.1.13 kaynağı, `kernel/inputs.json` içinde SHA-256 ile sabitlenmiş kernel.org arşividir. Yamalar üstüne aşağıdaki sırayla uygulanır.

## Topluluk yamaları (`kernel/patches/exynos7870-7.1/`)

[exynos7870-mainline](https://gitlab.com/exynos7870-mainline/linux) 7.1 dalından, henüz kernel.org'da olmayan altı yama:

| Yama | Konu |
| --- | --- |
| 01 | Exynos 7870 yapılandırma parçası |
| 02 | postmarketOS yapılandırma parçaları |
| 03, 04 | `samsung-dsim` ekran köprüsü düzeltmeleri |
| 05, 06 | `dw_mmc` DMA eşiği seçeneği ve Exynos değeri |

Yonga setinin ihtiyaç duyduğu geri kalan her şey — saat denetleyicileri, pin denetimi, S2MPU05 PMIC, USB, I²C, temel aygıt ağacı `exynos7870.dtsi` — 7.1'de zaten üst akımda.

## Yerel yamalar (`kernel/patches/linux-*.patch`)

Bunlar yalnızca bu projede var. Hiçbiri üst akıma gönderilmedi. İkisi, `btbcm` adresi ve video çözücünün ilk karesi, güncel mainline'a göre yeniden yazılıp `kernel/upstream/` altında gönderime hazırlandı (`checkpatch.pl` ile denetlendi, alıcılar `get_maintainer.pl` ile bulundu); göndermek, kendi `Signed-off-by` satırıyla sahibin adımıdır.

| Yama | Ne yapar | Neden |
| --- | --- | --- |
| `linux-mip4-vdd-supply` | Melfas dokunmatik için isteğe bağlı güç kaynağı ve 300 ms başlangıç gecikmesi | Yonga hazır olmadan sorgulanıyordu |
| `linux-mip4-z-resolution` | Eksik bir eksen çözünürlüğünü doldurur | Masaüstünün girdi kitaplığı aygıtı reddediyordu |
| `linux-mip4-empty-packet-debug` | Boş dokunma paketleri için ek tanılama | Yukarıdaki iki hatayı bulurken kullanıldı |
| `linux-tm2-touchkey-bitmap-events` | TC360 dokunmatik tuşları için bit eşlemi olay biçimi | Bu yonga tuş kodu göndermiyor |
| `linux-tmu-exynos7870-readonly` | Salt okunur sıcaklık sensörü sürücüsü | Bu yonga seti için mainline TMU desteği yok |
| `linux-cpufreq-exynos7870-j701f` | İki küme için CPU frekans ölçekleme | Mainline sürücüsü yok; gerilimler bu telefonda ölçüldü |
| `linux-g3d-exynos7870-scaling` | GPU PLL frekans tablosu ve PLL değişirken GPU'yu yedek saate alan sürücü | GPU 343 MHz'de sabitti |
| `linux-wdt-s3c2410-keep-on-shutdown` | Watchdog'u kapanış boyunca çalışır tutma seçeneği | Bir yeniden başlatma, watchdog çoktan durdurulmuşken takıldı |
| *(`kernel/patches/staged/` içinde, uygulanmıyor)* | Başvuru için saklanan deneyler: kazanç sağlamayan iki simpledrm değişikliği (önbellekli çerçeve belleği, yazılımsal gama tablosu) ve hâlâ incelenen ekran sürücüsü yamaları | Her dosyanın başlığı neden kullanılmadığını söyler |
| `linux-sysfb-j701f-fast-argb-copy` | Her karenin önyükleyici çerçeve belleğine daha hızlı dönüştürülüp kopyalanması | Bu kopya bütün masaüstünün kare hızını sınırlıyor ([ölçümler](performance.md#kare-hz-ekran-yolu)) |
| `linux-zz-simpledrm-j701f-software-backlight` | Düzeyi kareler kopyalanırken uygulanan `j701f-panel` arka ışık aygıtı; bağlayıcı DSI olarak bildirilir | Bileşikleyicinin fazladan geçişi olmadan parlaklık (kısıkken saniyede 20 → 49 kare). Addaki `zz`, dayandığı kopya yamasından sonra uygulanmasını sağlar |
| `linux-zzz-sysfb-j701f-neon-copy` | Kare kopyasının (düz ve karartılmış) NEON komutlarıyla yapılması | Karartılmış kareler düz olanlardan 10 ms pahalıydı: saniyede 41 → 51 kare |
| `linux-zzzz-mfc-keep-first-frame-all-codecs` | Video çözücü ilk veri paketini yalnız H.264'te değil her biçimde çözmek üzere saklar | HEVC, MPEG-2 ve VP8 ilk anahtar kareyi kaybediyordu: bir sonrakine kadar bozuk görüntü |
| `linux-wdt-s3c2410-keep-on-suspend` | Bekçi zamanlayıcısını uyku boyunca çalışır bırakma seçeneği | Kimsenin izlemediği uyku denemeleri için güvenlik ağı: bir kilitlenme sıfırlamayla biter |
| `linux-cpuidle-psci-exynos7870-default-off` | Bu SoC'ta CPU kapatma boşta durumunu kapalı olarak kaydeder | Durum bir deney; çekirdekler çalışma zamanında tek tek dahil edilir, böylece bir kilitlenme açılış döngüsüne dönüşemez |
| `linux-btbcm-43430a1-patched-default-addr` | Bluetooth yongasının yama yazılımı yüklendikten sonra bildirdiği adresi "yapılandırılmamış" olarak tanır | Onsuz aygıt ağacındaki sabit adres yok sayılıyordu |
| `linux-panfrost-shrinker-switch` | Çekirdeğin bellek baskısı altında GPU tamponlarını nasıl atacağını belirleyen çalışma zamanı ayarı (telefon kip 2'yi kullanır: paylaşılanlar asla atılmaz) | Tarayıcıdaki siyah alanlar; bkz. [başarım](performance.md) |
| `linux-mfc-exynos7870` | Video çözücü sürücüsünün v10 türüne saat adını verir, çözücünün önündeki bellek yönetim birimini geçirgen kipe alır ve çözücünün özel bir bellek bölgesi kullanmasını sağlar | Geçirgen kip olmadan çözücünün yazılımı hiç başlamıyor; bölge olmadan küçük videolar başarısız |
| `linux-power-j701f-s2mu005-charger` | Şarj durumu, kablo türüne göre akım sınırları, fener LED'leri (modül) | Masaüstü kablonun takılı olup olmadığını bilemiyordu; duvar şarjı bilgisayar girişinden hızlı şarj etmiyordu |
| `linux-audio-exynos7870-lpass` | Ses PLL'i kesirli PLL olarak düzeltildi; ses alt sistemi açılış sürücüsü | Ses için ilk adım |
| `linux-audio-j701f-codec-card` | COD3026X çalma kodeği, S1402X mikser kurulumu ve ses kartı | Üretici çekirdeğinden taşındı |

Ses sürücüleri Samsung'un GPL lisanslı 3.18 kaynaklarından türetildi. Başvuru dosyaları, depoları ve commit'leri `build/kernel/vendor-audio-reference/SOURCE.txt` içinde kayıtlı.

### Yerel sürücülerin sunduğu parametreler

| Dosya | Anlamı | Çekirdek varsayılanı |
| --- | --- | --- |
| `/sys/module/exynos7870_cpufreq/parameters/max_khz` | En yüksek CPU frekansı | 1352000 |
| `/sys/module/exynos7870_cpufreq/parameters/min_khz` | En düşük CPU frekansı | 546000 |
| `/sys/module/clk_exynos7870_g3d_park/parameters/max_khz` | En yüksek GPU frekansı | 343000 |

Varsayılanlar bilerek temkinli. Bir açılış betiği onları 1586000 ve 1001000'e yükseltir; bkz. [kullanıcı alanı](userspace.md).

## Yapılandırma

Çekirdek yapılandırması, üst akım `defconfig`'i artı iki topluluk parçası artı `kernel/configs/mainline-bringup.config`'tir; sonuncusu bu projenin eklediği her seçeneği açıklamalarıyla tutar. Dikkat çeken tercihler:

- Diğer tüm yonga ailesi seçenekleri (`ARCH_*`) kapalı; bu, çekirdek imajını 44 MB'tan yaklaşık 28 MB'a indirdi.
- Telefonun açılması ve görüntü vermesi için gereken sürücüler modül değil, gömülü.
- Samsung I²S ve yerel ses sürücüleri **bilerek modül** ve `/lib/modules` altına kurulmuyor; nedeni için [ses bölümüne](../journey/08-sound.md) bakın.

Çözümlenmiş yapılandırma `kernel/inputs.json` içinde özetle sabitlenmiştir. Parça değiştiğinde derleme durur ve yeni özetin bilerek kaydedilmesi gerekir.

## Aygıt ağacı

Kart tarifi katmanlar halinde kuruludur. Her dosya bir öncekini içerir ve bir kademe ekler; böylece portun tarihi dosya listesinden okunabilir:

| Dosya (`kernel/dts/exynos7870-j7velte-…`) | Ne ekler |
| --- | --- |
| `diagnostic.dts`, `pmic.dtsi` | Temel kart: bellek, PMIC regülatörleri, UART, USB |
| `logged.dts` | Simple framebuffer, ramoops |
| `usbdiag.dts` | USB anahtarını ayarlamak için kullanılan I²C veri yolu |
| `emmc.dts` | eMMC |
| `gpu.dts` | GPU ve saat denetleyicisi |
| `touch.dts` | Dokunmatik ekran |
| `wifi.dts` | Wi-Fi, Home tuşu, depolama takma adları |
| `periph.dts` | Pil ölçer, dokunmatik tuşlar |
| `thermal.dts` | Sıcaklık sensörü ve ısı bölgesi |
| `wdt.dts` | Watchdog |
| `cpufreq.dts` | CPU frekans sürücüsü, ısı eşikleri |
| `extra.dts` | Bluetooth, ivmeölçer (yerleşim matrisiyle) |
| `gpufreq.dts` | GPU çalışma noktaları, saat park düğümü |
| `gputhermal.dts` | Soğutma aygıtı olarak GPU |
| `audio.dts` | Ses saatleri, LPASS, DMA, I²S, kodek, ses kartı |
| `emmchs.dts` | eMMC High Speed / DDR52 |
| `phone1.dts` | Titreşim motoru, microSD yuvası, yakınlık sensörü |
| `mfc.dts` | Video çözücü saat denetleyicisi ve düğümü |
| `bt.dts` | Sabit Bluetooth adresi |
| `charger.dts` | Şarj durumu düğümü |
| `cpuidle.dts` | Tek bir CPU boşta durumu (çekirdek kapatma); kapalı olarak kaydedilir, aşağıya bakın |
| `suspend.dts` | Wi-Fi kartı uykuda gücünü korur |
| `fbmem.dts` | Çerçeve belleği düğümü ayrılmış bellek bölgesini adıyla gösterir; kare başına kopyayı hızlandırır ([neden](performance.md#kare-hz-ekran-yolu)) |
| **`camera.dts`** | İki kamera sensörü, I²C yolları üzerinde, beslemeleri, saatleri ve sıfırlama hatlarıyla ([Kamera](camera.md)) — **zincirin şu anki tepesi** |
| `emmchs200.dts` | Başarısız bir HS200 denemesi, kayıt olarak saklı; derlemelerde kullanılmıyor |

Bir doğrulayıcı (`tools/build-j701f-dtb.py`), ilgili `--allow-…` bayrağı verilmedikçe depolamayı, GPU'yu, Wi-Fi'yi ya da ses saatlerini açan bir aygıt ağacını reddeder; bellek ayırmalarını ve GPU kaynaklarını telefonda ölçülen değerlerle karşılaştırır.

## Derleme

```sh
# Yalnızca çekirdek
python3 tools/build-kernel.py panfrost --jobs 11

# Çekirdek + aygıt ağacı + initramfs + U-Boot + Android imajı, doğrulanmış
tools/build-mainline-image.sh AD kernel/dts/exynos7870-j7velte-camera.dts "--allow-audio --allow-sd --allow-mfc"
```

Derleyici LLVM/Clang. Kaynaklar `/tmp/j701f-kernel-build` altına açılır. Her yama bir kez uygulanır ve yamanın özetinden adını alan bir dosyayla işaretlenir; uygulanmış bir yamayı değiştirmek için dokunduğu dosyaları eski haline getirin, işaret dosyasını silin ve yeniden derleyin.

Ses modülleri aynı ortamla ve açık `.ko` hedefleriyle derlenir; derlenen modüller `build/kernel/audio-modules/` içinde tutulur.

## Bilgisayarda hazırlanan panel prototipi

`tools/kmod/ea8061s/`, ayrı derlenen deneysel bir EA8061S J7VE panel modülü
içeriyor. Kurulu çekirdek imajının ya da otomatik yükleme listesinin parçası
değil. Derleme ve bilgisayardaki komut/hata denetimleri geçti; panel görüntüsü,
DECON DMA ve simpledrm'den devralma henüz sınanmadı.
[Gerçek ekran sürücüsü](display.md) sayfasına bakın.

Yerel `linux-dsim-pll-wait-fix.patch`, alınan DSIM kodundaki PLL tamamlanma
sonucunu düzeltir, ilgili kesmeyi açar ve birleşik kesme olaylarını korur.
Bilgisayar testleri ve tam çekirdek derlemesi geçti. Kayıtlı `pfshrink3` BOOT
paketi bu düzeltmeyi, hata temizliği için `linux-dsim-init-errors.patch`
ve açıkça etkinleştirilen, varsayılan kapalı J701F zamanlama profili için
`linux-dsim-j701f-timing-trial.patch` içeriyor. Aygıt ağacında gerçek ekran
denetleyicileri kapalı kalıyor. Değişiklikler derlendi; donanımda doğrulanmadı.

## Uyku

**Boşta uyku çalışıyor** (`s2idle`; bu ürün yazılımının izin verdiği tek tür: PSCI sürümü 0.1 ve sistem uykusu çağrısı yok). Süreçler dondurulur, her sürücü aygıtını askıya alır, çekirdekler bir uyandırma kesmesine kadar boşta bekler ve her şey yaklaşık yarım saniyede geri gelir.

Telefonun başında kimse yokken nasıl ayağa kaldırıldı:

1. Çekirdeğe uyku sınama düzeneği eklendi (`CONFIG_PM_DEBUG`); bu düzenek bir uykuyu seçilen derinlikte durdurup beş saniye sonra geri dönebiliyor: önce `freezer`, sonra `devices`, sonra `platform`.
2. Yerel bir bekçi zamanlayıcısı seçeneği, zamanlayıcıyı uyku boyunca çalışır tutuyor; bir kilitlenme sıfırlamayla bitecekti. Hiç devreye girmedi.
3. Bir betik, uyandırma kaynağı olarak gerçek zaman saatini kurdu ve ağ geri gelmezse telefonu yeniden başlattı.

Düzeltilmesi gerekenler:

| Görülen | Neden | Çözüm |
| --- | --- | --- |
| Uyanınca Wi-Fi ölü, her SDIO erişimi zaman aşımına uğruyor | Kart uykuda gücünü yitiriyordu; MMC denetleyicisi "gücü koru"ya izin vermiyordu | Aygıt ağacında `keep-power-in-suspend` |
| Çekirdek uykuya girerken Wi-Fi ve Bluetooth ürün yazılımını istedi ve bulamadı | O dosyalar yalnızca initramfs içindeydi | Kök dosya sisteminde `/lib/firmware/brcm/` altında kopyaları |
| Uyurken saniyede iki kez kodek I2C hatası | Kulaklık algılama yoklaması çalışmayı sürdürüyordu | Artık dondurulabilir iş kuyruğunda çalışıyor |

Sınananlar: saat alarmıyla biten 6, 8 ve 60 saniyelik uykular, bütün yerel modüller yüklüyken; sonrasında masaüstü, Wi-Fi ve ekran görüntüsü çalıştı. Zararsız bir ileti kaldı (uyanışta `tm2-touchkey … failed to read i2c data`).

Tuşla uyandırma şu an ayarlı **değil**: güç ve ana ekran tuşlarını uyandırma kaynağı yapmak, yukarıdaki Wi-Fi ayarıyla birlikte, tarayıcının açılışını 1,1 saniye uzattı (sekiz imajda ölçüldü; ayarların her biri tek başına zararsız, nedeni anlaşılmadı). Bu yüzden uyuyan telefon yalnızca saat alarmıyla uyanıyor. Ölçülmeyen: uykunun ne kadar güç kazandırdığı — çekirdekler yalnızca boşta bekliyor, güçleri kesilmiyor (sonraki bölüme bakın).

Hiçbir şey telefonu kendiliğinden uyutmuyor. Bu şimdilik bilinçli: Wi-Fi de tuşlar da telefonu uyandırmıyor; bu yüzden önce mutlaka saat alarmını kurun. Elle denemek için:

```sh
# 30 saniye uyu, sonra saatle uyan
echo +30 | sudo tee /sys/class/rtc/rtc0/wakealarm
echo freeze | sudo tee /sys/power/state
```

## CPU boşta durumu: kapalı tutulan bir deney

Bir çekirdeğin yapacak işi kalmadığında yalnızca saati durur (WFI); yukarı akış bu SoC için daha derin bir durum tanımlamıyor. Üretici çekirdeği boştaki çekirdeklerin gücünü kesiyor; sistem uykusunun ihtiyaç duyduğu ilk şey de bu olduğu için denendi:

- Aygıt ağacı tek bir durum tanımlar: PSCI `CPU_SUSPEND` ürün yazılımı çağrısıyla çekirdek kapatma; parametre üreticinin aygıt ağacından alındı.
- Üretici çekirdeği bu çağrıdan hemen önce çekirdeğin güç yönetimi yazmacındaki bir alanı da sıfırlıyor. Bu yapılmazsa telefon saniyeler içinde kilitleniyor. Küçük bir modül, `tools/kmod/j701f_cpupd.c`, aynısını yapıyor.
- Modülle birlikte 1–7. çekirdekler birkaç dakika boyunca on binlerce kez bu duruma sorunsuz girdi. **0. çekirdeği dahil etmek telefonu** 20–80 saniye sonra **kilitliyor** (beş denemenin dördünde). Bütün aygıt kesmelerini 0. çekirdek alıyor; olası bağlantı bu, daha fazla incelenmedi.
- Ölçülebilir bir kazanç görülmedi: USB gücündeyken telefonun sunduğu tek ölçü SoC sıcaklığı ve o da gürültünün ötesinde kıpırdamadı.

Bu yüzden durum **kapalı** olarak kaydediliyor ve hiçbir şey onu açmıyor. Denemek için (kilitlenirse bekçi zamanlayıcısı telefonu yeniden başlatır):

```sh
sudo insmod ~/j701f-cpuidle/j701f_cpupd.ko
for c in 1 2 3 4 5 6 7; do echo 0 | sudo tee /sys/devices/system/cpu/cpu$c/cpuidle/state1/disable; done
```

Tek başına bir çekirdek bu duruma hiç girmez: çekirdek, ötekileri uyandırmak için uyanık bir çekirdeğe ihtiyaç duyar ve tek aday her zaman odur.

### Ekran tanılama kerneli

`linux-dsim-z-j701f-pll-diagnostics.patch`, yalnız J701F ekran denemesi açıkken
PLL kesme maskesi, bağlantı kilidi ve reset tamamlanmasını kaydeder. Register
programlamasını değiştirmez; zaman aşımı yine hata sayılır. `dsimdiag2` paketi
tam BOOT geri okumasıyla kuruldu; çalışan GNU build ID ve Plasma/simpledrm
doğrulandı. Yeni gerçek ekran/watchdog denemesi geçti; günlük yol simpledrm. [Ekran notları](display.md).

`linux-dsim-zz-j701f-inherited-pll.patch`, açık miras PLL'yi yalnız J701F deneme
modunda reset öncesinde durdurur. İzole `dsimpll2` artık kurulu: tüm BOOT geri
okuması `a2b11f5a…`, çalışan build ID `1950147e…` ve Plasma/simpledrm eşleşti.
Yeni watchdog reseti/aynı imaja dönüş ve `native-dsimpll2-01` native ilk başlatma
doğrulaması geçti: ilk denemede completion, PLL zaman aşımı yok, native kontroller/
120 flip ve aynı BOOT/Plasma'ya otomatik dönüş. Önceki tanılama DTB/initramfs
baytları aynen korundu. Beş gerçek init regresyon testi geçti; bu tek süreli
donanım A/B denemesidir, uzun kararlılık veya günlük native masaüstü testi değil.
