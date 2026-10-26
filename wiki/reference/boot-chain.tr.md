# Açılış zinciri ve güvenlik ağları

## Güç düğmesinden masaüstüne

```text
S-BOOT (Samsung, dokunulmadı)
  └─ BOOT'taki Android açılış imajını yükler
       └─ "çekirdek" = yamalı U-Boot v2026.01, içine gömülü bir FIT imajıyla
            └─ FIT: gzip ile sıkıştırılmış Linux Image + aygıt ağacı + initramfs
                 └─ Linux 7.1.13
                      └─ initramfs /init
                           ├─ USB anahtarını (MUIC) I²C üzerinden ayarlar
                           ├─ USB gadget'ı başlatır (seri + ağ)
                           └─ alpine-handoff: USERDATA'yı UUID ile bul, e2fsck ile denetle, bağla, switch_root
                                └─ /sbin/j701f-start (PID 1)
                                     └─ OpenRC → elogind, D-Bus, sshd, Wi-Fi, SDDM
                                          └─ Plasma Mobile (KWin, Wayland)
```

Gözden kaçması kolay birkaç ayrıntı:

- Android imajında **boş bir ramdisk** ve **yer tutucu bir aygıt ağacı tablosu** var. S-BOOT ikisinin de bulunmasında ısrar eder; hiçbiri kullanılmaz.
- **Çekirdek komut satırı U-Boot'un içinde ayarlanır** (`kernel/diagnostic/j701f-embedded-ramboot.c`). Aygıt ağacı kaynağındaki `bootargs`, çekirdeğin aldığı şey değildir.
- Komut satırı `clk_ignore_unused` ve `regulator_ignore_unused` seçeneklerini korur. Ekran yalnızca önyükleyicinin saatleri ve beslemeleri çalışır bırakıldığı için çalışıyor; bu iki seçenek olmasa çekirdek onları kapatırdı.

## İki bölüm

| Bölüm | Nasıl başlar | İçerik |
| --- | --- | --- |
| `BOOT` | Normal açılış | Güncel mainline imajı |
| `RECOVERY` | Power + Home + Ses Açma | 2026-10-10'dan beri: projenin [grafik arayüzlü kurtarma ortamı](recovery.md) (kendi çekirdeği ve initramfs'i). Öncesinde: aynı Alpine kökünü başlatan üretici 3.18 çekirdeği |

Kurtarma ortamı ayrı, küçük bir sistemdir; kurulu sisteme devredebilir ("Sistemi başlat" ile ya da 240 saniye kimse kullanmazsa kendiliğinden).

Telefona dokunmadan aralarında geçmek:

| Nereden | Nereye | Nasıl |
| --- | --- | --- |
| Sistem | Kurtarma | `sudo ~/j701f/boot-swap/reboot-recovery --execute` |
| Kurtarma | Sistem | Ekranda "Sistemi başlat" ya da Güç → "Sisteme yeniden başlat"; USB kabuğunda `reboot -f` |

## Yeni bir çekirdek imajı kurmak

Yeni imajlar her zaman **kurtarma ortamından** yazılır, çalışan sistemden asla:

1. `tools/build-mainline-image.sh AD kernel/dts/KART.dts` imajı derler, doğrular ve bir güncelleme dizini hazırlar.
2. `tools/run-recovery-update.sh AD` imajı telefona kopyalar, telefonu kurtarma ortamına yeniden başlatır, sabitlenmiş SSH anahtarıyla Wi-Fi üzerinden oraya girer, imajı kurtarma ortamının `flash-boot.sh` betiğine yazdırır ve yeniden başlatır. (2026-10-10'a kadar bu iş üretici sistemi üzerinden `tools/run-boot-update.sh` ile yapılıyordu.)

Kurtarma ortamı yazmadan önce imajın özetini denetler, `BOOT`'un önceki içeriğini geri alma için RAM'de saklar ve yazdığını geri okur. `build/kernel/boot-slot.json` hangi imajın kurulu olduğunu, `build/kernel/recovery-slot.json` `RECOVERY`'de ne olduğunu kaydeder.

## Güvenlik ağları

| Ağ | Neyi yakalar | Ne olur |
| --- | --- | --- |
| Watchdog, 30 sn, açılışta kurulu | Takılma | Yonga seti sıfırlanır |
| initramfs yedeği, 90 sn | Kök dosya sistemi bağlanamıyor | Kurtarma ortamına yeniden başlat |
| `j701f-netguard`, 300 sn | Mainline açık ama Wi-Fi adresi yok | Kurtarma ortamına yeniden başlat (o da Wi-Fi'yi kendisi dener ve sistemi yeniden başlatmadan önce 240 sn bekler). **2026-10-26'dan beri kapalı** (`/etc/j701f-netguard-off`): bilinen Wi-Fi'den uzakta gündelik kullanımda telefonu her yeniden başlatmadan sonra kurtarma ortamına gönderiyordu. Gözetimsiz çekirdek denemeleri için o dosyayı silerek yeniden kurun |
| "Bekliyor" damgaları | CPU/GPU sınırlarını yükselttikten ya da ses sürücülerini yükledikten kısa süre sonra sıfırlanma | Sonraki açılışlarda o adım, damga dosyası silinene kadar atlanır |
| `RECOVERY`'deki grafik kurtarma ortamı | Hiç açılmayan bir çekirdek | Power + Home + Ses Açma basılı tutulur; oradan başka bir imaj yazılır ya da geri alınır. Üretici 3.18 bölümü dosya olarak saklanır (`tools/restore-vendor-recovery.sh`) |
| Özgün `BOOT`'un Odin arşivi | İki bölüm de kullanılamaz | Download Mode ve kablo |

!!! warning "Yeniden başlatma sırasında takılma"
    Watchdog sürücüsü, sistem kapanırken watchdog'u kapatır. Çekirdek bundan sonra, asıl yeniden başlatmadan önce takılırsa telefonu hiçbir şey sıfırlamaz: bu bir kez, bir çekirdek hatası bir kilidi tutulu bıraktıktan sonra yaşandı. Kurtarma zorla yeniden başlatmadır — Ses Kısma + Power tuşlarını yaklaşık on saniye basılı tutun. Yerel bir yama (`s3c2410_wdt.keep_on_shutdown=1`) watchdog'u kapanış boyunca çalışır tutar; kuruldu ve sıradan bir yeniden başlatma hâlâ normal tamamlanıyor. Kapatma ve bilerek tetiklenen bir takılma sınanmadı.

!!! warning "Ağların yakalamadığı"
    **Açılışın erken aşamasında, her seferinde** çöken bir çekirdek sonsuza dek yeniden başlar: watchdog onu sıfırlar ve kullanıcı alanı bir şey yapamadan yine çöker. O döngüyü yalnızca tuş kombinasyonunu basılı tutan bir insan bitirir. Bu bir kez, ses çalışması sırasında yaşandı. Yanıt bir ağ daha değil, bir alışkanlık: riskli olan her şey modül olarak derlenir ya da varsayılan olarak kapalı bırakılır ve açılıştan sonra kullanıcı alanından açılır.

### Damga dosyaları

`/etc/local.d/j701f-gpufreq.start` ve `/etc/local.d/j701f-audio.start`, riskli adımlarından önce `/var/lib/` içinde birer dosya oluşturur ve birkaç dakika sonra siler. Telefon arada sıfırlanırsa dosya bir sonraki açılışta hâlâ oradadır ve adım atlanır. `/etc/local.d/j701f-stamps.stop` düzenli kapanışta dosyaları kaldırır; böylece sıradan bir yeniden başlatma çökme sanılmaz.

Atlanan bir adımı yeniden etkinleştirmek için:

```sh
sudo rm /var/lib/j701f-gpufreq.pending /var/lib/j701f-audio.pending
```

### Açılışta dosya sistemi denetimi

Kök dosya sistemi bağlanmadan önce initramfs üzerinde `e2fsck` çalıştırır. Kendi kopyası yoktur: kurulu olanı, gereken kitaplıklarıyla birlikte, kök salt okunur bağlıyken ondan ödünç alır. Kip, kurulu sistemdeki bir dosyayla seçilir:

| `/etc/j701f-fsck-mode` | Ne çalışır |
| --- | --- |
| yok | `e2fsck -p` — yalnızca güvenli, otomatik onarımlar |
| `-fn` | Zorlanmış, salt okunur rapor; hiçbir şey değişmez |
| `-fy` | Zorlanmış tam onarım |

Sonuç çekirdek günlüğünde (`j701f: e2fsck … exit status N`) ve `/run/j701f-fsck.log` dosyasındadır. Tek seferlik bir `-fn` ya da `-fy` çalıştırmasından sonra kip dosyasını silin.

## Asla yazılmayanlar

PIT, BL / sboot, EFS, TrustZone, modem ve RPMB. Wi-Fi MAC adresi normalde EFS'ten gelir; EFS hiç okunmak zorunda kalmasın diye aygıt ağacında sabit, yerel yönetimli bir adres kullanılır.
