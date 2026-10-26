# 9. İnanılabilir bir pil yüzdesi

**Hedef:** doğru bir pil yüzdesi ve pile özen gösteren bir şarj.

Bu bölüm bilerek sıra dışı. Sesle bu bölüm arasında gerçek ekran sürücüsü, kurtarma ortamı ve ilk kamera geldi; bunlar, sonradan yazılan 10-12. bölümlerde anlatılıyor. Pil ise bir öykü olarak anlatılıyor, çünkü projede bir hafta boyunca "çalışan" ama aslında çalışmayan bir şeyin en iyi örneği.

## Elde ne vardı

Telefonun şarj devresi, pil ölçeri ve USB anahtarı tek bir yongadır: Samsung S2MU005. Mainline Linux'ta pil ölçer kısmı için bir sürücü var ve erkenden açılmıştı: masaüstü bir yüzde, bir gerilim, bir şarj simgesi gösteriyordu. Şarj kısmının, yonganın ne yaptığını yalnızca bildiren küçük bir yerel sürücüsü vardı. Şarjı, önyükleyicinin bıraktığı ayarlarla yonganın kendisi yapıyordu.

Durum tablosunda "Pil göstergesi ✅" yazıyordu.

## Tutmayan sayı

Telefonun durumuna sıradan bir bakış şunu gösterdi:

```text
doluluk    %43
gerilim    4,35 V
akım       +0,19 A
şarj       Dolu
```

4,35 V'ta olan ve neredeyse hiç akım almayan bir lityum hücre doludur. Şarj yongası da bunu kendisi söylüyordu. Ölçer ise %43 diyordu.

Ölçerin yazmaçlarını okumak, yanlış ayarlanmış bir şey olmadığını gösterdi: yongadaki pil modeli tablosu, fabrika aygıt ağacındakiyle aynıydı. Ham değer gerçekten %43'tü. Yonga düpedüz yanılıyordu.

## Neden

Ölçer yük sayar. Her saniye, giren akımı ekler, çıkanı çıkarır. Küçük ölçüm hataları birikir ve günler sonra sayım gerçekten çok uzaklaşır.

Samsung'un sürücüsü bunu bilir. Hücre geriliminin bir sayımdan çok daha fazlasını söylediği yerlerde, yani doluya ve boşa yakınken, yongayı başka bir kipe alır; bu kipte yonga sayısını gerilimin ima ettiği değere doğru çeker. Arada yeniden saymaya döner. Bunu tek bir yazmaç yapar. Mainline sürücü yongayı yalnızca okur; dolayısıyla bu telefonda sayım, Android'in gittiği günden beri kayıyordu.

Kanıt iki dakika sürdü: o tek yazmaca elle yazmak ve izlemek.

```text
%43  →  %47  (iki dakika)  →  %91  (yarım saat)  →  %100
```

## İkinci bir görüş

%100'ün doğru olduğunu, yalnızca daha hoş bir yanlış sayı olmadığını nereden biliyoruz? Aynı akşam şarj sürücüsü şarjı kapatmayı öğrendi. Şarj kapalıyken ve telefon kablodan çalışırken pilden akım geçmez ve gerilimi dinlenme değerine oturur: 4,28 V. Bu tür bir hücre için bu, %90'ın epey üstünde bir pil demektir. Birbirinden bağımsız iki ölçüm artık aynı şeyi söylüyor.

## Yeni bir çekirdek imajı olmadan sıcaklık

Bir şarj devresi, pil soğukken ya da sıcakken yavaşlamalıdır; Samsung'unki öyle yapar. Bunun için pilin sıcaklığı gerekir; o da SoC'nin analog-sayısal çeviricisi üzerinden okunan bir termistörden gelir - mainline aygıt ağacının hiç sözünü etmediği bir aygıt.

Yeni donanım tanımlamak normalde yeni bir aygıt ağacı, dolayısıyla yeni bir `BOOT` imajı demektir. Burada ise küçük bir çekirdek modülü bir aygıt ağacı **eklentisi** (overlay) taşır - sistem çalışırken uygulanan bir aygıt ağacı yaması - ve çeviricinin düğümünü kendisi ekler.

İlk denemede çekirdeğin var olan Exynos ADC sürücüsü kullanıldı. Aygıta bağlandı ve her dönüştürme zaman aşımına uğradı. Üreticinin başlatma sırasını yazmaçlara elle yazmak ise hemen çalıştı: bu yonganın türü farklı başlatılıyor ve sonucunu başka bir adreste tutuyor. Bu yüzden modül kırk satırlık kendi sürücüsünü de getiriyor ve telefon artık şunu bildiriyor:

```text
pil    24,4 °C
kart   32,5 °C
```

## Şarj

Kablo türü ve sıcaklık bilinince şarj akla yatkın hale getirilebildi:

| Durum | Önce | Şimdi |
| --- | --- | --- |
| Bilgisayar girişi | 450 mA | 450 mA |
| Duvar şarjı | 450 mA | 1000 mA, 15 ile 41 °C arasında 1500 mA'e kadar |
| Pil soğuk ya da sıcak | 450 mA | düşürülür; 50 °C üstünde ya da 0 °C altında kapatılır |
| "%80'de dur" | mümkün değildi | isteğe bağlı |

Duvar şarjı satırının durumu başvuru sayfalarında açıkça yazıyor: yazıldı ve benzetilmiş bir sistemle sınandı, ama henüz gerçek bir duvar şarjıyla karşılaşmadı.

Kararlar (ölçer kipi, sıcaklık sınırları, isteğe bağlı şarj sınırı) tek bir küçük betikte, `system/battery/j701f-battery` içinde durur; yanında onu geçici dosyalardan yapılmış sahte bir telefona karşı çalıştıran bir test dosyası vardır. Bu testlerden biri ilk çalıştırmada başarısız oldu - ve yanlış olan betik değil, testti: üreticinin "neredeyse boş" kuralı gerilimi yüke göre düzeltir; testi yazan (aynı yazar) bunu unutmuştu.

## Bundan çıkarılacaklar

- "Bir sayı gösteriyor" bir sınama değildir. Birbirini tutması gereken iki değer bulun ve karşılaştırın. Projenin sağlık denetimi (`tools/phone-health.sh`) artık her çalıştığında yüzde ile gerilimi karşılaştırıyor.
- Bir mainline sürücüsü var olsa bile, üretici sürücüsünün yaptığının yalnızca yarısını yapıyor olabilir. Eksik yarı çoğu zaman bir özellik değil, bir düzeltmedir.
- Bir modülün yüklediği aygıt ağacı eklentisi, hiçbir şeyi yeniden yazmadan küçük bir donanım parçasını tanımlamanın meşru bir yoludur.

Ayrıntılar ve dosya adları: [Kullanıcı alanı → Pil yüzdesi, sıcaklık ve şarj](../reference/userspace.md#pil-yuzdesi-scaklk-ve-sarj).
