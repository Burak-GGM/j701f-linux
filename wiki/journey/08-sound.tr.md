# 8. Ses

**Hedef:** telefonun hoparlöründen bir şey duymak.

Ses, projedeki en büyük tek donanım işiydi ve merkezdeki yonga için hiçbir mainline sürücüsünün bulunmadığı ilk işti. Burada, hatalar dahil, olduğu sırayla anlatılıyor; çünkü öğretici olan kısım hatalar.

## Telefon sesi nasıl çıkarıyor

Dört blok işin içinde ve hoparlör kıpırdamadan önce dördünün de doğru olması gerekiyor:

```text
uygulama → PipeWire → I2S denetleyicisi → ses mikseri → kodek → hoparlör
                       (yonga setinde)     (yonga setinde) (PMIC'te)
```

- **I²S denetleyicisi** sayısal sesi yonga setinden dışarı gönderir. Mainline'da sürücüsü var.
- **Ses mikseri** (Samsung "S1402X") I²S denetleyicisi ile kodek arasında oturur ve uygulama işlemcisinden, modemden ve Bluetooth'tan gelen sesi birleştirebilir. Mainline sürücüsü yok.
- **Kodek** (Samsung "COD3026X") sayısal sesi hoparlör, ahize ve kulaklık girişi için analog sinyale çevirir. Ayrı bir yonga değildir: güç yönetim yongasının içinde yaşar. Mainline sürücüsü yok.
- Çevrelerinde ses saatleri, I²S denetleyicisini besleyen bir DMA denetleyicisi ve Samsung'un **LPASS** dediği bir sıfırlama bitleri bloğu var.

## Üretici kodunu okumak

Kodek için veri sayfası olmadığından, nasıl çalıştığının tek tarifi Samsung'un üretici çekirdeğindeki kendi sürücüsü: kodek için 4.300, mikser için 2.400 satır. Telefonun sahibi, üretici ve özel ROM çekirdeklerini okuyup onlardan taşıma yapmak için kalıcı izin verdi. Kullanılan dosyalar, kaynak commit'i ve sağlama toplamlarıyla `build/kernel/vendor-audio-reference/` altında saklı.

Taşımak, 7.000 satırı kopyalamak anlamına gelmedi. Üretici kodunun çoğu ilk ses için gerekmeyen şeylerle uğraşıyor: sesli aramalar, FM radyo, kulaklık düğmeleri, su algılama. İşe yarayan çekirdek birkaç **sıra**: "hoparlörü açmak için şu yazmaçları şu sırayla, şu beklemelerle yaz". Bunlar çıkarılıp güncel çekirdek için yazılmış yeni, çok daha küçük sürücülere yerleştirildi.

## 1. kademe: saatler ve tesisat

İlk kademe ses saat denetleyicisini açtı ve sıfırlama bitlerini bırakan küçük bir LPASS sürücüsü yazdı.

Saat işinden bir bulgu çıktı: mainline ses PLL'ini *tamsayı* PLL olarak tarif ediyordu. Önyükleyici onu 98.304.019 Hz'de çalışır bırakıyor — 26 MHz ile beslenen bir tamsayı PLL'in üretemeyeceği bir frekans. Üretici kodunda olduğu gibi *kesirli* bir PLL'dir ve saat sürücüsü düzeltildi.

!!! failure "Açılış döngüsü"
    Bu sürücülerin çekirdeğe gömülü olduğu ilk imaj açılışı atlatamadı: penguenler, yazılar, yeniden başlama, tekrar. Watchdog işini yaptı, ama aynı bozuk çekirdeğe yeniden başlamak kimseye yardım etmez. Telefonun sahibi recovery tuş kombinasyonunu basılı tutmak zorunda kaldı ve önceki imaj üretici sisteminden geri yazıldı.

    Çökme kaydı kaybolduğu için kesin neden hiç saptanamadı. Değişen şey *yöntem* oldu: o andan sonra yeni ses sürücüleri kendiliğinden yüklenmeyen **modüller** olarak derlendi. Açılıştan sonra SSH üzerinden elle yükleniyorlar. Biri çökerse telefon çalışan bir sisteme sıfırlanır ve kayıt hayatta kalır.

## 2. kademe: kodek, mikser, ses kartı

Sırada kodek sürücüsü (yalnızca çalma), mikser kurulumu ve I²S, mikser ve kodeği bir ses kartı olarak birbirine bağlayan bir "makine sürücüsü" vardı. Kodek I²C'de `0x04` adresinde bulundu — I²C standardının ayırdığı bir adres; bu yüzden aygıt ağacının onu kabul ettirmek için on bitlik adres olarak işaretlemesi gerekiyor.

`J701F` adlı bir ses kartı belirdi ve PipeWire onu tanıdı. İlk deneme tonu G/Ç hatasıyla başarısız oldu: I²S denetleyicisi saat üretmeye hiç başlamadı. Bu yonga seti, "Exynos 7" adının düşündürdüğünden *daha eski* bir yazmaç düzeni kullanıyor. Uyan tür seçilince veri aktı.

Ve hoparlör sessiz kaldı.

## 3. kademe: son üç anahtar

Buradan sonra ilerleme, hiçbir uzaktan aracın yerini tutamayacağı tek ölçü aletine bağlıydı: telefon sahibinin kulaklarına.

| Deneme | Ne düzeltildi | Ne duyuldu |
| --- | --- | --- |
| 1 | — | Hiçbir şey |
| 2 | Mikser ile kodek arasındaki dört I²S teli ses işlevine hiç alınmamıştı (pin denetimi) | Hiçbir şey |
| 3 | Bu telefonda kodeğin ana saati mikserden farklı bir pinden çıkıyor (üretici aygıt ağacında bir kart seçeneği) | Tık sesleri |
| 4 | Mikserin, uygulama sesini karışıma alan "kanal 1 etkin" biti | **Notalar — çok yüksek sesle** |

Tık sesleri iyi haberdi: hoparlör yükselticisinin açılıp kapanmasıydı; yani analog yarı çalışıyordu ve yalnızca sayısal yol hâlâ bozuktu.

## Cilalama

- **Çok yüksek, sonra bozuk.** Hoparlör kazanç yazmacı 0–15 kabul ediyor, ama üreticinin kendi açıklaması gerçek aralığı 0–9 olarak veriyor. Denetim artık 8'de sınırlı.
- **Sesten sonra hışırtı.** Yükseltici çalmadan sonra birkaç saniye açık kalıyordu. Artık hemen kapatılıyor.
- **Başlangıçta bir tık.** Kodek, ses akışı gerçekten başlayana kadar sayısal olarak sessizde tutuluyor.
- **İkinci ses hiç çalmadı.** Üreticinin kapatma sırası, kullanıcı anahtarı olarak da sunulan yazmaç bitlerini temizliyor ve yolu "kapalı" bırakıyordu. O anahtarlar kaldırıldı.
- **Ses tuşları bir şey yapmadı.** Desibel ölçeği olmadan masaüstü yalnızca dokuz kaba kademe görüyordu ve %5'lik bir tuş basışı olduğu yere geri yuvarlanıyordu. Üreticinin ölçeklerini eklemek sorunu çözdü.

## Ses ne durumda

Hoparlör çalıyor, sistem sesleri temiz, ses tuşları çalışıyor ve sürücüler açılışta, frekans sınırlarıyla aynı sıfırlama korumasının arkasında yükleniyor. Ana mikrofondan kayıt da aynı yolla, üreticinin açma sırası alınarak eklendi ve kimse dinlemeden doğrulandı: telefon kısık bir ton çaldı ve o tonu kendi kaydında buldu. Kulaklık ve ahize yazıldı ama denenmedi. İkinci mikrofon ve kulaklık mikrofonu, kulaklık algılama ve arama sesi taşınmadı.
