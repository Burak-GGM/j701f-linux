# Gerçek ekran sürücüsü

!!! success "Durum: yerel sürücü gündelik yol (2026-10-10'dan beri)"
    Her açılış, masaüstü başlamadan önce önyükleyicinin çerçeve belleğinden (`simpledrm`) gerçek **DECON → MIPI DSI → EA8061S** yoluna geçer: kare başına kopya olmadan panelin 59,6 Hz'inde sayfa çevirme, gerçek panel parlaklığı, ekranı kapatıp açma, uykudan dönüş. Önyükleyicinin çerçeve belleği yedek yol olarak kalır. Aşağıdaki bölümler oraya nasıl gelindiğinin kaydıdır, en yenisi başta; öyküsü [yolculuğun 12. bölümünde](../journey/12-display.md).

## Plasma yerel sürücüde (2026-10-10)

Codex yokken ekran işini Claude devraldı. Aynı bekçi zamanlayıcılı geri dönüşle, yalnızca RAM'de üç deneme daha yapıldı:

| Deneme | Sonuç |
| --- | --- |
| `plasma-dsimpll2-02` | Plasma yerel sürücüde başladı: KWin `exynos-drm` üzerinde, Panfrost ekran aygıtında ayrılmış bir arabelleğe çiziyor, kopyalama yok. Kopyalanan çerçeve belleğinde saniyede 54–56 kare veren deneme burada **59,5–59,8** veriyor, yani panelin yenileme hızı. KWin'in ekran görüntüsü normal bir ana ekran |
| `plasma-bl-01` | Panel sürücüsünün artık bir arka ışık aygıtı var (`j701f-panel`): düzeyler panelin AOR yazmacına eşleniyor, aralık üreticinin tablosundan alındı. Beş düzey yazılıp geri okundu, DSI bağlantısından şikâyet yok |
| `plasma-dpms-01` | Ekranın bileşikleyici üzerinden kapatılıp açılması: kapalıyken çıkış etkin değil, sonra geri geliyor, yine saniyede 59 kare |

Bu denemeler sırasında paneli kimse görmedi; sayılar çekirdeğin ekran durumundan ve bileşikleyiciden geliyor. Telefon sahibi sonradan baktı (aşağıda).

**2026-10-10'dan beri günlük yol.** Telefon sahibi yerel sürücüde panele baktı; resmi, parlaklığı ve ekranın kapanıp açılmasını doğru buldu. Bir açılış servisi (`system/display-native/`, `/etc/init.d/j701f-display` olarak kurulu) artık her açılışta masaüstü başlamadan önce ona geçiyor. Üretici çerçeve belleğine dönüş yolları: telefon açılırken Ses Kısma'yı basılı tutmak; başarısız ya da takılan bir geçiş yeniden başlatır ve sonraki açılışların geçişi atlamasını sağlayan bir işaret bırakır; ya da `/etc/j701f-display-native` dosyasını silmek. Ekran düğümleri hâlâ bir modülün yüklediği, BOOT'taki çekirdeğe sabitlenmiş bir kaplamadan geliyor: çekirdek güncellemesinden sonra modüller yeniden derlenmeli, yoksa geçiş vazgeçer ve telefon üretici çerçeve belleğini kullanır.

Uyku: yerel sürücü etkinken telefon boşta-uyku kipine alındı ve 25 saniye sonra saat alarmıyla uyandırıldı. Ekran bağlantısı hemen geri geldi ve masaüstü sonrasında saniyede 57 kare çizdi. O sırada ekrana kimse bakmadı.

## İlk donanım denemesi geçti

Yol haritasının 1.1 aşaması, yalnız RAM'de çalışan `native-bl9-05` denemesinde
geçti. DECON ve DSIM bağlandı, EA8061S paneli DCS GET_POWER_MODE komutuna `0x9c`
yanıtını verdi; 120 sayfa değişimi 59,641 Hz'de tamamlandı. DECON yeni fiziksel
`0xbe200000` tamponundan okudu; DSIM 720×1280 çözünürlüğü ve ölçülen yatay/dikey
boşlukları bildirdi; ekran SysMMU çevirisi kapalı kaldı. Watchdog telefonu
kendiliğinden değişmeyen `bl9` BOOT, simpledrm ve Plasma'ya döndürdü. Kanıt ve
yedi kontrol: `build/kernel/display-runtime/runs/native-bl9-05/result.json`.

Son düzeltme `panel.prepare_prev_first = true` oldu: panel komutlarından önce
DSI hostu hazırlanıyor. Kullanıcı bildirmedikçe **fiziksel görünüm görülmedi**.
Bu, günlük gerçek ekran yolu veya masaüstü hız testi değildir. Başarılı bağlantıdan
önce bir ilk PLL zaman aşımı hâlâ kaydediliyor; günlük kullanımdan önce incelenmeli.
Başarılı ölçüm P=3/M=110/S=1 kullanıyor; PLL oranlarını körlemesine değiştirmek için
gerekçe yok. Normal açılış simpledrm kullanıyor. Gerçek kalibre edilmiş parlaklık
ve ekran kapatma/suspend sonraki aşamalardır.
Başlangıç tamamlanınca güvenlik işaretleri kalmadı, GPU/CPU üst sınırları yeniden
1001/1586MHz oldu ve RAM overlay'i yoktu. Telefonda gerçekten çalıştırılan dosyalar
sonucun yanında yerel arşive alındı; SHA değeri sonuç dosyasında kayıtlı.

## Günlük ekran yoluna hazırlık

**Şu an BOOT:** izole `dsimpll2` kuruldu; tüm bölüm okuma doğrulaması
`a2b11f5a…`, çalışan GNU build ID `1950147e…` ve Plasma/simpledrm eşleşiyor.
DTB/initramfs tanılama imajıyla aynı baytlar. Modül/overlay yeniden derlendi;
yeni watchdog provası ve düzeltmenin native donanım doğrulaması artık geçti.
Günlük ekran hâlâ simpledrm. Kanıt:
`build/kernel/dsim-pll-observe/installed-fix3.json`.
Native kanıt: `build/kernel/display-runtime/runs/native-dsimpll2-01/result.json`.
İlk PLL tek denemede zaman aşımı olmadan tamamlandı; yedi native kontrol ve
59.641Hz hızında120 flip geçti, aynı BOOT/build ID/Plasma'ya otomatik dönüldü.
DCS yanıtı bu kez0x1c (temel bitler önceki0x9c ile aynı; bit7 farkı yorumlanmadı).
Başlangıç damgaları temiz, CPU/GPU sınırları1586/1001MHz ve RAM overlay yok.
Aşağıdaki tanılama sonuçları bu kurulumdan öncedir.

`dsimdiag2` BOOT'a tam bölüm geri okumasıyla kuruldu; çalışan GNU build ID ve
Plasma/simpledrm doğrulandı. Kendi watchdog provası ve `native-dsimdiag2-01`
denemesi de geçti: panel yanıtı, 120 değişim/59,641Hz ve otomatik aynı BOOT'a
dönüş. Başlangıç tamamlanınca işaretler temiz, CPU/GPU sınırları1586/1001MHz ve
geçici overlay yoktu. Günlük yol hâlâ simpledrm; fiziksel görünüm görülmedi.

İlk PLL programlamasından önce PLL zaten açık/kilitliydi; tamamlanma kesmesi
gelmedi. Hata temizliği PLL'yi kapattıktan sonraki başlatma hemen tamamlandı.
J701F deneme modunda miras kalan PLL'yi reset öncesinde kapatan küçük düzeltme
hazır. Beş yeni gerçek init testi, toplam29 DSIM testi, paket testleri (biri
atlandı), W=1 ve QEMU kontrolü kurulumdan önce geçti.
İzole `dsimpll2` paketi önceki DTB ve initramfs baytlarını aynen kullanır.
Önceki `dsimpll1`, eklenen etkisiz recovery koşulunu da içerdiği için bu A/B
denemesinde kullanılmayacak; Claude'un kodu değiştirilmedi.

`--prime-probe` iki yolu ölçtü: GPU render-node GBM tamponunu Exynos EINVAL ile
reddetti; ekran GBM üzerinden ayrılan tampon aktarılıp FB nesnesi oluşturuldu.
İkinci yolda ZINK başlatma hatası da var; son renderer henüz bilinmiyor. Tampon
ekrana sürülmedi ve GPU render doğrulanmadı. Bu sonuç IOMMU'nun zorunlu olduğunu
veya kopyasız hızlandırılmış masaüstünü kanıtlamaz. Sonraki ölçüm EGL/GL renderer'ı,
aktarılmış tampona çizimi ve gerçek masaüstü zamanlamasını kapsamalı.

Deneme dosyaları silinmeden `~/j701f/display-runtime/` altına taşındı. Yeni
imajın yükleme yolu `~/j701f/boot-update/dsimpll2`; modüller tekrar sabitlenip
watchdog provası yapılmalı. Telefon klasör düzenlemesi için Claude'a bırakıldı.

İki ek araç `native-dsimpll2-01` içinde **telefonda geçti**.
`native-display-egl.c` her GBM yolundaki gerçek renderer'ı belirler.
`native-display-dmabuf.c`, ekran için ayrılan doğrusal tampona Panfrost ile
çizer; 4096 pikseli GPU okuması ve eşzamanlanmış CPU eşlemesiyle doğrular,
ardından Exynos FB oluşturmayı dener. Bu tampon ekrana verilmez. Başarılı sonuç
ortak tampona GPU çizimini kanıtlar; GPU scanout veya masaüstü FPS kanıtı olmaz.
İsteğe bağlı deneme artık 150 saniye ayırır ve watchdog dönüşünü korur.
27 native-display bilgisayar testi geçti. İki EGL yolu da Panfrost/T830 bildirdi;
GPU ve CPU4096 pikseli doğruladı, Exynos FB oluşturma geçti. Gerçek telefon
dosyaları ve hash'leri sonuç yanında arşivlendi.
Ayrı `pll_initialization` sonucu ilk completion ve register kanıtlarını kontrol
eder; gerçek tanılama başlangıcı sonraki başarılı tekrara rağmen bunu geçemez.
Düzeltilmiş kernel ilk denemesinde geçti. Sonraki eşik süreli native Plasma ve
aynı compositor ölçümü; yol haritası1.2 hâlâ açık.
Eski tanılama yükleme klasörü ancak yeni imaj doğrulandıktan sonra kaldırıldı;
bilgisayardaki imajlar ve kurtarma yedeği duruyor. Telefon sonraki kurtarma
denemesi için sağlıklı biçimde Claude'a bırakıldı; tam BOOT geri yüklemesi istendi.

Salt okunur inceleme gerekli geliştirme başlıklarını ve Mesa26.1.6'yı doğruladı.
Bu sürümün resmî kmsro/Panfrost kaynağı 64 bayt stride hizalamasıyla ekran
tarafından tampon ayırmayı destekler (2880 bayt uygundur). Bu, yolu denemeyi
destekler; kurulu native EGL yolunun bunu kullandığını kanıtlamaz. Kaynak URL
ve özetleri `build/kernel/mesa-native-reference/provenance.json` dosyasında.

## Deneme yöntemi ve önceki girişimler

Onaylı yol haritası, telefonun kendiliğinden çalışan imaja dönmesi şartıyla
izleyici olmadan denemeye izin veriyor. Kullanıcı bildirmedikçe panel görünümü
"görülmedi" olarak kaydedilecek. Codex mevcut çalışan BOOT üzerinde **yalnızca
RAM'de** ilk denemeyi yaptı. `tools/build-display-overlay.py`,
`kernel/dts/j701f-display-runtime.dtso` ağacını ve tek kullanımlık yükleyiciyi
derler. Birleştirilmiş ağaç 21 gerçek ekran yazılım kontrolünden geçer. On iki
bilgisayar testi bağlantı eşdeğerliğini, yalnızca ekran düğümlerinin değişmesini,
RAM rezervasyonlarını ve gözeticinin süre sınırı/hata davranışını denetler.
Yükleyici ve standart DCS güç durumu okuyucusu `W=1` ile derlenir; KMS programı
uyarılar hata sayılarak derlenir. Beş test, yükleyicinin gerçek başlatma yordamını
adres/tanımsız davranış denetleyicileriyle derler: yanlış cihaz/kernel ayarı,
etkin denetleyici, bağlı firmware/MMU, IOMMU özelliğini kaldırma hatası ve kısmi
overlay uygulama hatası sınanır.

Prototip güncel `dsimdiag2` kaydına sabitlendi; ilk başarı `bl9` üzerindeydi. `display-trial-supervisor.py`
watchdog'u açıp besler, sınırlı alt süreci başlatır, ardından **dosya tanıtıcısını
açık tutarak beslemeyi keser**. Gerçek ekran denemesinden önce ekrana dokunmayan
prova, bunun telefonu yeniden başlatıp aynı çalışan imaja döndürdüğünü
kanıtlamalıdır. BOOT ve RECOVERY yazılmaz. Overlay yerinde kaldırılmaz; yeniden
açılış onu siler. Açılışa kurulmadığından kalıcı ekran yolu hâline gelmez.

`native-display-trial.sh`, runlevel ayarını değiştirmeden SDDM'yi durdurur,
simpledrm bağını çözer, DSIM zamanlamasını açar, panel/overlay'i yükler ve gerçek
DRM ana aygıtını yeniden bağlar. Hedef donanım kontrolleri: 120 tamamlanmış sayfa
değiştirme, standart DCS GET_POWER_MODE yanıtı ve sabit salt okunur denetleyici
register'larıdır. Ses, güç alanı sıfırlaması, rastgele DCS komutu veya fabrika
verisi okuması yoktur. Fiziksel görünüm bu kontrollerden ayrı doğrulanır.

İlk gerçek watchdog provası artık `bl9` üzerinde doğrulandı:
`build/kernel/display-runtime/runs/wd-bl9-03/result.json`. Dosya tanıtıcısı açık
kalırken besleme kesildi; telefon kendiliğinden reset atıp değişmeyen BOOT/kernel,
simpledrm ve Plasma'ya döndü. Son kayıt reset öncesi diske yazdırılıyor; ilk
prova da döndü fakat diske yazdırılmayan son satır kayboldu. Denetleyici en az
240 saniye çalışma ve başlangıç işaretlerinin temizlenmesini bekliyor: GPU işi
40 saniye sonra başlıyor, yükseltilen sınırları 180 saniye daha koruyor. İki
regresyon testi erken boş işaret listesini ve kalıcı bekleyen işareti sınar.
Bu, otomatik dönüşü kanıtlar; gerçek scanout veya fiziksel panel görünümünü değil.

İlk gerçek ekran girişimi (`native-bl9-01`) devralmadan önce reddedildi:
SDDM gözeticisi ve Plasma çalışırken OpenRC, SDDM'yi durmuş gösteriyordu.
Deneme artık gerçek SDDM gözeticisini durdurup süreçleri yeniden denetliyor;
açılış/runlevel ayarları değişmiyor. Root'a ait günlükler sudo ile okunuyor;
BusyBox dmesg'de `-w` olmadığından canlı kayıt `/dev/kmsg` üzerinden alınıyor.
Bu reddin ardından otomatik dönüş doğrulandı; panel etkinleştirilmedi.

SDDM kapansa da compositor alt süreçleri kaldı. Deneme artık yerel SDDM Wayland
cgroup'unu ve SSH/watchdog'un bunun dışında olduğunu doğruladıktan sonra kalan
süreçleri kapatıyor; dört geçici dosya testi güvenli olmayan grup seçimlerini
reddediyor. Deneme 03 firmware bağını çözmeye ulaştı ve overlay yükleyici hatasını
buldu: geçerli gömülü DTBO dizisi 8 bayta hizalanmadığından libfdt başlığı
reddediyordu. `__aligned(8)` gerçek modül konumunu `0x1e` yerine `0x20` yapıyor;
`.rodata` hizası da 8. İki test gerçek AArch64 modülünü ve bilgisayardaki libfdt'yi
denetliyor. Bu deneme gerçek modeset olmadan güvenle döndü. Deneme 04 yeniden
derlenen modülü kullanıyor; çalışan kernel Image ve BOOT değişmedi.

Telefondaki hafif salt okunur ön kontrol, çalışan GNU build ID'nin hazırlanmış
`bl9` modülleriyle eşleştiğini ve `keep_on_shutdown=Y` ayarını doğruladı.
Kayıt: `build/kernel/display-runtime/read-only-kernel-preflight.json`.
Bu kontrol watchdog yeniden açılış provası veya gerçek ekran testi değildir.

Laptop denetleyicisi `tools/run-native-display-trial.py`, eksik/süresi dolmak
üzere olan telefon kilidini, eski BOOT/modül derlemesini veya farklı GNU build
ID ile çalışan kerneli reddeder. Mevcut modül başlangıç güvenlik işaretlerinin
temizlenmesini bekler. Gerçek ekran modu aynı BOOT üzerinde başarılı watchdog
provasını gerektirir. Yeniden açılışta değişmeyen BOOT/build ID, simpledrm ve
KWin/plasmashell süreçleri doğrulanır. Deneme, KMS, kernel ve pstore günlükleri
`build/kernel/display-runtime/runs/` altında saklanır. Gerçek ekran başarısı ayrıca
yeni DECON tampon adresini (firmware `0x67000000` değil), 720×1280 DSIM çözünürlüğünü,
ölçülen yatay boşlukları ve kapalı SysMMU çevirisini gerektirir. Altı sonuç/koruma
testi, gerçek eski firmware kaydının, başarısız DCS okumasının, eksik sayfa
değiştirmenin ve yanlış zamanlamanın reddini içerir. Güvenli yeniden açılış tek
başına gerçek ekran başarısı sayılmaz. Bunlar fiziksel panel
görünümünün kanıtı değildir. Telefon Claude'dayken iki mod da çalıştırılmamalıdır.

```sh
python3 tools/run-native-display-trial.py --execute --rehearsal --label wd-01
python3 tools/run-native-display-trial.py --execute --label native-01 \
  --rehearsal-report build/kernel/display-runtime/runs/wd-01/result.json
```

### Geçmiş flash adayı (bl8 öncesi)

Claude ekran bağlantılarını güncel suspend katmanına taşıyıp
`boot-update-displaytrial3` paketini hazırladı; flashlamadı. Codex 24 gerçek
ekran/FIT kontrolünü, Samsung kapsayıcısını, gömülü FIT/loader eşleşmesini,
BOOT denetimini ve öngörülen tam bölüm baytlarını bağımsız yeniden doğruladı.
Paket `bl7` ile birebir aynı kernel Image ve initramfs'i kullanır; gerçek ekran
DTB'si farklıdır. Aday SHA:
`d797482febef7e9b0bcc77672e21a2860841e02ce5baf74ee152ec26dce04106`.
Önceki BOOT denetimi `bl7` (`25ae86fb…`) bekler. Kanıt:
`build/kernel/boot-update-displaytrial3/codex-package-audit.json`.

Deneme firmware framebuffer aygıtını kapattığından yazılımsal parlaklık sürücüsü
burada uygulanmaz. Grafik oturumunun durdurulması, açık DSIM zamanlama seçimi,
panelin elle `allow_init=1` ile yüklenmesi ve sınırlı modeset denemesi gereklidir.
İzleyici yararlıdır; yeni yol haritası bunu önkoşul olmaktan çıkardı.
Gerçek panel parlaklık uygulaması henüz yoktur.
Aşağıdaki eski numaralı paketler geçmiş kayıtlardır; güncel deneme olarak kullanılmamalıdır.

Telefon şu anda Samsung önyükleyicisinin bıraktığı çerçeve belleğini gösteren
`simpledrm` kullanıyor. Masaüstünü Panfrost çiziyor, fakat ekrana sunmak hâlâ
bu çerçeve belleğine kopyalamayı gerektiriyor. Hedef, sayfa değiştirme, dikey
boşluk zamanlaması ve ileride parlaklık ile panel güç denetimi sağlayan gerçek
bir **DECON → MIPI DSI → EA8061S** görüntü yolu.

## İlk panel prototipi

`tools/kmod/ea8061s/panel-j701f-ea8061s.c` içinde deneysel bir panel modülü
hazırlandı. Kurulu Linux 7.1.13 çekirdeği için derleme uyarısı olmadan
derleniyor. Başlatma yordamı, sabitlenmiş Samsung J7VE kaynağındaki 19 statik
komutun tamamıyla eşleşiyor. Bilgisayardaki testler baytları, beklemeleri ve
her aktarımda oluşabilecek hataya verilen yanıtı denetliyor. İkinci bilgisayar
testi, güç/sıfırlama sırasını ve kaynak ya da aktarım hatasından sonra temizliği,
tekrarlanan çevrimlerle birlikte sınar. Adres/tanımsız davranış denetleyicileri
altında dokuz test yordamı geçiyor; bunlar elektriksel davranışı kanıtlamaz.

Yukarıdaki denemede geçici yüklenip donanımda sınandı. Açıkça `allow_init=1` verilmesini
gerektiriyor, etkin aygıt ağacında düğümü yok ve yalnızca üreticinin sabit ilk
gamma değerlerini kullanıyor. Kalibre edilmiş parlaklık henüz uygulanmadı.

`tools/build-display-prototype.py`, ortak `kbuild` kilidini ve sabitlenmiş
yapılandırmayı denetledikten sonra modülleri yeniden derler. Bilinen ekran
yazmaçlarını okumak için ayrı bir salt okunur `j701f-display-info` modülü
hazırlandı; açılışta yüklenmiyor. `tools/capture-display-state.py` bu tanı
modülünü geçici yükleyip kaldırıldığını doğruladı. Çalışan ekran SysMMU'sunda
CTRL=0 ve STATUS=0 ölçüldü: adres çevirisi kapalıydı ve DECON fiziksel
`0x67000000` çerçeve belleğinden okuyordu. DSIM PLL alanları P=3, M=220, S=2
ile eşleşti. Ekran, saat veya MMU yazmaçlarına yazılmadı. Bağlantı adayı
`kernel/dts/exynos7870-j7velte-display-prepared.dts` derleniyor; görüntü bağlantı
ağı, beslemeler ve sıfırlama çözümleniyor, tüm ekran denetleyicileri kapalı kalıyor.

Ölçülen zamanlama, dört RGB888 DSI hattıyla nominal 60 Hz'de 720 × 1280.
Yatay arka/ön/senkron 48/56/4; dikey arka/ön/senkron 5/9/2.
Sıfırlama gpd3-4, beslemeler LDO30 (1,8 V) ve LDO29 (3,0 V).

## Kalan işler

İlk ayrı ekran denemesi, yukarıda ölçülen fiziksel DMA ve kapalı ekran
SysMMU'sunu koruyabilir. Saat istekleri ve simpledrm'den devralma hâlâ
bütünleştirilmeli; ölçüm farklı sıfırlama veya açılış imajından sonraki durumu
kanıtlamaz. Ekran, güç alanını sesle paylaşıyor; bu
yüzden tüm alanı yeniden başlatmak uygun değil. İlk donanım denemesinde
kullanıcı bildirmedikçe görünüm "görülmedi" kaydedilir; başarılı derleme görünür
görüntüyü kanıtlamıyor.

Etkinleştirmeden önce kaynak düzeyindeki testler başka bir fark buldu: ortak
DSI yordamı, çalışan firmware'in 56/48/4 yatay zamanlama değerleri yerine
46/39/0 yazacaktı. Derlenen `linux-dsim-j701f-timing-trial.patch`, hem yatay hem
dikey alanları eşleştiren, varsayılan olarak kapalı ve J701F'ye özel bir deneme
profili ekliyor. Altı bilgisayar testi profili ve sınırlarını doğruluyor. Panel
yüklenmeden önce, gerçek ekran oturumu kapalıyken root parametresi açıkça
etkinleştirilmeli. Ayrı sınanan mevcut PLL araması daha düşük VCO ile aynı
476,667 MHz çıkışı seçiyor; sınırlar değiştirilmedi. Hat kararlılığı donanımda
sınanmalı.

Ayrı ve kesin bir yazılım hatası da
`kernel/patches/linux-dsim-pll-wait-fix.patch` ile düzeltildi: PLL tamamlanması
ters yorumlanıyor, ilgili kesme maskeleniyor ve birleşik kesme olayları
kaybolabiliyordu. Gerçek C yordamlarını sınayan altı bilgisayar testi ve tam
AArch64 çekirdek derlemesi geçti. Claude'un sonraki `pfshrink2` paketi bu PLL
düzeltmesini içeriyor. Gelecekteki gerçek ekran yolunu etkiler; bugünkü simpledrm yolunda
siyah alanları açıklamaz. Gerçek PLL kilidi ve panel görüntüsü donanımda sınanmalı.

`linux-dsim-init-errors.patch`, saat/hat hatalarının veya sıfırlama zaman aşımının
yok sayılmasını da önlüyor; dört bilgisayar testi temizliği ve yeniden denemeyi
kapsıyor. Ayrı `display-trial.dts`, ayrılmış RAM ve ramoops'u koruyarak gerçek
denetleyicileri açıyor ve simple-framebuffer aygıtını kapatıyor. Sıkı
`tools/validate-display-trial.py` bu kaynakları ve derlenen çekirdek/modül
özetlerini denetliyor. Kayıtlı `pfshrink4` BOOT paketi üç DSIM değişikliğini de
içeriyor fakat gerçek ekran denetleyicileri kapalı. Yazılım denetiminden geçen
bir deneme, doğrulanmış günlük kullanım ekranı anlamına gelmiyor.

Bilgisayarda `displaytrial1` BOOT paketi hazırlandı: 132 proje testi çalıştı
(biri atlandı), QEMU Linux girişine ulaştı ve 20 gerçek ekran yazılım denetimi
geçti. Bilerek bozulan dört DTB reddedildi. Telefona flashlama, görünür görüntü
veya performans artışı iddiası yok. Ayrıntılar ve özetler
`build/kernel/boot-update-displaytrial1/display-trial-summary.json` içinde.
Claude daha sonra BOOT kaydını `pfshrink3` olarak güncelledi. Deneme, ayrı ekran
aygıt ağacıyla bu paketin aynı kernel ve initramfs'ini kullanıyor. Güncelleme
denetimi, kayıtlı tam bölüm imajına (`fe691403…`) göre yenilendi. Yeniden açılışın
ardından SSH erişilebilirdi. Başka imaj kurulursa bölüm kaydı yeniden denetlenmeli;
gerçek ekran denemesi hâlâ flashlanmadı.

Çalışma notları ve kanıt yolları depodaki `docs/j701f-display.md` içinde.
Bilgisayarda komut dizisini sınamak için:

```sh
python3 -m unittest discover -s tests -p 'test_ea8061s_*.py' -v
```

Ekran performansı ve tarayıcıdaki siyah alanlar ayrı ölçülmeli. Angelfish bellek
baskısı altında açılırken Panfrost tampon temizleme uyarıları kaydedildi;
yalnızca ekran sürücüsü bunlar için kanıtlanmış bir çözüm değil.

Sonraki DECON incelemesi, ortak Exynos7 koduyla Samsung'un 7870 başlığı arasında
bölücü alanı farkı buldu. SoC'ye özel düzeltme ayrı tutuluyor; gerçek C kodunu
sınayan altı test geçti. Kernel derleme girdilerine veya deneme imajına
eklenmedi. Saat altyapısı şu an 64 MHz bildiriyor ve bire bölme seçildiğinden
ilgili yazma atlanıyor. Bu, bugünkü yavaşlığın kanıtı değil, ilerideki
bütünleştirmeyi etkileyebilecek bir fark. Üçlü tamponun 18. biti de donanımla
karşılaştırılmalı: üretici başlığında adı bulunmaması tek başına hata kanıtlamaz.
Ayrıntılı kapsam çalışma notlarında.

[Yerel tarayıcı testi](scroll-benchmark.md), sonraki karşılaştırmalar için sabit
ve sessiz bir sahne sunuyor. Masaüstü kontrolleri telefon hızını ölçmez.

Son GPU sürümü ilk deneme paketinin yerini aldı. `displaytrial1` geçmiş bir
kontrol noktası olarak saklanıyor; eski BOOT denetimi yeni bölümü reddeder.
Yeni FIT yükü (`handoff-displaytrial2`), `pfshrink4` Image'ını
kullanıyor. Modül derleyici artık Image ve sembol sürümü hash'lerini kaydeder.
`--handoff-dir` ile doğrulama, yalnızca raporu değil gerçek sıkıştırılmış FIT
yüklerini denetler: 24 kontrol geçti, üç olumsuz durumda eski/bozuk yükler
reddedildi. Tamamlanan Samsung BOOT paketi `boot-update-displaytrial2` altında:
QEMU Linux'un ilk komutuna ulaşıyor, 146 test geçiyor (biri atlandı). Paket
kurulmadı; donanım görüntüsü veya performansı doğrulanmadı. Güncelleme denetimi
kayıtlı `pfshrink4` bölümünü bekler; kullanımdan önce kimliği tekrar denetleyin.
