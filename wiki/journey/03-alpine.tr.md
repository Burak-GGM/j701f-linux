# 3. Telefonda Alpine

**Hedef:** hâlâ üretici çekirdeği üzerinde, paket yöneticisi olan, gerçekten kurulu bir Linux dağıtımı.

## Neden Alpine

[Alpine Linux](https://alpinelinux.org/) küçüktür (temel sistem yaklaşık 8 MB), KDE Plasma Mobile dahil güncel AArch64 paketleri vardır ve *musl* C kitaplığı ile BusyBox kullanır; bu da onu altındaki çekirdek konusunda az talepkâr yapar. Son nokta önemliydi: üretici çekirdeği 2014'ten kalma 3.18 sürümü ve modern dağıtımların çoğu bu kadar eski bir çekirdekte çalışmayı reddediyor.

## Önce RAM'de dene

Depolamaya herhangi bir şey yazmadan önce Alpine'in "minirootfs" arşivi, çalışan recovery'ye USB kabuğu üzerinden gönderildi, bir RAM dosya sistemine açıldı ve `chroot` ile içine girildi. `tools/alpine-ram-test.py` bunu, arşivin sağlama toplamını ve imzasını denetlemek dahil, otomatikleştirir. Deneme, Alpine programlarının başladığını, `apk`'nin (paket yöneticisi) çalıştığını ve eski çekirdeğin yeterli olduğunu gösterdi — tek bir bölüme dokunmadan. Yeniden başlatma her izi sildi.

## Nereye kurulacağını seçmek

Telefonun depolamasında boş yer yok, yani bir şeyden vazgeçmek gerekiyordu. Seçilen düzen:

| Bölüm | Boyut | Görev |
| --- | --- | --- |
| `BOOT` | 32 MiB | Çekirdek + küçük bir yükleyici initramfs |
| `RECOVERY` | 38 MiB | 2. bölümdeki kurtarma ortamı |
| `SYSTEM` | 3 GiB | Dokunulmadı |
| `USERDATA` | 11,1 GiB | Alpine kök dosya sistemi (Android verilerinin yerine) |

Bölüm tablosunun kendisi değiştirilmedi. Android kullanıcı verilerinden bilerek vazgeçildi.

## Yükleyici

`BOOT`'a, recovery'deki aynı sağlam çekirdek farklı bir initramfs ile kondu. Bu initramfs'in `/init`'inin tek işi var: `USERDATA`'yı bul, gerçekten bizim sistemimizi içerdiğini denetle, bağla ve `switch_root` ile denetimi ona devret. Bir şey yanlış görünürse tahmin yürütmek yerine durur — eksik ya da bozuk bir kök, asla yarı başlamış bir sisteme yol açmamalı.

## Bilinmeye değer bir yazma hatası

11 GB'lık kök dosya sistemini yazmanın ilk denemesi, Download Mode'da bağlantıyı kapatma aşamasında başarısız oldu. Genel Android *sparse* kodlaması, sağlanan Samsung yazılımından farklıydı: Samsung imajında daha büyük başlıklar vardı ve "fill" parçaları yoktu. Bu olası bir uyumluluk sorunuydu, ama tek neden olduğu kanıtlanmadı. Hata sonrasında `USERDATA`'nın içeriği belirsizdi.

`BOOT`'a henüz dokunulmamıştı, ama telefon güncelleme hatası gösteriyordu ve recovery tuş kombinasyonu yine o ekrana dönüyordu. Yalnızca doğrulanmış recovery arşivini yeniden yazmak terminali geri getirdi. O günden beri geçerli olan bir kural çıktı: **imajını göndermeden önce üreticinin kendi imajıyla karşılaştır.** İmaj yazıcı, Samsung'un yazılımındaki parça biçimine uyacak şekilde yeniden yazıldı. Sonraki salt okunur denetim, kurulu Alpine kökünü ve başlangıç dosyalarını doğruladı; ardından normal açılış başarılı oldu. Kullanıcı Android DATA'nın değiştirilmesini kabul etmişti ve DATA yedeği yoktu. Ayrıntılar `docs/system-flashing.md` içinde.

## Kullanılabilir bir sistem

Alpine kurulunca, bir Linux sisteminin sıradan araçları tek tek eklenebildi:

- bir kullanıcı hesabı ve `sudo`,
- üreticinin Broadcom sürücüsüyle **Wi-Fi** (yazılım dosyaları Samsung'un kendi yazılım paketinden alındı); telefon internete, dolayısıyla `apk add`'e kavuştu,
- bu Wi-Fi bağlantısı üzerinden **SSH**; geliştirme artık seri kabuğa bağımlı değildi,
- ilk grafik program: doğrudan çerçeve belleğine çizen bir Qt terminali.

Bu noktada telefon küçük bir Linux bilgisayardı. Ama 2014'te takılı kalmıştı: GPU hızlandırması yok (üreticinin GPU sürücüsü yalnızca Android'in grafik yığınıyla konuşur), Wayland masaüstü çalıştırmanın yolu yok ve kimsenin bakımını yapmadığı bir çekirdek. Bu bölümden sonraki her şey o çekirdeği değiştirmekle ilgili.

!!! info "Depodaki ayrıntılar"
    `docs/alpine-ram-trial.md`, `docs/internal-system-layout.md`, `docs/system-flashing.md`, `docs/ssh.md`, `docs/wifi.md` ve `docs/gui.md`.
