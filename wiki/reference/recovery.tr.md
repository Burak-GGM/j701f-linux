# Grafik arayüzlü kurtarma ortamı

!!! success "Durum: kuruldu (2026-10-10)"
    RECOVERY bölümünde bu kurtarma ortamı var. Yerini aldığı üretici 3.18 yedeği dosya olarak saklanıyor.

## Nedir

38 MiB'lik RECOVERY bölümü için, kendi kendine yeten küçük bir sistem; TWRP ya da OrangeFox gibi, ama bu Linux kurulumu için: projenin ana hat çekirdeği, birkaç megabaytlık bir initramfs ve arayüzü çizen, statik bağlanmış tek bir program. Kurulu sistemden hiçbir şeye ihtiyaç duymaz; o sistem açılmadığında da çalışır.

Telefon sahibinin kararları (2026-10-10): kendini kanıtladıktan sonra RECOVERY'deki üretici yedeğinin yerini alacak; Wi-Fi kullanabilmeli; arayüz İngilizce ve Türkçe, varsayılan İngilizce.

## Ekranlar

| Kutu | Ne yapar | Durum |
| --- | --- | --- |
| Sistemi başlat | kurulu Alpine'e devreder | çalışıyor (telefonda denendi) |
| Çekirdek | çalışan çekirdeği, BOOT bölümünü ve özetini, pili, belleği gösterir; bir imaj dosyasını geri okuyarak BOOT'a yazar, eskisini saklar, geri alır | telefonda dokunarak da çalışıyor: yazma ve geri alma ayrı ayrı doğrulandı |
| Dosyalar | kurtarma ortamında, (salt okunur bağlanan) kurulu sistemde ve SD kartta gezinir; dosyayı metin olarak gösterir; dosyayı SD karta kopyalar | telefonda dokunarak çalışıyor: gezinme, seçme, kopyalama |
| Terminal | ekran klavyeli bir kabuk | telefon ekranında çalışıyor |
| Yedekleme | `/etc` ile kullanıcı ayarlarını SD karta arşivler, son arşivi doğrular | telefonda çalışıyor (17 saniyede 28 MB) |
| Bakım | salt okunur dosya sistemi denetimi, çekirdek günlüğü ve çökme günlüğü, Wi-Fi ve SSH aç/kapat | telefonda çalışıyor |
| Güç | sisteme, kurtarmaya ya da indirme kipine yeniden başlatma; kapatma | sisteme yeniden başlatma telefonda çalışıyor; diğer üçü denenmedi |

Sağ üstteki düğme İngilizce ile Türkçe arasında geçiş yapar. `rec8`'den beri seçim yeniden başlatmadan sonra da kalır: kurtarma ortamı ayarlarını kendi bölümünün sonuna yakın 512 baytlık tek bir blokta tutar (`recovery/scripts/settings.sh`), çünkü yazılabilir bir dosya sistemi yoktur ve kurulu sisteme asla yazmaz.

Ekranda ne olursa olsun, USB seri kabuğu hep açıktır. `rec7`'den beri bilgisayar telefonu iki depolama alanlı bir MTP aygıtı ("SM-J701F Recovery") olarak da görür: kurulu sistemin ev klasörü salt okunur, SD kart okunur-yazılır.

## Yerleşik güvenlik kuralları

- Kurulu sistem **salt okunur ve günlüğü işlenmeden** (`ro,noload`) bağlanır; ondan önce bölümün kendisi blok aygıtı düzeyinde salt okunur yapılır. İkinci adım, çekirdek günlüğünde ext4'ün "salt okunur" bağlama sırasında sahipsiz bir inode sildiği görülünce eklendi: yazılabilir aygıtta bunu yapıyor. Kurtarma ortamı devretmeden önce bağlamayı kaldırır; kaldıramazsa, yarı paylaşılan bir bağlama üzerinde sistem başlatmak yerine yeniden başlatır.
- Yazma betiği yalnızca BOOT bölümüne yazar, başka hiçbir yere değil. PIT, önyükleyici, EFS, TrustZone, modem ve RPMB seçilemez.
- Yedekleme ve Dosyalar sayfalarının yazdığı tek yer SD karttır ve orada hiçbir şeyin üzerine yazılmaz.
- Yedeği geri yükleme yalnızca boş bir klasöre açar.
- Deneme güvenliği: 240 saniye boyunca kimse ekrana dokunmaz ve USB kabuğunu kullanmazsa, kurtarma ortamı kurulu sistemi kendiliğinden başlatır.
- Kurulu sistemi silebilecek işlevler bu telefonda çalıştırılmaz ve denenmez (sahibinin kuralı). Kodları bilgisayarda imaj dosyaları üzerinde sınanır (`tests/test_recovery_*.py`).

## Neresi nerede

| Yol | İçerik |
| --- | --- |
| `docs/recovery-design.md` | tasarım, beş adımlı yol, sahibinin kararları |
| `recovery/ui/main.c` | arayüz (LVGL 9.2, MIT lisansı) |
| `recovery/ui/gen-tr-font.py`, `font_tr.c` | LVGL'nin yerleşik yazı tipinde olmayan on iki Türkçe harf; aynı Montserrat dosyasından üretilir |
| `recovery/scripts/` | `sysinfo.sh`, `flash-boot.sh`, `backup.sh`, `storage.sh`, `wifi.sh`, `power.sh` — depolamaya dokunan her şey; sınanabilsin diye arayüzün dışında tutulur |
| `kernel/diagnostic/recovery-main` | initramfs `/init`'inin kurtarma kipi |
| `tests/test_recovery_flash.py`, `tests/test_recovery_backup.py` | geçici dosyalar üzerinde sınamalar |

## Derleme ve deneme

```bash
make -C recovery/ui
```

bilgisayar sürümünü derler; bu sürüm herhangi bir ekranı, görüntü aygıtı olmadan bir resme çizer:

```bash
J701F_RECOVERY_LANG=tr build/recovery-ui/host/recovery-ui --snapshot /tmp/home.ppm
```

Telefon sürümü telefonun kendisinde derlenir (`make TARGET=phone`, statik program) ve imaja şu komutla girer:

```bash
J701F_RECOVERY_UI=build/recovery-ui/phone/recovery-ui tools/build-mainline-image.sh AD kernel/dts/exynos7870-j7velte-fbmem.dts "--allow-audio --allow-sd --allow-mfc"
```

## İlk denemenin öğrettikleri

- Metin konsolu, arayüz ilk karesini çizdikten sonra da çerçeve belleğine yazmayı sürdürür; kurtarma ortamı önce onu çerçeve belleğinden ayırmalıdır.
- LVGL'nin kendi dokunma okuyucusu yalnızca olay kuyruğunu boşalttıktan sonra kalan durumu bildirir, bu yüzden kısa bir dokunuş kaybolabilir. Arayüz artık dokunmatik ekranı kendisi okuyor ve her basış ile bırakışta duruyor.
- Kurtarma ortamı devrettikten sonra kurulu sistemin USB kabuğu yanıt vermedi; güncelleme betiği bu durumda yeniden başlatmanın SSH üzerinden istenmesine ihtiyaç duyar.

## Wi-Fi ve SSH

Wi-Fi sürücüsü ve ürün yazılımı kurtarma ortamının parçasıdır. Bağlantıyı kuran programlar (`wpa_supplicant`, `udhcpc`, `sshd`), kayıtlı ağ ve SSH anahtarları ise **kurulu sistemden ödünç alınır**; sistem bunun için salt okunur bağlanır, `/run` ve `/tmp` dizinlerinin üzerine küçük RAM dosya sistemleri konur. Kurtarma ortamı bunu açıldıktan birkaç saniye sonra kendisi dener; Bakım sayfasından kapatılıp açılabilir.

Bu yüzden SSH ile giren kişi kurulu sistemin dosyalarını (salt okunur) görür, ama kurtarma ortamının çekirdeği üzerindedir. Kurulu sistemin dosyaları okunamıyorsa Wi-Fi de yoktur — onlara hiç bağlı olmayan yol USB kabuğudur.

## İkinci denemenin öğrettikleri

- Initramfs'teki `/run` 8 MiB'dir; geri alma için önceki 32 MiB'lik BOOT içeriğini saklamak kendi RAM dosya sistemini gerektirir. Yazıcı BOOT'a dokunmadan reddetti — istenen davranış bu, ama ileti vermeden yaptı.
- `wpa_cli` yanıt soketini `/tmp` içinde açar; salt okunur sistemde bu başarısız olur ve "hiç bağlanmadı" gibi görünür.
- SD kart ana hat çekirdeğinde `mmcblk2`, üretici çekirdeğinde `mmcblk1`'dir; betik artık her aygıta türünü soruyor.
- Alpine'de `e2fsck` statik bağlı değildir: imaj onu kitaplıkları ve C kitaplığının yükleyicisiyle birlikte `/recovery/lib` içinde taşır.

## Üçüncü denemenin gösterdikleri

- Wi-Fi ve SSH açılıştan sonra kendiliğinden geldi; yazma / geri alma / yeniden yazma dizisinin tamamı kablo gerekmeden SSH üzerinden yürütüldü.
- Yazma sırasında 32 MiB'lik bölümün bir an için iki kopyası bulunur (geri alma için saklanan ve yeni alınan), bu yüzden durum alanı 80 MiB'dir.
- Donanım tuşları çalışıyor: iki kez ses kısma ve güç tuşu Çekirdek sayfasını açtı. Home tuşu da seçer (bu kartta `KEY_LEFTMETA` bildiriyor; sahibi çalışmadığını bulunca `rec6`'da düzeltildi).
- SSH ile girenin kendi `/run` dizini vardır; kurtarma ortamının 240 saniye sonra sistemi başlatmasını önlemek için `/run/recovery-state/stay` dosyası oluşturulur.

## Kuruldu

2026-10-10'dan beri RECOVERY bölümünde bu kurtarma ortamı var (aynı akşamdan beri `rec8` imajı; yenisini `tools/install-recovery.sh` yazar). Kurtarma tuş kombinasyonuyla ya da sistemden `~/j701f/boot-swap/reboot-recovery.sh --execute` ile başlatılır; bu betik önce dosya sistemlerini temiz kapatır (yalın `reboot-recovery` yardımcısı bunu yapmaz). 240 saniye boyunca kimse ekrana dokunmaz, tuşa basmaz ve bekleme işaretini koymazsa kurulu sistemi başlatır.

Çekirdek güncellemeleri onun üzerinden yapılır: `tools/run-recovery-update.sh AD` imajı hazırlar, kurtarma ortamına yeniden başlatır, BOOT'u SSH üzerinden ona yazdırıp doğrulatır ve yeniden başlatır. Eski `tools/run-boot-update.sh` RECOVERY'de üretici sistemini gerektiriyordu; artık yeni araca yönlendirip duruyor.

Bölümde daha önce duran üreticinin 3.18 sistemi bütün olarak (38 MiB) telefonda ve bilgisayarda saklanıyor; `tools/restore-vendor-recovery.sh` onu geri yazar. Bu betik henüz çalıştırılmadı.

## Bir sürümü TWRP ya da OrangeFox'tan kurmak

!!! danger "Bu işlem telefonun verilerini siler ve telefonu açılamaz bırakabilir"
    ZIP **USERDATA'nın tamamını siler**: bütün Android uygulamaları, tüm uygulama verileri ve iç depolamanın tamamı (fotoğraflar, indirilenler, belgeler). Geri alınamaz; saklamak istediğiniz her şeyi önce bir bilgisayara kopyalayın.

    Kurulum başarısız olur ya da yarıda kesilirse (pil biter, SD kart çıkarılır, yazma sırasında bozuk bir yük fark edilir), USERDATA eksik kalır ve **telefon normal şekilde açılmaz** (yumuşak brick). Onarılabilir, ama yalnızca bir kurtarma ortamından (ZIP yeniden çalıştırılır) ya da hiçbir kurtarma ortamı açılmıyorsa Download Mode'dan Odin ile. Ancak ikisine de erişebiliyorsanız kullanın.

RECOVERY'de bu projenin kurtarma ortamı yerine hâlâ TWRP ya da OrangeFox bulunan bir telefon için `tools/build-recovery-zip.py`, bir sürümü USERDATA'ya yazan, kurtarmadan yüklenebilir bir ZIP üretir. ZIP **yalnızca USERDATA'ya yazar**: BOOT ve RECOVERY en fazla okunur; EFS, modem ve önyükleyici hiç açılmaz. Genel adımlar ve sürümün kendisi kurulum sayfasında anlatılır.

| | |
| --- | --- |
| Dosyalar | `recovery/installer/` (`update-binary`, `installer.sh`), `tools/build-recovery-zip.py`, testler `tests/test_recovery_zip.py` içinde |
| Sürüm | `userdata.ext4.gz`, `userdata.ext4.gz.sha256`, `userdata.ext4.sha256`, `release.json`; ya SD kartta ZIP'in yanındaki `j701f-release/` klasöründe ya da yük 4 GiB'tan küçükse ZIP'in içinde (`--embed`) |
| Telefondaki araçlar | ZIP, projenin sürümü sabitlenmiş statik AArch64 BusyBox 1.36.1'ini taşır; kurtarmanın kendi araçları kullanılmaz. Burada incelenen iki kurtarmada (OrangeFox R11.1, J7 Nxt için TWRP 3.x) 2017–2021 tarihli bir BusyBox var; TWRP'ninki 32 bittir ve `getevent` içermez |

Bir şey yazılmadan önce aşağıdakilerin hepsi sağlanmıyorsa ZIP kurulumu reddeder:

1. Çekirdek komut satırı bir `J701F` önyükleyicisi bildirir ve kurtarma `j7velte` için derlenmiştir.
2. `USERDATA` bölümü `mmcblk0p24`'tür ve tam 23314432 sektördür (11936989184 bayt); bu değerler telefonda denetlendi.
3. BOOT'ta projenin Linux yükleyicisi zaten vardır (U-Boot ortamı `bootcmd=j701f_ramboot` içerir; derlenmiş 86 BOOT imajının hepsinde ve telefonun BOOT bölümünde denetlendi). Bu yoksa Android verisini silmek, hiçbir şeyi başlatamayan bir telefon bırakır.
4. ZIP ve sürümün her dosyası, sembolik bağlantılar izlendikten sonra, blok aygıtı fiziksel bir SD kart olan bir dosya sistemindedir (`/sys/dev/block/MAJ:MIN/…/device/type` değeri `SD`). Gerisi reddedilir: iç depolama, onun bir bağlaması ya da emüle edilmiş görünümü, SD karttan ona giden bir bağlantı. USERDATA'nın bağlı olduğu yerler adla değil, `/proc/self/mountinfo` içindeki major:minor ile bulunur.
5. `release.json` bu bölümü tarif eder (sektör, bayt, dosya sistemi UUID'si, `j7velte`); sıkıştırılmış yük SHA-256 değeriyle eşleşir ve eksiksiz bir gzip akışıdır.
6. Ekranda USERDATA'nın tamamının (Android uygulamaları, veriler, iç depolama) kalıcı olarak silineceğine ve başarısız bir kurulumun telefonu normal açılamaz bırakabileceğine dair uyarıdan sonraki 60 saniye içinde **Ses Açma** tuşuna basılır. Ses Kısma ya da hiç tuşa basmamak iptal eder. Tuşlar doğrudan `/dev/input`'tan okunur; bu yüzden TWRP'de de çalışır.

Ardından USERDATA'nın tüm bağlantılarını kaldırır (kurtarmanın MTP'si bölümü tutuyorsa durur ve MTP'nin kapatılmasını ister), imajı yazar, bölümün **tamamını** geri okuyup SHA-256'sını karşılaştırır ve dosya sistemi UUID'sini denetler. Sonuç (`PASS` ya da `FAIL` ve günlük) sürümün yanındaki `install.status` dosyasına yazılır. Yazma yarıda kalırsa USERDATA eksik kalır; BOOT ve RECOVERY'ye dokunulmamıştır ve ZIP yeniden çalıştırılabilir.

Durum 2026-10-27: bilgisayarda, benzetilmiş bir telefona karşı aynı BusyBox ile `qemu-aarch64` altında denendi (16 durum; aralarında SD karttan iç depolamaya bağlantılı ZIP ya da yük ve SD kart olmayan depolama da var; ilk 12'si: yükün iki yeri, iptal ve zaman aşımı, başka model, eksik Linux yükleyicisi, yanlış bölüm boyutu, bozuk yük, başka bir sürüm, iç depolamadaki ZIP, geri okuma uyuşmazlığı). **Telefonda henüz çalıştırılmadı**; ilk gerçek kurulum panoda koordine ediliyor. Bu deneme için resmi OrangeFox R11.1 kullanılacak: projenin başladığı OrangeFox imajıyla bayt bayt aynıdır. j7velte için resmi bir TWRP yok. OrangeFox'un "Disable DM-Verity" ve "Disable Forced Encryption" seçenekleri yeniden başlatırken BOOT'u yamalar; kapalı kalmalıdır. Deneme adımları ve bu projenin kurtarma ortamına dönüş yolu `docs/recovery-zip-device-test.md` içindedir.
