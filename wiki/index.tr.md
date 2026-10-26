# Samsung Galaxy J7 Neo (SM-J701F) üzerinde Linux

Bu wiki, 2017 model bir Samsung telefona gerçek bir Linux sistemi kurmanın hikâyesini anlatıyor ve sonucu, başka birinin — meraklı bir okurun ya da projede çalışacak bir sonraki kişinin — ne yapıldığını ve neden yapıldığını izleyebileceği kadar ayrıntılı belgeliyor.

Telefon bir **Samsung SM-J701F** (kod adı `j7velte`): sekiz Cortex-A53 çekirdekli Exynos 7870 yonga seti, Mali-T830 GPU, 2 GB RAM ve 720×1280 AMOLED ekran. Android ve Samsung'un 3.18 çekirdeğiyle satıldı. Bugün **Linux 7.1.13** ile açılıyor, **Alpine Linux 3.24** çalıştırıyor ve dokunmatik, Wi-Fi ve sesi çalışan, GPU hızlandırmalı bir **KDE Plasma Mobile** masaüstü gösteriyor.

## Şu anki durum

| Alan | Durum |
| --- | --- |
| Çekirdek | Linux 7.1.13, topluluğun Exynos 7870 yamaları ve bir dizi yerel sürücüyle |
| Ekran | Yerel panel sürücüsü (saniyede 59,6 kare, parlaklık, karartma); önyükleyicinin çerçeve belleği yedek yol |
| GPU | Panfrost, 343–1001 MHz arası frekans ölçeklemeyle |
| CPU | Sekiz çekirdeğin hepsi, 546–1586 MHz arası frekans ölçeklemeyle |
| Dokunmatik, Wi-Fi, USB (seri, ağ, MTP ile dosyalar), eMMC, SD kart | Çalışıyor |
| Ses | Hoparlörden çalma ve ana mikrofon çalışıyor; kulaklık algılama ve arama yok |
| Pil göstergesi, şarj, sıcaklık, watchdog | Çalışıyor; pil yüzdesi, henüz açılışta başlatılmayan bir yardımcı betik istiyor |
| Döndürme, fener, donanımsal video çözme | Çalışıyor |
| Kurtarma | Projenin kendi grafik kurtarma ortamı: çekirdek güncelleme ve geri alma, yedek, USB üzerinden dosyalar |
| Uyku | Boşta uyku elle başlatıldığında çalışıyor; henüz otomatik değil |
| Kamera | İki kameradan önizleme ve fotoğraf; video kaydı ve otomatik odak yok |
| Modem | Çalışmıyor, şimdilik planda yok |

Tablonun tamamı [donanım ve durum](reference/hardware.md) sayfasında.

## Sırada ne var

İlk planın çoğu tamamlandı: gerçek ekran sürücüsü, daha hızlı depolama, donanımsal video çözme, Bluetooth, parlaklık, titreşim, fener, döndürme, bir kurtarma ortamı ve ilk kamera. Hâlâ açık olanlar, günlük kullanımdaki önemine göre kabaca şu sırada:

1. **Masaüstünün hızı:** uygulamalar yavaş açılıyor, görev değiştirici akıcı değil.
2. **Kamera:** video kaydı, otomatik odak, tam çözünürlük, renkler.
3. **Güç:** tuşla uyanan otomatik uyku, pil sıcaklığı (duvar şarjının tam akımla kullanılabilmesi için), pil yardımcısının açılış hizmeti olması.
4. **Ses:** kulaklık ve ahizenin kulakla doğrulanması, ara sıra yarım saniyelik kesintiler.

Modem ve FM radyo şimdilik planda yok.

## Bu wiki nasıl okunur

**[Yolculuk](journey/01-starting-point.md)**, hikâyenin sırayla ve öğretici biçimde anlatıldığı bölümdür. Mümkün olan en küçük adımla — telefona kendi yazdığımız tek bir satırı yazdırmakla — başlar; şimdilik masaüstüne, sese, doğruyu söyleyen bir pil göstergesine, projenin kendi kurtarma ortamına, ilk kameraya ve gerçek ekran sürücüsüne kadar gelir. Her bölüm hedefin ne olduğunu, neyin engel çıkardığını ve nasıl çözüldüğünü anlatır. Böyle bir portun *nasıl* yapıldığını anlamak istiyorsanız burayı okuyun.

**[Başvuru](reference/hardware.md)** bölümü belgelemedir: hangi çekirdek ve yamalar kullanılıyor, açılış zinciri nasıl işliyor, telefondaki her betik ne yapıyor, yeni bir imaj nasıl derlenip kurulur ve tekrarlanmaması gereken hatalar nelerdir. Bir bilgiye ihtiyacınız varsa burayı okuyun.

## Kim yaptı

Proje, telefonun sahibi olan ve her fiziksel adımı — tuş kombinasyonları, kablolar, Odin ile yazma, sesi dinleme — kendisi yapan Burak'a ait. Kodu ve araştırmanın çoğunu, onunla sırayla çalışan yapay zekâ kod yardımcıları yazdı: önce ChatGPT Codex, sonra Claude. Depoda alışılmadık ölçüde ayrıntılı notlar tutulmasının nedeni de bu: her yardımcı, diğerinin bıraktığı yerden devam edebilmeliydi. Bu wiki o notların okunabilir halidir.

!!! warning "Bu bir deney, ürün değil"
    Buradaki her şey tek bir telefonda yapıldı. Bu depodan derlenen imajları başka bir cihaza, hatta başka bir J7 modeline yazmak cihazı açılmaz hale getirebilir. Bu projedeki hiçbir şey önyükleyiciye, bölüm tablosuna, modeme ya da EFS bölümüne yazmaz; siz de öyle bırakın.
