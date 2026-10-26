# 11. İlk kamera

**Hedef:** sıradan bir kamera uygulamasında telefonun kamerasından bir görüntü.

İlk yol haritası kamerayı sona koymuştu: "çünkü en zoru". Android'de bu telefonun kameralarını FIMC-IS çalıştırır: büyük bir Samsung sürücüsü ve SoC'nin içindeki bir görüntü işlemcisi için kapalı bir aygıt yazılımı. Bunların hiçbiri mainline Linux'ta yok, belgesi de yok.

## Bunu mümkün kılan soru

İşe yarayan soru "FIMC-IS'i nasıl taşırız" değil, "bir karenin geçmek zorunda olduğu en az donanım hangisi" oldu.

```text
sensör → CSI-2 alıcısı → görüntü işlemcisi → bellek        (Android)
sensör → CSI-2 alıcısı → bellek                             (burada)
```

Bir kamera sensörü ham piksel değerlerini hızlı bir seri hat üzerinden yollar. SoC'deki bir alıcı bunları içeri alır. Android'de sonra görüntü işlemcisinden geçerler; o da bunları bitmiş bir resme çevirir. Ama bu SoC'nin alıcısı aldığını doğrudan belleğe de yazabiliyor; ham pikselleri resme çevirmek ise yazılımın yapabileceği bir iş: libcamera'nın tam bu durum için yazılımsal bir görüntü işlemcisi var. Böylece kapalı kısım tümüyle dışarıda bırakılabildi.

## Beş kilometre taşı

1. **Orada mı?** Arka sensöre üreticinin sırasıyla güç verip kimliğini I²C üzerinden okumak. Küçük bir deneme modülü; yanıt doğru yonga numarasıydı.
2. **Tek bir kare.** Sensörü bir kip için üreticinin yazmaç tablosuyla programlamak, alıcıyı bir bellek parçasına yöneltmek, gelene bakmak.
3. **Resim olan bir kare.** İlk kareler sağlama hatalarıyla geldi. Kamera bloğunun saatleri hâlâ önyükleyicinin bıraktığı yavaş osilatördeydi; üç seçici gerçek saatlere çevrilince hatalar bitti.
4. **Öteki kamera.** Ön sensör veri yolluyordu, alıcısı ise hiçbir şey görmüyordu. Üreticinin PHY sürücüsü, bir sistem yazmacında mainline sürücünün bilmediği bir biti daha kuruyor.
5. **Gerçek bir kamera aygıtı.** Her sensörü Linux'un beklediği biçimde sunan bir sürücü; böylece libcamera - ve onunla Plasma Camera - bu telefon hakkında hiçbir şey bilmeden "Internal back camera" ve "Internal front camera"yı buluyor.

## Kimsenin söylemediği şeyler

- **libcamera'nın genel işlem hattı yalnızca bilinen platform sürücülerinden oluşan bir listeyi kabul eder.** Buradaki sürücü adını o listeden biri olarak veriyor. Bu bir geçici çözümdür ve öyle de etiketlenmiştir; temiz çözüm libcamera'ya bir satır eklemektir.
- **Yazılımsal görüntü işlemcisi, `BOOT`'taki çekirdeğin sağlayamadığı türden bir bellek tamponu ister.** Yeni bir çekirdek derlemek yerine, çekirdeğin bunun için olan kendi sürücüsü ayrıca modül olarak derlendi.
- **GPU'da işleme, aşağı yukarı her üç başlatmanın birinde çöktü.** Oturum libcamera'ya işlemciyi kullanmasını söylüyor: kare başına yaklaşık 50 ms, önizleme için yeterli.

## Paragrafını hak eden iki hata

**Ortak bir anahtar.** İki sensörün arayüz gerilimini tek bir pin açıp kapatır. O pini iki yerden "paylaşımlı" olarak istemek çalıştı - bir modül yeniden yüklenene dek; sonra çekirdek, yeniden başlatmayı da kilitleyen bir biçimde çöktü. Pin artık bir kez, iki sensörün de başvurduğu bir regülatör olarak tanımlı; regülatör zaten bunun içindir.

**140 kilobayt fazla.** Başka bir veri düzeninin denemesi, tamponunu resmin boyutlarından hesapladı ve o düzenin piksel başına daha çok bayt kullandığını unuttu. Donanım tamponun sonunu aşıp ardından gelen neyse onun üstüne yazdı. Telefon, hiçbir şey bozulmuş belleğe güvenemeden hemen yeniden başlatıldı. Belleğe kendi başına yazan bir aygıt, bir C dizisinin sınırlarına saygı göstermez; tampon, donanımın yazacağı miktara göre boyutlandırılmalı ve denetlenmelidir.

## Sahibinin hükmü

Telefonun sahibinin çektiği ilk fotoğraflar tepetaklaktı. Bir sensörün dönüklüğü hiçbir yerden okunamaz; ilk değer üreticinin dosyalarından yapılmış bir tahmindi ve yarım tur yanlıştı.

Geldiği yer: Plasma Camera'da önizleme, fotoğraf ve kamera değiştirme çalışıyor. Video kaydı boş dosya üretiyor, otomatik odak yok, çözünürlük sensörün yapabildiğinin dörtte biri ve renkler, ayarlanmamış yazılım ne çıkarırsa o. Bu bir ilk kamera, iyi bir kamera değil; iş de şimdilik duraklatıldı.

## Bundan çıkarılacaklar

- Büyük bir üretici alt sistemini taşımadan önce, bir sonucun onun hangi parçalarından geçmek zorunda olduğunu sorun. Yanıt, çoğunu dışarıda bırakabilir.
- Donanımı, her biri tek bir şeyi kanıtlayan adımlarla ayağa kaldırın: kimlik, tek kare, temiz kare, aygıt.
- Donanım belleğe kendi başına yazıyorsa, o belleğin boyutu bir güvenlik konusudur.

Başvuru: [Kamera](../reference/camera.md).
