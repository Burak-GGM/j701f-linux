# Telefonu kullanmak

Telefonu elinde tutan kişi için kısa bir kılavuz. Buradaki her şey başvuru sayfalarında daha ayrıntılı anlatılıyor; bu sayfa yalnızca ne yapılacağını söyler.

## Açılış ve açılmadığında

| Ne | Nasıl |
| --- | --- |
| Olağan açılış | Güç tuşu. Masaüstü, çekirdek başladıktan yaklaşık yarım dakika sonra görünür |
| Kurtarma ortamı | Açarken **Güç + Home + Ses Açma** tuşlarını basılı tutun. Çekirdek imajı yazma ya da geri alma, dosyalar, yedek, terminal kutucukları. Dört dakika dokunulmazsa olağan sistemi başlatır |
| Bir güncellemeden sonra ekran siyah kalıyor ya da bozuk görünüyor | Telefon açılırken **Ses Kısma**'yı basılı tutun: telefon, önyükleyicinin kurduğu basit ekran yolunda kalır |
| Çalışan sistemden kurtarma ortamına | Bir terminalde `~/j701f/boot-swap/reboot-recovery.sh --execute` |

Kurtarma ortamında ses tuşları gezdirir, Güç ya da Home seçer; sağ üstteki düğme İngilizce ile Türkçe arasında geçer.

## Dosyalar

- **Bilgisayardan:** USB kablosunu takın. Telefon, iki depolamayla "SM-J701F Linux" olarak görünür: ev klasörü ("J701F") ve SD kart ("SD-card").
- **SD kart:** açılışta yuvadaysa `/media/sdcard` altına bağlanır; dosya yöneticisinde Yerler altındadır.
- Kamera uygulamasının çektiği **fotoğraflar** ev klasöründeki `Pictures` içindedir.

## Pil ve şarj

- Yüzdeyi küçük bir yardımcı doğru tutar. Hizmet olarak kurulana dek telefonun her açılışından sonra bir kez başlatılması gerekir; `sudo sh ~/j701f/battery/install.sh` onu kalıcı olarak kurar.
- **Duvar şarjı**, yardımcı çalışırken bilgisayar girişinden hızlı şarj eder (0,45 A'e karşı 1,5 A'e kadar); yardımcı yokken 1 A. Bu, yazıldı ve benzetilmiş bir sistemle sınandı, ama henüz gerçek bir duvar şarjıyla denenmedi.
- **Şarj sınırı:** telefon hep kabloda duruyorsa pili %75-80 arasında tutmak için, içinde `charge_limit=80` satırı olan bir `/etc/j701f-battery.conf` dosyası oluşturun. Yeniden tam şarj için dosyayı silin.
- **Şarjı şimdi durdur:** `echo inhibit-charge | sudo tee /sys/class/power_supply/s2mu005-charger/charge_behaviour`; `inhibit-charge` yerine `auto` sürdürür. Telefonu yeniden başlatmak da sürdürür.

## Işık, kamera, tarayıcı

- **Fener:** hızlı ayarlardaki (üst paneli aşağı çekin) fener kutucuğu arka ışığı tam güçte açar ve kapatır. Başka güçler ya da ön ışık için: `echo 3 > /sys/class/leds/white:flash/brightness` (arka, 0-6), `echo 1 > /sys/class/leds/white:front-flash/brightness` (ön, 0-2); `0` kapatır.
- **Kamera:** Plasma Camera önizleme gösterir, fotoğraf çeker ve iki kamera arasında geçer. Video kaydı henüz çalışmıyor, otomatik odak da yok.
- **Tarayıcı:** Angelfish'i kullanın. Grafik yongasıyla çizer; Firefox çalışır ama yazılımla çizer ve daha yavaştır.
- **Video dosyaları:** `mpv`, donanımsal video çözücüsünü kullanacak şekilde ayarlıdır.

## Bakım

| İş | Nerede |
| --- | --- |
| Ayarların SD karta yedeği | Kurtarma ortamı → Yedek, ya da bilgisayardan `tools/phone-backup.sh` (geri yüklemenin provasını da yapar) |
| Her şey yolunda mı? | Bilgisayardan `tools/phone-health.sh`: denetim başına bir satır |
| Paket güncellemeleri | Bilgisayardan `tools/phone-update.sh` (önce gösterir; kurmak için `--apply`) |
| Yeni bir çekirdek imajı | Bilgisayardan `tools/run-recovery-update.sh AD`, ya da kurtarma ortamındaki Çekirdek kutucuğu |

## Yapamadıkları

Arama, SMS ve mobil veri yok (modem sürülmüyor). GPS yok. Otomatik uyku yok: ekran kapanır, telefon uyanık kalır. Otomatik parlaklık yok (telefonda ışık sensörü yok). Kulaklık, ahize ve Bluetooth sesi doğrulanmadı.
