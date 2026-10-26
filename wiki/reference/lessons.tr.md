# Dersler ve tuzaklar

Zamana mal olan şeylerin listesi; ikinci kez mal olmasınlar diye. Her girdi ne görüldüğünü, nedenin ne olduğunu ve ne yapılacağını söyler.

## Yöntem

**İmaj başına tek şey değiştir.** Sorunsuz geçen her kademe tek bir şeyi değiştirdi. Birkaç yeni gömülü sürücüyü birleştiren tek imaj, hangi parçanın sorumlu olduğunu söylemenin yolu olmayan bir açılış döngüsü üretti.

**Başarı kodu sonuç değildir.** Çizim çağrıları siyah bir ekranla başarı döndürdü. Bir ton sessiz bir hoparlöre "hatasız çalındı". Bir başarım ölçümü karartılmış bir ekrana karşı çalıştı. Gerçek gözlenebilir şeyin ne olduğuna karar verin — pikseller, ses, donanımdan geri okunan bir sayı — ve onu denetleyin.

**Tahmin etmeden önce üretici sistemini ölç.** CPU gerilimleri, GPU kademeleri, USB anahtarı yazmaçları, ses PLL frekansı: hepsi üretici çekirdeği çalışırken telefondan okundu. Değerlerin varsayıldığı yerlerde çoğunlukla yanlış çıktılar.

**Başarısızlıkları sakla.** `kernel/rejected-trials.json` ve `docs/j701f-mainline.md` içindeki olay notları aynı çıkmaz sokağı birden fazla kez önledi.

**Yeni ve riskli olan "varsayılan olarak kapalı"dır.** Frekans sınırları önyükleyicinin değerlerinde başlar; ses sürücüleri açılıştan sonra yüklenen modüllerdir. O zaman bir takılma, döngü yerine çalışan bir sisteme sıfırlanmayla sonuçlanır.

## Açılış ve yazma

| Görülen | Neden | Yapılacak |
| --- | --- | --- |
| Kök dosya sisteminin Odin yüklemesi reddedildi | Samsung'un sparse imaj biçimi Android'in genel biçiminden farklı | Üreticinin parça biçimini üret; önce bir üretici imajıyla karşılaştır |
| Açılış döngüsü: logo, yazılar, yeniden başlama | Erken açılışta çöken gömülü bir sürücü; watchdog aynı çekirdeğe yeniden başlatıyor | Power + Home + Ses Açma'yı basılı tut, önceki imajı geri yaz. Yeni sürücüleri modül olarak derle |
| Hazırlanmış bir güncelleme çalışmayı reddediyor | `BOOT`'ta orada olandan farklı bir imaj bekliyor | `prepare-boot-update.py`'yi yeniden çalıştır |
| U-Boot bağlama "Error 135" ile başarısız | Bilgisayarın `/tmp`'si (RAM diski) eski derleme dizinleriyle dolu | `/tmp/j701f-uboot-embedded-source/out-uboot-j701f-*` dizinlerini sil |
| Her açılışta "mounting fs with errors" | Sert sıfırlamalar yarı silinmiş dosyalar bıraktı; güvenli `e2fsck -p` düzeltmeyi reddediyor | `/etc/j701f-fsck-mode` dosyası `-fn` iken bir açılışla raporu oku, sonra `-fy` ile onar, sonra dosyayı sil |
| Sıradan bir yeniden başlatmadan sonra GPU 343 MHz'de takılı | Sıfırlama koruması hızlı bir yeniden başlatmayı çökme sandı | `j701f-stamps.stop` ile düzeltildi; aksi halde damga dosyasını sil |

## Çekirdek ve aygıt ağacı

| Görülen | Neden | Yapılacak |
| --- | --- | --- |
| Mainline'da USB aygıtı yok | Yonga seti ile bağlayıcı arasındaki MUIC anahtarı açık | initramfs'ten iki I²C yazmaç yazımı |
| Wi-Fi yongası yanıt vermiyor | Eklenen bir pin yapılandırması güç-etkinleştirme hattını düşük tuttu | Gerekçelendiremediğin pin ayarını ekleme |
| Dokunmatik tek kesme veriyor, sonra hiçbir şey | Seviye ile sinyal veren yongada kenar tetiklemeli kesme | Düşük seviye kullan |
| Dokunmatik aygıt masaüstünce yok sayılıyor | Bir eksen sıfır çözünürlük bildirdi | Sürücüyü, dolduracak şekilde yamala |
| eMMC `mmcblk1` oldu | İkinci bir MMC denetleyicisi açıldı | `mmc0`/`mmc1` takma adları ekle |
| Çekirdek imajı fazlasıyla büyük | Her yonga ailesi açık | Exynos dışındaki tüm `ARCH_*` seçeneklerini kapat |
| I²S akışı açılıyor, her yazma G/Ç hatası veriyor | Yanlış yazmaç düzeni türü; denetleyici hiç saat üretmiyor | Bu yonga seti eski "v5" düzenini kullanır: `samsung,s5pv210-i2s` |
| eMMC HS200'de: kart açılıyor, sonra her yazma başarısız | Mainline'da bu yonga setinin hıza göre pin sürüş güçleri ve ince ayarı yok | DDR52'de kal. Bir depolama zamanlama kipini asla yazılabilir bağlı kökte sınama; önce initramfs'ten sına |
| Saat istenen hızın 4/5'inde kalıyor | Bölücüden, üst saatinin verebileceğinden biraz azını istemek | Üreticinin yaptığı gibi biraz fazlasını iste |
| Ses PLL hızı imkânsız görünüyor | Tamsayı PLL olarak tarif edilmiş; kesirli | Önyükleyicinin bıraktığı hızla karşılaştır |
| Kodek adresi reddediliyor | `0x04` ayrılmış bir 7 bit adres | Aygıt ağacında on bitlik adres olarak işaretle |
| Hoparlör tıklıyor ama ton yok | Analog yol sağlam, sayısal ses kodeğe ulaşmıyor | Pin işlevlerini, ana saat yönlendirmesini, mikserin kanal etkinleştirmesini denetle |
| Denetimler çalmadan sonra kendiliğinden kapanıyor | Bir güç sırası ile bir kullanıcı denetimi yazmaç bitlerini paylaşıyor | Bir sıranın sahip olduğu bitleri denetim olarak sunma |
| Ses tuşlarının etkisi yok | Desibel ölçeği olmayan ses denetimi | Ölçeği ekle |
| Aygıt ağacındaki Bluetooth adresi yok sayılıyor | Yama yazılımı yüklendikten sonra yonga, çekirdeğin "ayarlanmamış" olarak tanımadığı bir varsayılan adres bildiriyor | O adresi sürücünün varsayılanlar listesine ekle |
| Donanımsal video çözücü: yazmaçlar çalışıyor, yazılım hiç başlamıyor, kesme yok | Çözücünün önündeki SysMMU sıfırlamadan geçirgen değil, "etkin ve engelli" çıkıyor | Çözücüyü başlatmadan önce onu geçirgen kipe al (ya da düzgün sür). Bir SysMMU'nun geçirgen olduğunu varsaymadan önce denetim ve durum yazmaçlarına bak |
| Donanım çözücü 720p'de çalışıyor ama küçük videolarda başarısız | IOMMU olmadan tüm tamponlar çözücünün yazılımının üstünde olmalı; küçük tamponlar altına ayrılıyordu | Çözücüye kendi bellek bölgesini ver; böylece yazılım en alttaki ayırma olur |
| Fabrika ayar değerleri sıfır okunuyor | Yazmaçlar sıcak yeniden başlatmada değerini koruyor ve üzerine yazılmıştı | Boştayken fabrika değerlerini geri yaz |

## Canlı telefonda hata ayıklama

| Görülen | Neden | Yapılacak |
| --- | --- | --- |
| debugfs'te bir regmap `registers` dosyasını okumak okuyanı çekirdek hatasıyla öldürüyor; sonraki yeniden başlatma takılıyor | Döküm bloğun her yazmacına dokunur; bazı PMU yazmaçları hata verir ve kilit tutulu kalır | Bir MMIO regmap'in tamamını asla dökme. Tek tek, bilinen yazmaçları oku |
| `reboot`'tan sonra telefon ekranı açık halde donmuş | Watchdog kapanış için durdurulduktan sonraki bir takılma | On saniye Ses Kısma + Power |

| Güç alanı elle kapatılıp açıldıktan sonra video çözücü takılıyor | Alan, çözücünün saat denetleyicisini de barındırıyor; çıplak bir yazmaç yazımı onu çekirdeğin haberi olmadan sıfırlıyor | İçindeki hiçbir şey kullanılmıyorsa dışında bir alana dokunma; kullanılan bir alan gerçek bir sürücü ister |

## Masaüstü

| Görülen | Neden | Yapılacak |
| --- | --- | --- |
| Plasma logosundan sonra siyah ekran | Oturum yöneticisi Xwayland istiyor | Kur; `/tmp/.X11-unix` oluştur |
| Kısa güç tuşu basışında telefon "yeniden başlıyor" | elogind'in varsayılan eylemi | Güç tuşunu "yok say"a ayarla |
| Firefox penceresi siyah ya da yarım çizilmiş | Bu GPU ailesinde Mesa gölgelendirici derleyicisi hatası | Firefox için yazılımsal çizim; GPU çizimi için Angelfish |
| Firefox'ta bir video hiç başlamıyor | `/tmp` 16 MB'tı ve doldu | `/tmp` artık 256 MB |
| Ekran görüntüleri bozuk PNG dosyası olarak çıkıyor | Ekran ölçeği değişti; yakalama artık 720 × 1280 değil | Yakalama aracının bildirdiği boyutu kullan |
| Tarayıcıda siyah alanlar; `panfrost_gem_open` içinde çekirdek uyarıları | Çekirdek, Mesa'nın atılabilir işaretlediği GPU tamponlarını atıyor; tarayıcının öteki iş parçacığının hâlâ içe aktardıkları dahil | Yerel Panfrost ayarı `shrinker_purge=2`; bkz. [başarım](performance.md) |
| "GPU tamponlarını hiç atma" ayarından sonra ana ekran açılmadı | Masaüstü açılışta bir anlığına 1,2 GB'a kadar GPU tamponu ayırıyor; geri alınabilecek hiçbir şey olmayınca bir ayırma başarısız oldu | Bir belirtiyi gidermek için önbelleği asla kilitlemeyin: önce ne tuttuğunu ölçün (`/proc/PID/fdinfo` program başına GPU belleğini gösterir) |
| Bir uygulama arka planda beş dakika kaldıktan sonra "takılıyor" | Arka plan dondurucusu tarafından bilerek durduruldu | Etkinleştirilince devam eder; hariç tutma listesi ve kapatma anahtarı `~/.config/j701f-freezer.conf` içinde |
| Parlaklık kısılınca ekrandaki her şey yarı kare hızında çalışıyor | Arka ışık aygıtı olmayınca bileşikleyici resmi fazladan bir çizim geçişiyle karartıyor | Ona bir arka ışık aygıtı verin; çekirdeğin kare kopyasında uygulanan yazılımsal bir aygıt bile olur. Plasma'nın bunu kullanması için `polkit` çalışmalı ve bağlayıcı türü "yerleşik" olmalı ([ayrıntılar](performance.md#kare-hz-ekran-yolu)) |
| Bir grafik sınaması hiçbir şey bildirmiyor ya da her çalıştırmada çok farklı sayılar veriyor | Kilit ekranı açıktı (uygulamalar gizli) ya da ekran kararmıştı | Her ölçümden önce kilidi açın ve kullanıcı etkinliği benzetin |
| Bir GTK 4 uygulaması siyah alanlar gösteriyor | GTK'nin GL çizicisi varsayılan iyileştirmeleriyle Panfrost/Mali-T830'da doğru çizmiyor | `GSK_RENDERER=gl GSK_GPU_DISABLE=all` (yazılımsal çizici `cairo` da çalışır ama yavaştır) |
| Öldürülen bir komut SSH oturumunu da götürdü | `pkill -f AD`, onu çalıştıran kabukla da eşleşti | Yalnızca hedefte bulunan bir yolla eşleştir |

## Uzaktan çalışmak

- Herhangi bir ekran görüntüsünden ya da grafik sınamasından önce ekranı uyandır.
- Yapıştırılması amaçlanan komutlara yer tutucu koyma; oldukları gibi yapıştırılırlar.
- Telefonun sahibi uzaktayken, Download Mode gerektirebilecek her şey bekler.
- Bazı şeyler uzaktan hiç doğrulanamaz: ses, fiziksel tuşlar, bir şeyin nasıl hissettirdiği. Bunu açıkça söyle ve sor.

## İyi bir sayı, hiçbir şey olmadığı anlamına gelebilir

Donanımsal video çözücüyle VLC bir işlemci çekirdeğinin üçte birini kullandı ve geciken kare bildirmedi. Aynı anda siyah bir pencere gösteriyordu: çözücü tek bir resim verip durmuştu. Ölçüm, ayarın çalıştığının kanıtı sayıldı ve telefon sahibi bakana kadar kimse ekrana bakmadı. O günden beri bir video denemesi, oynatma sırasında çerçeve belleğinin dökümünü ve siyah olmayan piksellerin sayımını da içeriyor.

## Çalışan masaüstünü ölçmek için yeniden düzenleme

KWin'in bulanıklık efektinin kare kaybettirip kaybettirmediğini görmek için efekt çalışan oturumda yüklenip kaldırıldı. Masaüstü kabuğu o efektlerin sağladığı Wayland arayüzlerini kullanıyordu; bağlantısını protokol hatasıyla yitirdi ve kapandı. Elle yeniden başlatılana kadar telefon kabuksuz bir oturum gösterdi. Böyle ayarlar oturumun içinde değil, oturum yeniden başlatılarak karşılaştırılmalı.

## Sessizce devrede kalan bir güvenlik ağı başlı başına bir arızadır

Açılıştan sonra GPU ve işlemci hız sınırlarının yükseltilmesi bir işaret dosyasıyla korunur: işaret varken telefon sıfırlanırsa, sonraki açılış sınırları düşük bırakır. Eskiden bundan sonraki her açılışta, biri dosyayı silene kadar düşük bırakıyordu - ve bunu hiçbir şey haber vermiyordu. Yanlış anda yapılan tek bir bilinçli yeniden başlatma, telefonu bir oturum boyunca GPU hızının üçte birinde bıraktı; o sırada birkaç ölçüm alındı ve ana ekran yavaş bulundu. Bir koruma yalnızca bir açılışa mal olmalı, sonra yeniden denemeli ve devreye girdiği görünür olmalı.

## Kimsenin sorgulamadığı bir sayı

Pil yüzdesi, pil ölçer sürücüsü ilk yüklendiğinden beri "çalışıyor" diye listeleniyordu: bir sayı gösteriyordu, sayı da değişiyordu. 2026-10-13'te, şarj devresinin dolu dediği bir pilde %43 okudu. Yonga yükü sayar ve biri onu doluya ve boşa yakınken düzeltmezse kayar; üretici çekirdeği bunu yapar, ana hat sürücü yapmaz - yani sayı baştan beri bilinmeyen bir miktarda yanlıştı. Onu yakalayan, birbirini tutması gereken iki şeyi (yüzde ile hücre gerilimini) karşılaştırmak oldu; `tools/phone-health.sh` artık her çalıştığında bu karşılaştırmayı yapıyor. Yalnızca var olan bir değer sınanmış sayılmaz.

## Aynı düzeltme ikinci düzenlemeden sağ çıkmaz

`tools/build-kernel.py` her yerel yamayı bir kez uygular ve bunu kaydeder. Bir yama sonradan düzenlendiğinde araç yeni sürümü eskisinin üstüne uygulamaya çalışıyor, başarısız oluyordu; bunun üzerine değişen dosyayı çalışma ağacına elle kopyalama alışkanlığı oluştu - ağaç sıfırdan kurulana ve elle taşınan durum yok olana dek işe yarayan bir alışkanlık. Araç artık uyguladığının bir kopyasını saklıyor ve önce eski sürümü geri alıyor. Bir araç doğru yolu kestirmeden daha zor kılıyorsa, düzeltilmesi gereken araçtır.

## Yeniden karşılaşılan küçük tuzaklar

- Süreçleri kalıba göre öldüren bir komut (`pkill -f`), kalıp kendi içinde geçiyorsa komutu taşıyan kabuğu da yakalar: oturum, başka hiçbir şey çalışmadan sessizce biter. Böyle şeyleri betik dosyası olarak gönderin.
- Bilgisayarın araç kabuğu değişti (fish oldu) ve seçenekleri bir değişkende taşıyan komut tek sözcük olarak çalıştı: hiçbir şey olmadı, hiçbir şey de yakınmadı. Çok adımlı komutlar bir `bash` betiğinden geçer.
- Bir modülden çekirdeğe verilen aygıt ağacı eklentisi sekiz bayta hizalanmış olmalıdır (yoksa "Invalid overlay_fdt header").
- Çıkış işlevi olmayan bir modül yeniden başlatmadan değiştirilemez; geliştirirken deneme kopyalarını başka adla yükleyin.
