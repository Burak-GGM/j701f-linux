# 4. İlk mainline açılış

**Hedef:** telefonda güncel, olabildiğince az değiştirilmiş bir Linux çekirdeği başlatmak ve onunla kurulu Alpine sistemine ulaşmak.

## Neden "mainline"

"Mainline", bir telefon üreticisinin bir kez yayımlayıp hiç güncellemediği, ağır biçimde değiştirilmiş kopyanın aksine, kernel.org'da yayımlanan Linux çekirdeği demektir. Üreticinin 3.18 çekirdeği çalışıyor, ama yalnızca Samsung'un yapması için derlediği şeyleri yapabiliyor. Mainline çekirdek açık GPU sürücüsünü (Panfrost), güncel Wi-Fi ve grafik yığınlarını ve güvenlik düzeltmelerini getirir.

Exynos 7870 üst akımda boş bir sayfa değil. **exynos7870-mainline** adlı bir topluluk projesi temelleri — saatler, pin denetimi, PMIC, USB ve birkaç kardeş telefonun (Galaxy J6, J7 2016, A2 Core, On7) aygıt ağaçları — eklemiş. Bizim telefon, J701F, aralarında yoktu. Yani görev şuydu: bu telefon için bir aygıt ağacı yaz ve başka neyin eksik olduğunu bul.

## Birinci sorun: önyükleyici onu başlatmıyor

S-BOOT, Samsung'un yöntemiyle paketlenmiş, Samsung'un aygıt ağacı tablosunu taşıyan bir çekirdek bekler ve bilgiyi mainline çekirdeğin anlamadığı bir biçimde aktarır. Proje bununla boğuşmak yerine araya küçük, iyi bilinen bir program koydu:

```text
S-BOOT → Android açılış imajı → U-Boot → Linux
```

**U-Boot** açık kaynaklı bir önyükleyicidir. Burada telefonun önyükleyicisi olarak kurulmuyor — S-BOOT'a dokunulmuyor. U-Boot yalnızca Android imajının içindeki "çekirdek". S-BOOT onu herhangi bir çekirdek gibi başlatır; U-Boot sonra gerçek Linux çekirdeğini, aygıt ağacını ve initramfs'i kendi ikili dosyasına gömülü bir paketten (*FIT imajı*) yükler, çekirdek komut satırını ayarlar ve atlar.

U-Boot derlemesi bu telefon için yamalıdır (`kernel/diagnostic/j701f-embedded-ramboot.c`) ve herhangi bir imaj telefona yaklaşmadan önce QEMU öykünücüsünde çalıştırılıp gerçekten Linux'a devrettiği noktaya ulaştığı denetlenir. Ayrıca bilerek bozulmuş on beş imaj da sınanır; yükleyicinin onları reddettiğinden emin olunur.

## İkinci sorun: ne olduğunu bilmek

Erken aşamada takılan bir çekirdek şikâyetlerini telefonun dışarı açmadığı bir seri porta yazar. Bir süre her başarısız deneme aynı görünüyordu: siyah ekran. İki şey bunu değiştirdi:

- Aygıt ağacında bir **simple framebuffer** girdisi. Önyükleyici ekranı açık ve belleğin bir bölgesine (`0x67000000`, 720×1280) bakar halde bırakır. Çekirdeğe bunu söylemek ilk saniyeden itibaren ekranda bir metin konsolu verir — sonradan tanıdık bir manzara olan penguenler ve kayan iletiler.
- **ramoops**: çekirdeğin günlüğünü, bir sonraki açılışın okuyabilmesi için yazdığı ayrılmış bir RAM parçası.

Bütün bu denemeler `RECOVERY` bölümünde yapıldı; `BOOT` 3. bölümdeki çalışan sistemi tutmaya devam etti.

## Üçüncü sorun: USB görünmedi

Çekirdek açıldı, ama bilgisayar hiçbir USB aygıtı görmedi. Neden USB sürücüsünde değildi. Yonga seti ile USB bağlayıcısı arasında küçük bir yonga, **S2MU005 MUIC** oturur; veri hatlarını USB, fabrika UART'ı ve şarj algılama arasında anahtarlar. Üretici çekirdeği onu programlar; mainline'da sürücüsü yok, o yüzden anahtar açık kaldı.

Çözüm, üretici sürücüsünün yaptığını minik bir programdan yapmaktı: USB'yi başlatmadan önce initramfs'ten I²C üzerinden iki yazmaç yazmak (`CTRL1 = 0x13`, `SW_CTRL = 0x24`). Değerler önce üretici çekirdeği altında telefondan okundu. Bundan sonra gadget belirdi ve seri kabuk yeni çekirdekte çalıştı.

!!! tip "Ders"
    Bir mainline sürücüsü "eksik" olduğunda, çoğu zaman önemli olan iki üç yazmaç yazımını bulup elle yapmak yeterlidir. Düzgün bir sürücü sonra gelebilir.

## Depolama ve devir

Aygıt ağacında eMMC denetleyicisini açmak telefonun depolamasını görünür kıldı. initramfs sonra 3. bölümdeki yükleyici mantığını tekrarladı: `USERDATA`'yı dosya sistemi UUID'siyle bul, bağla, `switch_root`.

İlk kez, kurulu Alpine sisteminin içinde `uname -r` 3.18 yerine güncel bir sürüm bildirdi. Aynı kök dosya sistemi artık iki çekirdekle de başlatılabiliyordu: `BOOT`'tan üretici çekirdeğiyle, `RECOVERY`'den mainline çekirdeğiyle.

## Sayılan denemeler

Bu aşama, her biri fotoğraflanan ya da günlüğe alınan ve her biri tek bir şeyi değiştiren dokuz numaralı deneme sürdü. Başarısız olanlar nedeniyle birlikte `kernel/rejected-trials.json` dosyasına kaydedildi. O dosya çalışan kod kadar değerlidir: aynı çıkmaz sokağın ikinci kez denenmesini önler.

!!! info "Depodaki ayrıntılar"
    `docs/j701f-mainline.md`, bu aşamanın ve sonraki her aşamanın uzun biçimli günlüğüdür.
