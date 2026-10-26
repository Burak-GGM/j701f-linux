# 6. Plasma Mobile

**Hedef:** GPU'nun çizdiği, dokunmaya uygun bir grafik masaüstü.

## "Bir kabuk"tan "bir oturum"a

Buraya kadar telefon, ilk süreç olarak tek bir kabuk betiği başlatıyordu. Bir masaüstü çevresinde daha fazlasına ihtiyaç duyar: hizmetleri başlatıp gözeten bir şey, hangi kullanıcının hangi ekranın başında oturduğunu bilmenin bir yolu, bir giriş yöneticisi. Alpine'de bu şu demektir:

- **OpenRC**, hizmet yöneticisi,
- **elogind**; oturumları izler ve aygıtları (ekran, dokunmatik) giriş yapmış kullanıcıya verir,
- **D-Bus** ve **PipeWire**; ileti veri yolu ve ses/görüntü sunucusu,
- **SDDM**; otomatik giriş yapacak şekilde ayarlanmış giriş yöneticisi,
- **Plasma Mobile**'ın kendisi, Wayland bileşikleyicisi olarak **KWin** ile.

Özgün başlangıç betiği ilk süreç olarak korundu ve OpenRC ondan, yalnızca telefon mainline çekirdeği çalıştırırken başlatılıyor. Bu, üretici çekirdekli yedeği basit ve değişmemiş tutar.

## Pikseller ekrana nasıl ulaşıyor

Telefonun gerçek ekran denetleyicisi için hâlâ sürücü yok. Ekran, önyükleyici onu kurduğu ve çekirdeğe görüntünün bellekte nerede durduğu söylendiği için çalışıyor (`simpledrm`). Bu "aptal" bir ekrandır: bitmiş bir görüntüyü gösterebilir ama çizim yapamaz.

GPU ise tersidir: çizebilir ama kendi ekran çıkışı yoktur. Mesa ikisini **kmsro** denen bir düzenekle birleştirir — Panfrost her kareyi çizer, sonuç basit ekrana kopyalanır. KWin çiziciyi `Mali-T830 MC1 (Panfrost)` olarak bildirir ve canlandırmalar akıcıdır.

Gerçek ekran sürücüsünün olmamasının bedeli: parlaklık ayarı yok, paneli gerçekten kapatmanın yolu yok ve yenileme hızı sabit.

## Ters giden şeyler

"Paketler kuruldu"dan "dokunabildiğin bir masaüstü"ne varmak bir akşamlık küçük sürprizler aldı. Bu tür işler için tipikler:

**Plasma logosundan sonra siyah ekran.** Görünen her şey Wayland olduğu halde oturum yöneticisi **Xwayland**'in kurulu olmasını istiyordu. Bir paket ve bir dizin (`/tmp/.X11-unix`) sorunu çözdü.

**Telefon "kendi kendine yeniden başladı".** Çökmedi: güç düğmesine tek kısa basış, bir bilgisayarda olacağı gibi, elogind'e sistemi kapattırdı. Güç tuşu artık elogind tarafından yok sayılıyor ve Plasma'ya bırakılıyor.

**Saniyede 5 kare gösteren bir başarım ölçümü.** Ekran güç tasarrufuyla karartılmıştı; bileşikleyici kare sunmuyordu. Ekran uyanıkken aynı sınama dikey eşzamanlamayla 44 FPS, onsuz 200'ün üstünde çalıştı.

**"Bildirim çekmecesi açılmıyor."** Açılıyordu; onu uzaktan sınayan yöntem yanlıştı. Dokunma olayları olarak enjekte edilen gerçek bir kaydırma çekmeceyi açtı.

Son ikisi aynı ders: bir şeyi düzeltmeden önce, ölçümün doğruyu söylediğinden emin ol.

## Telefona dokunmadan çalışmak

Bu aşamanın bir bölümü, telefonun sahibi telefondan uzaktayken yapıldı. Bu, ekranı uzaktan görüp kullanacak araçlar gerektirdi:

- `tools/phone-screenshot.sh` ekranı uyandırır, oturumun kilidini açar, KWin'den ekran görüntüsü ister ve bilgisayarda PNG'ye çevirir.
- `tools/inject-swipe.py` ve `tools/inject-key.py` çekirdeğin girdi aygıtlarına dokunma ve tuş olayları yazar; böylece bir hareket SSH üzerinden yapılabilir.

Bunlar [araçlar](../reference/tools.md) sayfasında belgeli.

## Gezinme tuşları

Telefonun fiziksel bir Home düğmesi ve yanında iki dokunmatik tuşu var. Home, Plasma Mobile'ın ana ekrana dönmek için kullandığı "Meta" tuşuna eşlendi. Dokunmatik tuşlar daha sonra, sürücü kademelerinde geldi.

Bu bölümün sonunda telefon gerçek bir masaüstü gösteriyor, terminal açıyor, ağdan yazılım kuruyor ve parmakla kullanılabiliyordu.
