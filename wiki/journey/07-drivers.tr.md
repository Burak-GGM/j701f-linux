# 7. Kademe kademe sürücüler

**Hedef:** "açılıyor ve masaüstü gösteriyor" durumunu, donanımı düzgün davranan bir telefona çevirmek.

Aşağıdaki her kalem kendi küçük kademesi olarak yapıldı: bir imaj derle, kur, doğrula, ekran görüntüsü al, yaz. Bir seferde tek şeyi değiştirmek kâğıt üstünde yavaş, uygulamada hızlıdır; çünkü bir şey bozulduğunda tek bir şüpheli vardır.

## Önce daha yeni bir çekirdek

İlk mainline açılışlar Linux 6.15'i, exynos7870-mainline ağacının tamamıyla kullandı. Sürücülere yatırım yapmadan önce taban, kernel.org'dan **Linux 7.1.13**'e ve yalnızca henüz üst akıma girmemiş altı topluluk yamasına taşındı. Daha yeni bir taban, taşınacak daha az özel yama demektir ve bunu erken yapmak geç yapmaktan kolaydır. Eski çekirdek yapılandırması, bir karşılaştırma gerekirse diye depoda tutuluyor.

## Pil göstergesi

Pil ölçer, S2MU005 yongasının bir parçasıdır ve mainline'da sürücüsü vardır. Yalnızca doğru I²C veri yolunda bir aygıt ağacı düğümüne ihtiyaç duydu. Masaüstünün pil göstergesi gerçek bir yüzde göstermeye başladı.

## Sıcaklık

Yonga setinin sıcaklık sensörünün (TMU) bu yonga için mainline desteği yok. Küçük, **salt okunur** bir sürücü yazıldı: kalibrasyon değerlerini okur, sensör okumasını dereceye çevirir ve donanıma hiç yazmaz. Bunun üstüne aygıt ağacı üç eşik tanımlar: 70 °C'de yavaşla, 85 °C'de uyar, 105 °C'de kapan.

## Watchdog

Watchdog, yazılım onu "beslemeyi" sürdürmedikçe makineyi sıfırlayan bir zamanlayıcıdır. Yonga setinde bir tane var ve mainline destekliyor. Açılışın ilk anından itibaren 30 saniyelik sınırla kurulu. Bu, sonraki her denemeyi "telefon dondu, birinin güç düğmesini basılı tutması gerek"ten "telefon kendini yeniden başlatır"a çevirdi.

## CPU frekans ölçekleme

Mainline çekirdek, kutudan çıktığı haliyle sekiz çekirdeğin hepsini önyükleyicinin bıraktığı 902 MHz'de tuttu. Üretici çekirdeği onları 546 ile 1586 MHz arasında çalıştırır. Bir işlemcinin saatini çalışırken değiştirmek naziktir ve bu yonga için mainline sürücüsü yoktur; o yüzden ölçümlerden yola çıkarak bir tane yazıldı:

1. **Ölç.** Üretici çekirdeği altında her frekans kademesi sırayla seçildi ve besleme gerilimi (`BUCK1` regülatörü) geri okundu. O tablo `build/kernel/vendor-opp-measurement.txt` dosyasında saklı.
2. **Sırala.** Frekansı değiştirmek için: yukarı çıkılıyorsa gerilimi yükselt; çekirdekleri yedek bir "anahtar" saatine al; PLL'i yeniden programla ve kilitlenmesini bekle; çekirdekleri geri al; aşağı iniliyorsa gerilimi düşür.
3. **Pay bırak.** Her gerilime 12,5 mV eklenir.

On bir kademenin hepsi doğrulandı. Tek çekirdekli bir başarım ölçümü beklendiği gibi ölçekleniyor: 546 MHz'de 254 olay/sn'den 1586 MHz'de 741'e.

## Tuşlar, Bluetooth, ivmeölçer

- İki **dokunmatik tuş** bir Coreriver TC360 yongasıdır. Mainline sürücüsü neredeyse uyuyor, ama bu yonga basışları tuş kodu olarak değil bit eşlemi olarak bildiriyor; küçük bir yama bu biçimi ekler. "Görev değiştirici" ve "geri"ye eşlendiler.
- Wi-Fi yongasının **Bluetooth** yarısı aygıt ağacında tarif edildi ve denetleyici görünüyor. Kullanıcı alanı tarafında eşleştirme kurulmadı.
- **İvmeölçerin** (ST LIS2HH12) mainline sürücüsü var; yalnızca bir düğüm gerekti.

## GPU frekans ölçekleme

CPU gibi GPU da açılış frekansında, 343 MHz'de takılıydı; üretici çekirdeği ise 1001 MHz'e kadar kullanıyor. Düzeltmenin üç parçası var:

- Saat sürücüsüne GPU PLL'inin yedi üretici kademesi için ayarlarını öğretmek.
- PLL'i değişirken GPU'yu yedek saate alan küçük bir sürücü; CPU'lardakinin aynısı.
- Panfrost'un kendi ölçekleme mantığı için aygıt ağacında bir frekans ve gerilim tablosu.

Buradaki bir hata telefonu her açılışta kilitleyebileceğinden, **isteğe bağlı** olacak şekilde kuruldu: çekirdek GPU'yu 343 MHz ile sınırlı başlatır ve sınırı açılıştan 40 saniye sonra bir betik yükseltir. Telefon yükseltmeden kısa süre sonra sıfırlanırsa, betik bunu bir sonraki açılışta fark eder ve sınıra dokunmaz.

Sonuç: eşzamanlamasız bir çizim sınaması saniyede yaklaşık 250 kareden yaklaşık 800 kareye çıktı.

Aynı kalıp — çekirdekte güvenli bir varsayılan, kullanıcı alanından korumalı bir yükseltme — artık CPU'nun en yüksek hızı ve ses sürücülerinin yüklenmesi için de kullanılıyor.

## Isıyı hıza bağlamak

Son olarak CPU ve GPU'nun ikisi de 70 °C eşiğine "soğutma aygıtı" olarak kaydedildi; böylece yonga ısındığında çekirdek ikisini birlikte yavaşlatır. Sekiz çekirdeğin hepsi 1586 MHz'de ve GPU 1001 MHz'deyken dört dakika, sensörü 54'ten 60 °C'ye çıkardı — eşiğin altında; yani kısma elle sınandı ama henüz kendiliğinden devreye girmedi.

## Sonraki tur: depolama, küçük parçalar, Bluetooth

Sesten ([8. bölüm](08-sound.md)) sonra iş, telefon sahibinin belirlediği sırayla bu listeye döndü: önce başarım, sonra gündelik telefon özellikleri.

- **eMMC** en yavaş kipinde çalışıyordu. Daha hızlı kiplere izin vermek sıralı okumayı 22'den 60–80 MB/sn'ye çıkardı. Bir üst kip (HS200) açıldı, sonra her yazmada hata verdi; geri alındı ve arkasında bir kural bıraktı: bir depolama kipini asla açıldığın dosya sisteminde deneme.
- **Titreşim motoru, microSD yuvası ve yakınlık sensörü**nün her biri yalnızca bir aygıt ağacı düğümü gerektirdi, çünkü mainline'da uyan sürücüler zaten var: motor anahtarlanan bir regülatör, kart yuvası kardeş bir telefonla aynı ve sensör başka bir ad altındaki mevcut bir sürücüyle destekleniyor. Üçü de telefon ulaşılamazken hazırlandı ve ilk açılışta çalıştı.
- **Bluetooth** yama yazılımına, sabit bir adrese ve BlueZ hizmetine kavuştu; tarama çevredeki aygıtları buluyor.
- **Donanımsal video çözme** iki deneme aldı. İlkinde sürücü yüklendi ama çözücünün kendi yazılımı hiç başlamadı. Çözücünün yazmaçları yanıt veriyordu, yazılım imajı yerindeydi ve tek bir kesme gelmiyordu. Neden, çözücü ile bellek arasında oturan bir bellek yönetim birimiydi: sıfırlamadan *etkin ve engelleyici* çıkıyor, bu yüzden çözücü kendi yazılımını okuyamıyordu. O birimi geçirgen kipe almak tek yazmaçlık bir düzeltmeydi; ardından 720p bir video, yazılımsal çözmeye göre yaklaşık 24 kat daha az işlemci zamanıyla çözüldü.

Bir olay da buraya ait. Güç yönetim bloğunun her yazmacını döken bir hata ayıklama dosyasını okumak, okuyan süreci çekirdeğin içinde çökertti ve bir kilidi tutulu bıraktı; sonraki yeniden başlatma, watchdog çoktan kapatılmışken takıldı ve telefonun elle yeniden başlatılması gerekti. Watchdog artık kapanış boyunca kurulu kalıyor.

## Yapılamayanlar

- **Kamera.** Samsung'un kamera hattının (FIMC-IS) bu yonga için mainline sürücüsü yok ve taşımak başlı başına bir proje.
- **Gerçek ekran sürücüsü.** Panelin ve ekran denetleyicisinin parametreleri kayıtlı, ama o sürücüyü yazıp sınamak ekranı izleyen birini gerektiriyor.
- **Modem, uyku, şarj denetimi**ne başlanmadı.
