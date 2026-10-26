# 10. Kendi kurtarma ortamımız

**Hedef:** telefonda, birincisini onarabilen küçük bir ikinci sistem - dokunarak, gerekirse bilgisayarsız.

## Eski güvenlik ağı neden gitmeliydi

5. bölümden beri telefonda iki sistem vardı: `BOOT` bölümündeki yeni sistem ve `RECOVERY` bölümünde Samsung'un metin terminalli 3.18 çekirdeği. Her çekirdek güncellemesi o eski sistemden geçiyordu: ona yeniden başla, `BOOT`'u oradan yaz, geri dön. Çalışıyordu ve projenin hata yapmayı göze alabilmesinin nedeniydi.

Ama aynı zamanda çıkmaz bir sokaktı. Yeni sürücüleri kullanamıyordu, tek arayüzü bir metin konsoluydu ve bilgisayarında projenin betikleri olmayan biri onunla hiçbir şey yapamazdı. Telefonun sahibi, Android'de TWRP ya da OrangeFox ne ise onu istedi: ekranda kutucuklar, İngilizce ve Türkçe.

## Nelerden oluşuyor

- Ana sistemle **aynı mainline çekirdek**. Ayrıca bakılacak bir şey yok.
- **Birkaç megabaytlık bir initramfs**; ana sistemin de içinden geçerek açıldığı aynı initramfs. `RECOVERY` bölümünden başlatıldığında sistemi devretmek yerine RAM'de kalır.
- Arayüzü LVGL kitaplığıyla doğrudan çerçeve belleğine çizen, **statik bağlanmış tek bir program**. Masaüstü yok, görüntü sunucusu yok.
- Depolamaya dokunan her şey için **kabuk betikleri** - `BOOT`'u yazmak, yedek almak, bağlamak - bilgisayarda imaj dosyaları üzerinde sınanabilsinler diye arayüzün dışında tutulur.

38 MiB'a sığmak ve kurulu sistemden hiçbir şeye gereksinmemek zorunda; çünkü bütün amacı, o sistem çalışmadığında çalışmaktır.

## Ona biçim veren kural

Telefonun sahibi erkenden bir kural koydu: kurulu sistemi silebilecek ya da dosya kaybettirebilecek işlevler yazılabilir, ama bu telefonda asla çalıştırılmaz ve denenmez. Tasarım bundan türedi.

- Kurulu sistem salt okunur bağlanır - ve bunun "salt okunur" sözcüğünden fazlasını gerektirdiği ortaya çıktı. Çekirdek günlüğü, ext4'ün böyle bir bağlama sırasında sahipsiz bir dosyayı sessizce sildiğini gösterdi. Artık önce bölüm blok aygıtı düzeyinde salt okunur yapılıyor ve günlük (journal) yeniden oynatılmıyor.
- Yazıcı yalnızca `BOOT` bölümünü yazabilir, başka hiçbir şeyi değil. Bölüm tablosu, önyükleyici, modem ve ötekiler seçilemez bile.
- Yazmadan önce eski içeriği saklar; yazdıktan sonra geri okuyup karşılaştırır; tek dokunuşla geri alır.
- Yedekler yalnızca SD karta gider, geri yükleme de yalnızca boş bir klasöre açar.
- Dört dakika boyunca kimse dokunmazsa kurulu sistemi kendiliğinden başlatır. Sonsuza dek bekleyen bir kurtarma ortamı, ölü görünen bir telefondur.

## Denemeler

"Bir ekran çiziyor"dan "kuruldu"ya varmak sekiz imaj sürdü.

- **Konsol arayüzün üstüne çizmeyi sürdürdü.** Çekirdeğin metin konsolu da program da çerçeve belleğinin sahibiydi; önce konsolun ayrılması gerekiyor.
- **Kısa dokunuşlar kayboldu.** Kitaplığın dokunma okuyucusu, olay kuyruğunu boşalttıktan sonraki durumu bildiriyordu; hızlı bir bas-bırak hiçbir şey olmamış gibi görünüyordu. Program artık dokunmatik ekranı kendisi okuyor.
- **İletisiz bir ret.** Geri alma için eski 32 MiB'lık `BOOT` içeriğini saklamak 8 MiB'lık RAM diskine sığmadı. Yazıcı `BOOT`'a dokunmadan reddetti - doğru davranış - ama hiçbir şey söylemedi.
- **"Hiç bağlanmayan" Wi-Fi.** Bağlantı durumunu soran yardımcı, `/tmp` içinde bir soket oluşturur; orası yazılabilir bir yer olarak yoktu.
- **Home tuşu bir şey yapmadı.** Bunu telefonun sahibi buldu; bu kartta tuş kendini kimsenin beklemediği bir tuş olarak bildiriyor.
- **Dil yeniden başlatmada kalmadı.** Kurtarma ortamının yazılabilir bir dosya sistemi yok ve kurulu sisteme yazamaz; bu yüzden ayarlarını kendi bölümünün sonundaki 512 baytlık tek bir blokta tutuyor.

Wi-Fi ayrı bir notu hak ediyor. Kurtarma ortamında Wi-Fi sürücüsü var, ama programlar ve kayıtlı ağ yok: bunları kurulu sistemden, salt okunur olarak **ödünç alır**. Böylece gizli bilgiler imajın dışında kalır. Kurulu sistemin dosyaları okunamıyorsa Wi-Fi de yoktur - hiçbir şeye bağlı olmayan USB seri kabuk ise yine oradadır.

## Ağı değiştirme anı

Yedek sistemi yeni bir şeyle değiştirmek, ikisinin birden kaybedilebileceği tek adımdır. Şu sırayla yapıldı:

1. Yeni kurtarma ortamı önce `BOOT`'tan çalıştı; eski sistem hâlâ `RECOVERY`'deydi. Gerçek telefonda bir çekirdek imajını yazıp doğrulayana ve geri alana dek böyle kaldı.
2. Eski `RECOVERY` bölümünün tamamı, onu geri yazan bir betikle birlikte, telefonda ve bilgisayarda dosya olarak saklandı.
3. Yeni kurtarma ortamı ancak ondan sonra `RECOVERY`'ye yazıldı.

O günden beri her çekirdek güncellemesi ondan geçiyor: bilgisayar bir imaj hazırlar, telefon kurtarma ortamına yeniden başlar, kurtarma ortamı `BOOT`'u yazıp doğrular, telefon yeni çekirdekle yeniden başlar. Aynı şey parmakla da yapılabilir.

## Bundan çıkarılacaklar

- Kurtarma sistemini ana sistemle aynı parçalardan kurun. İkinci bir çekirdek, ikinci bir projedir.
- Tehlikeli işlemleri, reddetmeyi bilen küçük betiklere koyun ve retleri dosyalar üzerinde sınayın.
- "Salt okunur", sorduğunuz katmanın sözüdür; altındaki katmanların değil.
- Yenisi sizi en az bir kez yakalamadan eski güvenlik ağını kaldırmayın.

Başvuru: [Grafik kurtarma ortamı](../reference/recovery.md).
