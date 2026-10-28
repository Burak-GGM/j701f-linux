# Kullanıcı alanı

## Kurulu sistem

| | |
| --- | --- |
| Dağıtım | Alpine Linux 3.24 (`main` ve `community` depoları) |
| Kök dosya sistemi | `USERDATA` (`mmcblk0p24`) üzerinde ext4, yaklaşık 10,9 GB, UUID ile bağlanır |
| Kullanıcı | `burak-alpine`, `sudo` yetkili |
| Init | PID 1 olarak küçük bir betik; mainline çekirdekte OpenRC'yi başlatır |
| Oturum | elogind, D-Bus, PipeWire + WirePlumber, otomatik girişli SDDM |
| Masaüstü | KDE Plasma Mobile 6.6, Wayland üzerinde KWin, oturum yöneticisi için Xwayland |
| Grafik | Panfrost'lu Mesa 26.1; görüntü çıkışı için yerel ekran sürücüsü (`exynos-drm`), yedek olarak önyükleyicinin çerçeve belleği (`simpledrm`) |
| Ağ | Ana hat çekirdeğinde Wi-Fi NetworkManager üzerinden (böylece Plasma onu görür ve yönetir), yönlendiriciden sabit adresle; `sshd`. Üretici çekirdeği hâlâ özgün `wpa_supplicant` betiğini kullanır |

## Bu projenin telefona kurduğu dosyalar

Kaynakları depoda `system/` içindedir.

| Telefonda | Kaynak | Görev |
| --- | --- | --- |
| `/sbin/j701f-start` | `start` | PID 1. RAM dosya sistemlerini bağlar, `/tmp`'yi 256 MB'a büyütür, sonra `/etc/inittab`'ı izler |
| `/etc/inittab` | `inittab` | Aşağıdaki parçaları başlatır |
| `/sbin/j701f-openrc` | `openrc-runlevel` | Bir OpenRC çalışma düzeyini süre sınırıyla çalıştırır — yalnızca OpenRC kuruluysa |
| `/sbin/j701f-display` | `display-select` | Masaüstü (mainline) ile çerçeve belleği terminali (üretici çekirdeği) arasında seçim yapar |
| `/sbin/j701f-netguard` | `netguard` | Açılıştan 300 sn sonra Wi-Fi adresi yoksa → kurtarma ortamına yeniden başlat. 2026-10-26'dan beri kapalı (`/etc/j701f-netguard-off`) |
| `/etc/local.d/j701f-gpufreq.start` | `gpufreq-limit` | Açılıştan 40 sn sonra: GPU sınırı 1001 MHz, CPU sınırı 1586 MHz; damga dosyasıyla korumalı |
| `/etc/local.d/j701f-audio.start` | `audio-autoload` | Ses modüllerini, video çözücü modüllerini ve `~/j701f-misc-modules/` içindeki modülleri (şarj durumu) yükler; damga dosyasıyla korumalı |
| `/etc/udev/rules.d/60-j701f-video.rules` | `video-udev.rules` | Video çözücü aygıt düğümlerini `video` grubuna verir |
| `~/j701f-mfc-modules/load.sh` | `mfc-load` | Video çözücü modüllerini sırayla yükler |
| `/etc/local.d/j701f-stamps.stop` | `stamps-stop` | Düzenli kapanışta damga dosyalarını temizler |
| `~/j701f-audio-modules/load.sh` | `audio-load` | Altı ses modülünü sırayla yükler |
| `/etc/elogind/logind.conf.d/…`, `/etc/elogind/sleep.conf.d/10-j701f-nosleep.conf` | `elogind-powerkey.conf`, `elogind-nosleep.conf` | Güç tuşu Plasma'ya bırakılır; uyku kapalıdır. Uykuyu kapatan dosya yalnızca `sleep.conf.d` içinde etkilidir: `logind.conf.d` içinde yok sayılır ve telefon 15 dakika boşta kalınca, onu uyandıracak bir tuş olmadan askıya girer |
| `/etc/sddm.conf.d/…` | `sddm-autologin.conf` | `plasma-mobile` oturumuna otomatik giriş |
| `/etc/profile.d/…` | `session-profile.sh` | Oturum ortamı |
| `~/j701f-boot-swap/` | — | `reboot-recovery` ve özgün `BOOT` imajının yedeği |
| `/etc/fstab` (tek satır) | — | SD kartı (`/dev/mmcblk2p1`, FAT) telefon kullanıcısına ait olarak `/media/sdcard` altına bağlar; `nofail` olduğundan kart yoksa açılış beklemez |
| `~/j701f/boot-swap/reboot-recovery.sh` | `reboot-recovery.sh` | Dosya sistemlerini temiz bırakarak kurtarma ortamına geçiş: damga dosyalarını siler, masaüstünü durdurur, salt okunur bağlar, sonra `reboot-recovery`'yi çağırır |
| `~/j701f/battery/j701f-battery` | `battery/` | Pil yardımcısı: gösterge kipi değişimi ve sıcaklığa göre şarj akımı (aşağıya bakın); şimdilik elle çalıştırılıyor |
| `~/j701f/modules/misc/j701f_adc.ko` | `tools/kmod/j701f_adc.c` | Pil ve kart sıcaklığı (hwmon aygıtı `j701f_adc`); o klasördeki öteki modüllerle birlikte yüklenir |
| `/etc/localtime`, `/etc/timezone` | `build-release.py --timezone` | Saat dilimi; sürüm oluşturucu, başka bir şey söylenmedikçe derlemeyi yapan bilgisayarın dilimini kullanır. Bu dosya olmadan telefon UTC gösterir (hem eski sistemde hem ilk sürümde eksikti) |
| `/usr/local/bin/j701f-flashlight`, "Fener" uygulaması; `/usr/local/bin/j701f-front-flash` | `flashlight/` | Arka ve ön flaş LED'i için iki düğme (Plasma'nın fener düğmesi yalnızca arkadakini yakar); uygulama kapanınca ikisi de söner. `j701f-front-flash [on\|off\|toggle]` öndekini terminalden yakar |
| `~/.config/kglobalshortcutsrc` | `release/kglobalshortcutsrc` | Son uygulamalar dokunmatik tuşunu (`KEY_PROG1`, Qt'de "Launch (1)") Plasma Mobile'ın görev değiştiricisine bağlar; Plasma bu tuşa varsayılan olarak hiçbir şey bağlamaz. Bir sonraki oturum açılışında etkinleşir |
| (kurulmuyor) | `session/backkey/` | `j701f-backkey`: geri dokunmatik tuşu yarım saniye basılı tutulunca açık uygulamayı kapatır (Plasma'nın geri tuşu yalnızca uygulama içinde bir sayfa geri gider). Denendi, ama henüz kendiliğinden başlamıyor: yeni bir oturum otomatik başlatması sahibin onayını bekliyor. Elle: oturumda `/yol/j701f-backkey &` |

## Grafik

KWin, Panfrost ile çizer ve kareleri kopyalamadan yerel ekran sürücüsü `exynos-drm` üzerinden sunar (telefon önyükleyicinin çerçeve belleğine geri düşmüşse kopyalayarak `simpledrm` üzerinden; hangisi olduğunu `tools/phone-health.sh` söyler). Çizen sürücüyü denetlemek için:

```sh
# masaüstü kullanıcısı olarak, oturum ortamının içinde
qdbus org.kde.KWin /KWin supportInformation | grep -i renderer
```

**Firefox** artık günlük kullanım paketleri arasında değil. Burada GPU'yu kullanamıyordu: Mesa'nın bu GPU ailesi için derleyicisi WebRender gölgelendiricilerinde hatalı kod üretiyor, sayfanın bölümleri eksik kalıyor ve GPU iş hataları oluşuyordu. Firefox kurulu olduğunda sistem genelindeki tercih dosyası yazılımsal çizimi zorunlu kılıyordu.

Plasma Mobile'ın kendi tarayıcısı **Angelfish** (Chromium motoru) sayfaları GPU'da hatasız çiziyor ve tercih edilecek tarayıcıdır. Angelfish içinde video çalışıyor: telefonun sahibi görüntü ve sesle bir YouTube videosu izledi (2026-10-10) ve iki küçük kusur bildirdi: ara sıra saniyenin bir bölümü kadar ses kesilmesi ve seyrek, kısa bir titreme; ikisi de incelenmedi.

Sahibinin günlük uygulama grubu 2026-10-26'da küçültüldü. Angelfish, Dolphin, Koko, Plasma Camera, terminaller, saat, hesap makinesi, GNOME Software, VLC ve mpv kaldı. Firefox, Pure Maps, Discover, Gwenview, Elisa, AudioTube, PlasmaTube, Kasts, KWeather, Wike ve GNOME Chess ile gereksiz kalan bağımlılıkları kaldırıldı. Deneysel ağ araç kutusu `~/j701f/old/` altına taşındı, yalnızca onun kullandığı paketler kaldırıldı. Bu işlem kullanıcının fotoğraflarını ya da tarayıcı verilerini silmedi. Tekrarlanabilir paket listeleri ve `setup.sh` için `system/apps/` dizinine bakın; betik varsayılan olarak yalnızca ön izleme yapar, temizleme için ayrıca seçenek gerekir.

**Koko'da fotoğraf açma.** Koko 26.04.2 bu telefonda mobil Kirigami düzeniyle herhangi bir resmi açarken çöküyordu. Yapay bir PNG ile hata yeniden üretildi; hata ayıklayıcı izinde çökme Kirigami yerleşim kodundaydı. Koko `QT_QUICK_CONTROLS_MOBILE=false` ile başlatılınca aynı resim açıldı, ekranda göründü ve uygulama çalışmaya devam etti. `system/apps/koko-wrapper`, `/usr/local/bin/koko` olarak kurulu; yalnız Koko bu düzeni kullanıyor, Plasma Mobile mobil kalıyor. Sahibi 2026-10-26'da galeri içinden gerçek bir fotoğrafın açıldığını ve Koko'nun açık kaldığını doğruladı.

**GNOME Software'da kaydırma.** Sahibi uygulama listesinde yavaş kaydırma bildirdi. Telefonda tekrarlanan on saniyelik kaydırma denemesi, güvenilir `GSK_GPU_DISABLE=all` ayarıyla etkin sürede yaklaşık 10 ekran değişimi/saniye ölçtü. GTK GPU seçenekleri tek tek ayrıldığında yalnız `gradients` açıkken ana görünümün yaklaşık %19'u, yalnız `occlusion` açıkken yaklaşık %99'u karardı; diğer seçenekler görünümü korudu. Yalnız bu ikisini kapatmak (`GSK_GPU_DISABLE=gradients,occlusion`) kaydırmadan sonra içeriği görünür tuttu, fakat yaklaşık 12 değişim/saniye ve daha yüksek işlemci yükü ölçüldü. Güvenilir `all` ayarı geri yüklendi. Ölçüm yalnız bu görünüm ve denemeyle sınırlıdır; mağazadaki kaydırma performansı henüz çözülmedi.

**Temel uygulama açılışı.** 2026-10-26'da sessiz, önbelleği temizlenmiş/sıcak başlatma denemesi, pencerenin ilk görünme süresini değil işlemin işlemci bakımından sakinleşme süresini ölçtü: Dolphin 4,5/3,0 sn (soğuk/sıcak), Koko 7,0/5,3 sn, Kalk 8,5/7,0 sn, QMLKonsole 7,0/5,3 sn ve Plasma Ayarlar 6,5/4,8 sn. Koko ile Kalk bu denemede yaklaşık 110-120 MiB oransal bellek kullandı. Bu, uygulama açılışını sonraki iyileştirme konusu olarak gösterir; her uygulamanın tüm ekranlarının görsel olarak denetlendiği anlamına gelmez.

**VLC** varsayılan video uygulamasıdır. Qt 5 arayüzü Xwayland üzerinden çalışır. Videoyu yazılımla çözer. Bir günlüğüne donanımsal çözücüyü kullanacak şekilde ayarlanmıştı (`~/.config/vlc/vlcrc` içinde `avcodec-codec=h264_v4l2m2m`) ve ölçümler çok iyi görünüyordu - bir çekirdeğin üçte biri, geciken kare yok - çünkü VLC hiçbir şey göstermiyordu: o çözücüyle VLC 3 tek bir resim alıyor, "buffer deadlock prevented" bildiriyor ve ses çalarken pencereyi siyah bırakıyor. Telefon sahibi fark etti; ayar 2026-10-10'da kaldırıldı. Çıkan ders [dersler sayfasında](lessons.md): düşük işlemci yükü, görüntü var demek değildir. Donanımsal çözücüyü kullanan oynatıcı `mpv`'dir.

## Donanımsal video çözme

Samsung video çözücüsü (MFC), modülleri yüklendikten sonra bir V4L2 çözücüsü olarak kullanılabilir:

```sh
sudo sh ~/j701f-mfc-modules/load.sh      # /dev/video0 çözücü, /dev/video1 kodlayıcı
sudo ffmpeg -c:v h264_v4l2m2m -i ~/Videos/test720.mp4 -an -f null -
```

Samsung'un çözücü yazılımına `/lib/firmware/s5p-mfc-v10.fw` olarak ihtiyaç duyar; bu dosya telefonun kendi Samsung yazılım paketinden gelir ve yeniden dağıtılmamalıdır. Modüller açılışta, ses sürücüleriyle aynı korumalı betik tarafından yüklenir ve `video` grubunun üyeleri aygıt düğümlerini kullanabilir. 360p'den 1080p'ye H.264 doğru çözülüyor. **mpv** kurulu ve çözücüyü varsayılan olarak kullanıyor (`/etc/mpv/mpv.conf`: `hwdec=v4l2m2m-copy`); hâlâ varsayılan video uygulaması olan VLC ve tarayıcılar yazılımla çözüyor.

## Ses

Ses kartı `J701F`'dir; bir çalma ve bir kayıt aygıtı (ana mikrofon) vardır. PipeWire onu "Built-in Audio Stereo" olarak sunar.

| Denetim | Anlamı |
| --- | --- |
| `Speaker Volume` | Hoparlör yükselticisi kazancı, 0–8 (−6 dB ile +2 dB). Daha yüksek değerler bozulma yaptığı için yonganın en yükseğinin altında sınırlı |
| `SPK SPK On` | Hoparlöre yönlendirme (varsayılan olarak açık) |
| `HP HP On`, `Headphone Volume` | Kulaklık yolu — yazıldı, denenmedi |
| `EP EP On`, `Earphone Volume` | Ahize yolu — yazıldı, denenmedi |
| `DAC Gain` | Sayısal kazanç |
| `Headset Jack` (salt okunur) | Kulaklık takılı mı; ayrıca `J701F Headset Jack` adlı bir girdi aygıtı |
| `MIC1 Volume`, `MIC1 Boost Volume`, `ADC Gain` | Ana mikrofonun kazanç kademeleri |
| `MIC1 MIC1 On`, `MIC2 MIC2 On`, `MIC3 MIC3 On` | Hangi mikrofon girişinin kaydedileceği (varsayılan: MIC1). MIC2 ve MIC3'ün (kulaklık) çalıştığı doğrulanmadı |

Donanım yolu yalnızca 48 kHz, 16 bit stereo kabul eder; gerisini PipeWire dönüştürür.

Sürücüleri elle yüklemek ya da yeniden yüklemek:

```sh
sudo sh ~/j701f-audio-modules/load.sh
```

## Proje dosyaları telefonda nerede durur

Projenin ev dizinine koyduğu her şey `~/j701f/` altındadır: `boot-swap/` (öteki bölüme yeniden başlatan yardımcı, saklanan üretici imajı), `boot-update/AD/` (kurulmakta olan imaj), `modules/audio`, `modules/mfc`, `modules/misc` (açılışta yüklenen çekirdek modülleri), `experiments/`, `recovery-build/`, `display-runtime/` ve `old/` (ilk aşamalardan kalanlar). Kullanıcının kendi klasörlerinin yanına başka hiçbir şey açılmaz ve önceki güncellemelerin bekleyen imajları silinir.

## Wi-Fi, döndürme ve öteki masaüstü hizmetleri

- **Masaüstünde Wi-Fi.** `/sbin/j701f-wifi` eskiden `wpa_supplicant` ile bir DHCP istemcisini kendisi çalıştırıyordu; bu işliyor ama Plasma'yı Wi-Fi yok sanır hâlde bırakıyordu. Ana hat çekirdeğinde, `/etc/j701f-wifi-nm` dosyası varsa betik bunun yerine NetworkManager'ı başlatır; kayıtlı ağ `/etc/NetworkManager/system-connections/j701f-home.nmconnection` dosyasındadır ve `/etc/NetworkManager/conf.d/j701f.conf` sabit MAC adresini korur. NetworkManager 90 saniye içinde adres alamazsa betik onu durdurur ve o açılış için eski yola döner. `/etc/j701f-wifi-nm` silinirse kalıcı olarak eski yola dönülür.
- **Ekran döndürme.** `iio-sensor-proxy` (varsayılan çalışma düzeyinde) ivmeölçeri okur; `qt6-qtsensors` KWin'in onu kullanmasını sağlar; çıkışın döndürme ilkesi "her zaman". Paket ilk kurulduğunda sensörün tanınması için `udevadm trigger` gerekti. `/etc/udev/rules.d/81-j701f-accel.rules` (kaynağı `system/accel-udev.rules`) hizmetin sensörü yoklayarak okumasını sağlar: veri-hazır kesmesi birkaç yüz örnekten sonra duruyor ve okumalar donuyordu. Sensörün aygıt ağacındaki yönü (mount matrix) ayna görüntüsüydü, bu yüzden ekran ters dönüyordu; doğrusu telefon sahibinin denemesiyle bulundu ve `accel1` imajından beri aygıt ağacının kendisinde.
- **Titreşim.** Plasma Mobile titreşimi (tuş basışları, bildirimler) feedbackd adlı bir hizmetten ister. Bu hizmet kurulu değildi; kabuk "feedbackd vibration failed" diye günlüğe yazıyor ve sürücüsü çoktandır yüklü olan motor, masaüstü tarafından hiç kullanılmıyordu. 2026-10-13'te kuruldu (`feedbackd`, `feedbackd-device-themes`); udev kuralı bu motorun sürücü adını tanıyor ve oturum açmış kullanıcıya erişim veriyor. Profili `quiet` olarak ayarlandı (`gsettings set org.sigxcpu.feedbackd profile quiet`): yalnızca titreşim. Varsayılan `full` profilinde aynı olaylar ses de ister; burada ses Plasma'nın işidir. Telefona kimse dokunmadan denetlendi: 150 ms'lik bir geri bildirim olayı motorun beslemesini açıp yeniden kapattı; hızlı ayarlardaki bir kutucuğa enjekte edilen iki dokunuş da - yani Plasma'nın kendi dokunma geri bildirimi - aynısını yaptı ve oturum günlüğüne yeni hata satırı düşmedi. Hissedilip hissedilmediğini telefonun sahibi söyleyecek.
- **Uygulama mağazası.** `apk` eklentili GNOME Yazılımlar kurulu tek grafik mağazadır. Uygulamaları, simge ve açıklamalarıyla, Alpine'in `/var/lib/swcatalog` içindeki AppStream kataloğundan gösterir (`alpine-appstream-downloader` indirir, ayar betiği haftada bir yeniler; dizin herkesçe okunabilir olmalı). GTK 4 uygulamaları bu GPU'da `GSK_RENDERER=gl` ile birlikte `GSK_GPU_DISABLE=all` ister; oturum için `~/.config/plasma-workspace/env/j701f-gtk.sh` içinde ayarlıdır: GTK'nin varsayılan iyileştirmeleriyle pencerenin bazı bölümleri siyah kalır, yazılımsal çizici (`cairo`) ise doğru çizer ama rahat kullanılamayacak kadar yavaştır.
- **polkit** kurulu ve çalışıyor. Plasma'nın ayrıcalıklı işlemler için kullandığı yardımcılar (arka ışık dahil) onsuz çalışmaz.
- **Müzik.** Elisa günlük kullanım profilinden çıkarıldı. Sahibinin müzik dosyalarına dokunulmadı; istenirse paket deposundan yeniden bir müzik çalar eklenebilir.

## Bellek

1,2 GB'lık sıkıştırılmış bir takas aygıtı (zram), birkaç çekirdek ayarıyla birlikte her açılışta `/etc/local.d/j701f-tune.start` tarafından kurulur; `earlyoom` hizmeti de masaüstü donmadan önce en büyük web işleyicisini sonlandırır. Tarayıcı motoru, `~/.config/plasma-workspace/env/j701f-webengine.sh` içindeki düşük bellek anahtarlarıyla başlatılır. Arka planda beş dakika kalan uygulamalar durdurulur ve etkinleştirilince devam eder (`j701f-freezer`, ayarları `~/.config/j701f-freezer.conf` içinde). Her ayarın ne yaptığı ve ne kazandırdığı [başarım sayfasında](performance.md).

## Bilinen pürüzler

- Masaüstü oturumunu temiz biçimde yeniden başlatmak, kullanıcının tüm oturum süreçlerini durdurmayı gerektirir; yalnızca KWin'i ya da SDDM'yi yeniden başlatmak yarı başlamış bir oturum bırakır.
- Üretici çekirdeği artık `RECOVERY`'de değil; masaüstü ile metin terminali arasında çekirdeğe göre seçim yapan betikler hâlâ kurulu ve artık hep masaüstünü seçiyor.

## Yönetici kim

Polkit ("Authentication required" penceresini gösteren hizmet) `wheel` grubunun üyelerini yönetici sayar, yoksa root'un parolasını ister. Telefonun kullanıcısı `wheel` grubunda değil; bu yüzden yazılım mağazası onun kendi, doğru parolasını reddediyordu. `/etc/polkit-1/rules.d/49-j701f.rules` (depoda `system/polkit/49-j701f.rules`) kullanıcıyı yönetici olarak tanımlar ve telefonun başındayken GNOME Yazılımlar üzerinden parolasız paket kurmasına, kaldırmasına ve güncellemesine izin verir - zaten parolasız `sudo` yetkisi var.

## USB üzerinden dosyalar (MTP)

Bir bilgisayara takıldığında telefon, seri kabuğun yanında ev klasörünü bir MTP aygıtı ("SM-J701F Linux") olarak sunar. Initramfs'in hâlâ kurduğu USB ağ işlevi - Wi-Fi çalışmadan önceki giriş yolu; takıldığı her bilgisayarda yeni bir kablolu bağlantı gösteriyordu - 2026-10-13'ten beri aynı başlatma betiği tarafından aygıttan çıkarılıyor (`touch /etc/j701f-usb-net` onu korur). Arkasındaki program uMTP-Responder'dır; Alpine paketlemediği için telefonda derlendi. Depodaki `system/usb-mtp/`, yapılandırmasını ve açılışta USB aygıtına MTP işlevini ekleyen betiği içerir. Bilgisayardan kopyalanan dosyalar telefonun kullanıcısına ait olur. Ev klasörünün tamamı, gizli klasörler dahil, görünür. Açılışta yuvada bir SD kart varsa ikinci depolama olarak, "SD-card" adıyla görünür (`/media/sdcard` altına bağlıdır; başlatma betiği onu çalışan MTP sunucusuna ekler, böylece kart yokken boş bir depolama gösterilmez).

## Pil yüzdesi, sıcaklık ve şarj

**Yüzde.** S2MU005 içindeki pil ölçer, giren ve çıkan yükü sayar ("akım kipi") ve zamanla kayar; 2026-10-13'te, şarj devresinin kendisinin dolu bildirdiği (4,35 V, şarj akımı azalırken) bir pilde %43 gösteriyordu. Üretici çekirdeği bunu, pil doluya ve boşa yakınken yongayı "gerilim kipine" alarak düzeltir; çünkü orada hücre gerilimi daha güvenilir tanıktır. Ana hat sürücü ise yongayı yalnızca okur. Pil yardımcısı `system/battery/j701f-battery`, üreticinin kip değişimini kullanıcı alanından, üreticinin koşullarıyla yapar: gerektiğinde tek bir yazmaca yazar (0x4A: 0x10 akım, 0xFF gerilim). Yonga gerilim kipindeyken gösterilen değer yarım saati biraz aşan bir sürede %43'ten %91'e, gerçek değere doğru yükseldi. Yonga, bırakıldığı kipi yeniden başlatmada korur.

**Sıcaklık.** `j701f_adc.ko`, pil paketinin termistörünü ve kart üzerindeki bir termistörü SoC'nin ADC'si üzerinden okur ve `j701f_adc` adlı bir hwmon aygıtı olarak gösterir (`temp1` pil, `temp2` kart); dönüşüm fabrika aygıt ağacındaki tablolarla yapılır. Ana hat aygıt ağacı bu ADC'yi tanımlamıyor ve çekirdeğin kendi Exynos ADC sürücüsü onunla çalışmıyor (dönüştürmeleri zaman aşımına uğruyor; üreticinin türü farklı başlatılıyor ve sonucu başka yerde tutuyor); bu yüzden modül küçük bir aygıt ağacı eklentisini ve kendi yoklamalı sürücüsünü birlikte getirir. `BOOT`'a dokunulmaz.

**Şarj hızı.** Şarj sürücüsü, kablo türü her değiştiğinde giriş sınırını ve şarj akımını türe göre ayarlar: bilgisayar girişi 500/450 mA, şarj girişi 1000/1000 mA, duvar şarjı 1200/1000 mA. İkisi de `/sys/class/power_supply/s2mu005-charger/` altında okunup yazılabilir (`input_current_limit`, `constant_charge_current`, µA cinsinden; üst sınır 1550 ve 1500 mA); yazılan değer kablo türü değişene dek geçerlidir. `dcp_input_ma`, `dcp_charge_ma` ve `auto_limits` modül parametreleri kuralı değiştirir. Bunun üstüne pil yardımcısı sıcaklığı kullanır: duvar şarjı takılıyken ve pil 15 ile 41 °C arasındayken sınırları 1550/1500 mA'e yükseltir (üretici 2150 mA'e kadar şarj eder); 15 °C'nin altında 700 mA'e, 5 °C'nin altında ya da 41 °C'nin üstünde 450 mA'e izin verir; 50 °C'nin üstünde ya da 0 °C'nin altında ise pil 45 °C'nin altına ya da 5 °C'nin üstüne dönene dek şarjı kapatır. Sıcaklık okunamıyorsa hiçbir şeyi değiştirmez.

**Şarjı elle durdurma.** Aynı klasördeki `charge_behaviour` dosyası `inhibit-charge` ve `auto` değerlerini alır. Durdurulduğunda telefon kablodan çalışır ve pil dinlenir (ölçülen: pil akımı yaklaşık 120 mA'den 1 mA'e düşer, durum "Not charging"); `auto` şarjı sürdürür. Önyükleyici her açılışta şarjı yeniden açar.

**Şarj sınırı.** İçinde `charge_limit=80` satırı (50 ile 99 arası herhangi bir değer) bulunan bir `/etc/j701f-battery.conf` dosyası, yardımcının şarjı o yüzdede durdurmasını ve beş puan altında yeniden başlatmasını sağlar; arada telefon kablodan çalışır. Dosya yoksa sınır da yoktur. Telefonda geçici bir dosyayla denendi: %100'de yardımcı şarjı bir turda kapattı ("Not charging", pil akımı sıfıra yakın).

**Durum.** Yardımcı `i2c-tools` ister. Telefonda `~/j701f/battery/` içinde, bir OpenRC hizmet dosyasıyla birlikte duruyor, ama **henüz açılış hizmeti olarak kurulmadı**; o zamana dek yalnızca açılıştan sonra elle başlatılırsa çalışır (`sudo sh ~/j701f/battery/j701f-battery &`). Telefonda `sudo sh ~/j701f/battery/install.sh` hizmeti kurar. Kararları `tests/test_battery_daemon.py` ile benzetilmiş bir sistem üzerinde sınanıyor; duvar şarjı yolu gerçek bir duvar şarjıyla denenmedi.

**Saat.** Çekirdek açılışta sistem saatini donanım saatinden kurar, ama donanım saatini yazan hiçbir şey yoktu; bu yüzden her açılış, Wi-Fi saati getirene dek 2000 yılında başlıyordu. Wi-Fi başlatma betiği artık her başarılı saat alımından sonra donanım saatini yazıyor.

## Yedek ve telefonu yeniden kurma

`tools/phone-backup.sh`, çalışan sistemden, bu telefonu düz bir Alpine kurulumu değil de J701F portu yapan şeyleri arşivler: `/etc` (kurulu paketlerin listesi `/etc/apk/world` dahil), `/sbin` ve `/usr/local` (projenin açılış betikleri ve MTP sunucusu), kullanıcının `.config` ve `.local/share` klasörleri, ve `~/j701f` içinden çekirdek modülleri, pil yardımcısı ve kurtarma ortamına geçiş yardımcıları. Arşiv SD karta (`j701f-backups/`), kurtarma ortamının Yedek sayfasının yaptıklarının yanına yazılır; ikisi de aynı betiği (`recovery/scripts/backup.sh`) kullanır ve birbirinin arşivlerini okuyabilir. İçinde gizli bilgiler vardır (Wi-Fi anahtarı, parola özetleri, SSH ana makine anahtarları); bu yüzden kartta kalır ve asla depoya kopyalanmaz.

Araç, arşivi yaptıktan sonra **geri yüklemenin provasını yapar**: arşivi telefonda boş bir klasöre açar ve her dosyayı canlı olanla karşılaştırır (içerik, tür, sahip ve izinler), sonra klasörü siler. 2026-10-13'te: 35 MB, 1693 girdi, 1369 dosya birebir aynı, farklı olan yok. Çalışan sistemin üzerine hiçbir zaman bir şey açılmaz.

Kaybedilmiş bir sistemi geri koymak elle yapılan bir iştir ve baştan sona provası yapılmamıştır, çünkü bu, bu telefonu silmek demek olurdu:

1. Alpine'ı kurun ve projenin `BOOT` imajıyla açın (imajlar bilgisayarda `build/kernel/` altındadır; kurtarma ortamı birini yazabilir).
2. Arşivi boş bir klasöre açın (`backup.sh restore`), sonra `etc/apk/world` dosyasını yerine kopyalayın ve `apk`'nin oradaki paketleri kurmasını sağlayın.
3. Arşivin kalanını yeni sistemin üzerine kopyalayın.
4. `~/j701f/modules` içindeki çekirdek modülleri yalnızca derlendikleri çekirdekte yüklenir: `BOOT`'ta başka bir çekirdek varsa onları yeniden derleyin (bkz. [Derleme ve kurulum](tools.md)).

## Fener

Arka ve ön LED iki sıradan LED aygıtıdır: `/sys/class/leds/white:flash` (arka, parlaklık 0-6, adım başına 25 mA) ve `/sys/class/leds/white:front-flash` (ön, 0-2). Bir sayı yazmak ışığı açar, 0 kapatır; masaüstü kullanıcısı yazabilir. LED'leri şarj yongası sürdüğü için kod projenin şarj sürücüsünde durur. Akımlar üreticinin izin verdiğinin epey altında tutuldu. Telefon sahibi 2026-10-10'da doğruladı: iki LED de yanıyor ve arkadaki altı kademenin her birinde daha parlak oluyor. Plasma'nın hızlı ayarlardaki fener kutucuğu onunla çalışıyor (2026-10-13'te enjekte dokunuşlarla ve yonganın etkinleştirme yazmacıyla denetlendi: kutucuk arka LED'i en yüksek kademe olan 6'ya, 150 mA'e getiriyor ve yeniden kapatıyor). Kutucuk, adı `:flash` ya da `:torch` ile biten bir LED arar; bu yüzden yalnızca arkadaki bulunur ve yazmayı kendi küçük yetkili yardımcısıyla yapar.
