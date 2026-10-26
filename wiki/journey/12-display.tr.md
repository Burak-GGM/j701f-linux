# 12. Gerçek ekran sürücüsü

**Hedef:** önyükleyicinin geride bıraktığı bir resmin içine çizmek yerine paneli kendimiz sürmek.

## Çalışan şeyin nesi eksikti

İlk masaüstünden (6. bölüm) beri ekran bir hileyle çalışıyordu. Samsung'un önyükleyicisi paneli açar ve logosunu bir bellek parçasından gösterir; Linux aynı belleğe yazmayı sürdürebilir ve resim değişir. Çekirdek buna "basit çerçeve belleği" der. Ekran donanımının hiçbiri için sürücü gerektirmez.

Ama hiçbir ince ayarın kaldıramayacağı sınırları vardır. GPU bir kare çizer, sonra karenin tamamının o belleğe **kopyalanması** gerekir - en iyi durumda saniyede 54-56 kare. "Panel son kareyi göstermeyi bitirdi" diye bir işaret yoktur, paneli kapatmanın bir yolu yoktur, parlaklık da ancak pikselleri karartarak taklit edilebiliyordu.

## Zincir

```text
DECON  →  DSIM  →  EA8061S
(ekran     (MIPI DSI   (AMOLED
denetleyici) verici)    panel)
```

Mainline Linux'ta ilk iki blok için, başka Exynos yongaları için yazılmış sürücüler var; bu panel için ise yok. Panel sürücüsü, Samsung'un bu telefon için kaynağındaki başlatma sırasından yazıldı: on dokuz komut; bilgisayarda her baytı, her beklemeyi ve herhangi bir aktarım başarısız olduğunda ne olacağını denetleyen testlerle birlikte.

## Elinizdeki tek ekranda nasıl deney yapılır

Başarısız olan bir ekran sürücüsü siyah bir ekran bırakır; bu telefonun ikinci bir ekranı yok ve gece başında bekleyen kimse de yok. İşi mümkün kılan yöntem, sürücü denenmeden önce kuruldu:

- **Hiçbir şey kalıcı olarak yazılmadı.** Ekranın aygıt ağacı düğümleri, değişmemiş çalışan imajın üstüne, bir modülün yüklediği bir eklenti olarak çalışma anında eklendi. Bir sıfırlama her şeyi geri alır.
- **Sıfırlama güvence altındaydı.** Bir gözetmen program donanım bekçi zamanlayıcısını açar, denemeyi başlatır, sonra bekçiyi açık tutarak beslemeyi bilerek keser. Ne olursa olsun - başarı, takılma, çökme - telefon yarım dakika içinde çalışan imajla yeniden başlar.
- **Güvencenin önce provası yapıldı**; ekranla ilgili hiçbir şeyi değiştirmeyen bir denemeyle, sıfırlamanın gerçekten geldiği ve aynı sistemin gerçekten geri döndüğü kanıtlandı.
- **Sonuçlar görülmedi, okundu.** Çekirdeğin kendi ekran durumu, panelin bir durum komutuna verdiği yanıt, tamamlanan kare çevirme sayısı. Telefonun sahibi bakana dek her rapor "görünüş görülmedi" dedi.

## Yolda duranlar

- **Zamanlama sayıları.** Ortak DSI sürücüsü yatay zamanlamayı, önyükleyicinin çalıştırdığından farklı programlayacaktı (çalışan bağlantı 56/48/4 kullanırken 46/39/0). Telefona özgü, varsayılan olarak kapalı bir zamanlama profili eklendi.
- **Tersine yazılmış bir denetim.** Sürücü, vericinin saat üretecinin kararlı olduğunu bildirmesini bekler. O sınama ters çevrilmişti, kesmesi de maskelenmişti; bekleme ya zaman aşımına uğruyor ya da yanlış nedenle geçiyordu.
- **İki adımın sırası.** Panele komutları, verici onları taşımaya hazır olmadan gönderiliyordu. "Önce vericiyi hazırla" diyen tek bir satır son düzeltme oldu.

Sonra, kimsenin izlemediği bir denemede: panel bir durum isteğine yanıt verdi ve 120 kare saniyede 59,641 hızla çevrildi.

## Bir denemeden her sabaha

Geçen bir deneme masaüstü demek değildir. Üç adım daha geldi; her biri yine RAM'den ve arkasında bekçiyle:

1. **Yerel sürücüde Plasma.** Bileşikleyici artık bitmiş kareleri ekran denetleyicisine kopyasız veriyor: saniyede 59,5-59,8 kare; bu da düpedüz panelin kendi hızı.
2. **Parlaklık.** AMOLED bir panelin arka ışığı yoktur; parlaklık paneldeki bir yazmaçtır. Aralık Samsung'un tablosundan alındı.
3. **Ekranı kapatıp açma** ve uykudan uyanma.

Sonra telefonun sahibi ekrana baktı; görüntüyü, parlaklığı ve karartmayı doğruladı. Geçiş ancak bundan sonra her açılışın parçası oldu - yine açılış imajına gömülmeden, kök dosya sisteminden yüklenerek; böylece önyükleyicinin çerçeve belleği geri dönüş yolu olarak hazır kalıyor: açılırken Ses Kısma'yı basılı tutun, telefon onda kalır.

Tam burada bir arıza daha ortaya çıktı. Geçiş bir damga dosyasıyla korunur: telefon masaüstü açılmadan sıfırlanırsa sonraki açılış geçişi atlar. İlk sürüm bundan sonraki her açılışta da, sessizce, atlamayı sürdürüyordu - ve ilk sıradan yeniden başlatma onu tetikledi. Haber vermeden devrede kalan bir güvenlik ağı başlı başına bir arızadır; damga artık tek bir açılışa mal oluyor.

## Bundan çıkarılacaklar

- İleri giden yoldan önce geri dönüş yolunu kurun ve provasını yapın.
- Kimsenin izlemediği donanımda, neyin kanıt sayılacağına önceden karar verin ve görülmemiş olanı açıkça söyleyin.
- Eski yolu, bir bedeli olmadığı sürece yenisinin yanında yaşatın.

Projenin bu kısmını Codex başlattı, Claude bitirdi. Başvuru: [Gerçek ekran sürücüsü](../reference/display.md).
