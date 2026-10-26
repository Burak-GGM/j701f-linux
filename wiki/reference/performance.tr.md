# Başarım ve ince ayar

Kritik sürücülerden sonra ana hedef, telefonun kullanılabilir *hissettirmesi*. Bu sayfa neyin ölçüldüğünü, neyin değiştirildiğini ve her değişikliğin ne kazandırdığını kaydeder. Sayılar telefonun kendisinden; ölçülmeyen şeyler için öyle yazıyor.

## Zaman nereye gidiyor

| Ölçüm (2026-10-10) | Sonuç |
| --- | --- |
| Angelfish, soğuk önbellek, geri yüklenen altı sekme: başlatma → web görünümü hazır | 10,2 sn |
| Aynısı, geri yüklenen iki sekmeyle | 7,5–7,9 sn |
| Aynısı, sıcak önbellekle | 5,8 sn |
| Ayarlar uygulaması: başlatmadan sonra meşgul kalma (sıcak, kaba) | yaklaşık 7 sn |
| Terminal (foot): başlatmadan sonra meşgul kalma | yaklaşık 1 sn |
| Bir uygulama açılırken CPU frekansı | neredeyse baştan sona 1586 MHz'lik üst sınırda |
| Web sayfası kaydırılırken GPU | az yüklü (tam parlaklıkta yaklaşık dörtte bir meşgul); sonraki bölüme bakın |

Bir tarayıcı açılışının sistem genelindeki profili (`perf`), açılışın düpedüz "işlemciye bağlı" olduğu yolundaki ilk izlenimi düzeltti. İşlemci gerçekten tam frekansta çalışıyor, ama ortalamada sekiz çekirdeğin yalnızca bir buçuğu kadarı meşgul: açılış, tek iş parçacıklı adımlardan oluşan bir zincir; önbellekler soğukken buna depolamayı beklemek ekleniyor. Sıcak bir açılışın 5,4 saniyesi şuralara gidiyor:

| Adım | Süre |
| --- | --- |
| Programı yüklemek ve kitaplıklarını bağlamak (tarayıcı motoru tek başına 172 MiB'lik bir kitaplık) | 1,4 sn |
| Tarayıcı motorunu ve GPU sürecini başlatmak | 1,0 sn |
| Kullanıcı arayüzünü (QML) yüklemek | 0,9 sn |
| Reklam engelleme listelerini yüklemek | 1,2 sn |
| İlk web görünümünü oluşturmak | 0,8 sn |
| Geri yüklenen her ek sekme | yaklaşık 0,25 sn |

Bundan iki sonuç çıkıyor:

- **Soğuk ile sıcak arasındaki fark 1,6 saniye** ve tamamı dosya okumak. Artık bir açılış betiği, açılıştan 75 saniye sonra tarayıcı motorunu sayfa önbelleğine okuyor (arka planda 2,4 saniyelik okuma); böylece açılıştan sonraki ilk başlatma da sıcak oluyor.
- Hiçbir adım tek başına baskın değil; yani süreyi yarıya indirecek ucuz bir numara kalmadı. Daha hızlı bir bellek ayırıcı (önyüklenen mimalloc) denendi: uygulama başına 50 MB fazla bellek karşılığında 0,4 sn kazanç; benimsenmedi. Etkili yanıt, uygulamaları hiç başlatmamak: açık bırakmak ve [arka plan dondurucusunun](#arka-plandaki-uygulamalar) onların bir şeye mal olmasını engellemesine izin vermek.

Tarayıcının geri yüklediği sekmeleri azaltmak da yardımcı oluyor (ilk ölçümler altı sekmeyle alınmıştı).

**Açılış süresi, ilgisiz görünen şeylere duyarlı.** Aynı ölçümü gecenin her imajında (üçer kez) yinelemek iki basamak gösterdi: erken imajlarda 5,9–6,0 sn, hızlı ekran yolu geldikten sonra 6,6–6,7 sn, tuşlar da uyandırma kaynağıyken 7,0–7,3 sn. Son basamak geri alındı. Ortadaki, şimdiki durum: tarayıcı ilk görünümünü, ekran saniyede 38 kareyle çizilirken olduğundan yaklaşık 0,7 sn daha geç gösteriyor. İşlemcinin, belleğin ve süreç başlatmanın ham hızı bu imajların hepsinde aynı; yani bu, uygulama ile hızlanan bileşikleyicinin etkileşiminde bir şey ve nedeni bulunmadı.

**İşe yarayan:** Qt Quick'e ayrı bir çizim iş parçacığı yerine uygulamanın ana iş parçacığından çizmesini söylemek (`QSG_RENDER_LOOP=basic`). Üçer açılış: varsayılanla 6,0–6,3 sn, `basic` ile 5,5 sn; kaydırma sınaması değişmedi (saniyede 52,7'ye karşı 52,3 geri çağrı). Pencere kilit ekranının arkasında gizliyken açılış 5,7–6,0 sn sürüyor; yani olağan bir açılışın yaklaşık yarım saniyesi henüz kimsenin ihtiyaç duymadığı kareleri çizmeye gidiyor. Ayar yalnızca Angelfish'e, başlatıcısının `~/.local/share/applications/` altındaki bir kopyasıyla uygulanıyor; ana ekranda ve öteki uygulamalarda denenmedi.

## Kare hızı: ekran yolu

Ekranın ne kadar akıcı hissettirdiğini GPU değil, bileşikleyiciden (KWin) panele giden yol belirliyor. Henüz gerçek bir ekran sürücüsü yok; bu yüzden KWin her kare için GPU'da çiziyor, resmi geri okuyor ve çekirdek onu dönüştürüp önyükleyicinin çerçeve belleğine kopyalıyor.

| Ölçüm (2026-10-10) | Sonuç |
| --- | --- |
| GPU tek başına, ekrana vermeden küçük bir sınama sahnesi çizerken | saniyede yaklaşık 3460 kare |
| Aynı türden sahne KWin üzerinden, tam ekran | saniyede 38 kare |
| …aşağıdaki aygıt ağacı değişikliğinden sonra | 44 |
| …çekirdekteki daha hızlı kopya yordamıyla (şimdiki durum) | 49,5 |
| …şimdiki durum, ekrana dokunulurken (frekans tabanı yükseltilmiş) | 54 |
| …NEON kopya döngüleri ve ekran açıkken 902 MHz tabanıyla (güncel), tam parlaklık / kısık | 55 / 51 |
| KWin'in kare başına kendi çizim süresi | 3 ms |
| Çizimin bitmesinden karenin çerçeve belleğine ulaşmasına kadar | 25–50 ms |
| Angelfish'te bir sınama sayfasını kaydırma (saniyedeki tarayıcı geri çağrısı, ortanca aralık) | saniyede 45, 16,7 ms |
| Aynısı %50 parlaklıkta, aşağıdaki arka ışık düzeltmesinden önce | saniyede 18, 50 ms |

Bundan çıkanlar:

- **Parlaklık eskiden kare hızını yarıya indiriyordu; bu düzeltildi.** Arka ışık denetimi olmadığından KWin resmi fazladan ve pahalı bir çizim geçişiyle kendisi karartıyordu (%100'ün altındaki her parlaklıkta ve ekran boşta karardığında saniyede 42 → 20 kare). Artık çekirdek bir arka ışık aygıtı sunuyor, `/sys/class/backlight/j701f-panel`, ve düzeyini kare zaten kopyalanırken her piksele uyguluyor. Plasma onu gerçek bir arka ışık gibi kullanıyor. İlk sürüm saniyede 49 kareyi yalnızca birkaç saniye tutuyor, sonra kullanıcının %89 ayarında 32'ye oturuyordu; kopya döngüleri NEON ile yeniden yazılınca %100'de sabit 55, daha düşük her ayarda 51 oldu. Çekirdek yamasının yanında iki şey daha gerekti: ekran bağlayıcısı artık DSI olarak bildiriliyor, böylece Plasma ekranı yerleşik panel sayıyor; ve `polkit` hizmeti kuruldu, onsuz Plasma'nın arka ışık yardımcısı düzeyi yazamıyor. (Önce KWin'e bir gama tablosu sunmak denendi ve işe yaramadı; KWin parlaklık için tablo kullanmıyor.)
- **Çerçeve belleği kopyası gereksiz yere yavaştı.** Çekirdek çerçeve belleğini aygıt belleği sayıyor ve ona yavaş bir erişim yoluyla yazıyordu. Aygıt ağacında ayrılmış bellek bölgesini adıyla göstermek (`memory-region`) sıradan bellek erişimini kullandırıyor: kare başına 26,5 → 23 ms. Pikseller, çerçeve belleği geri okunup bir ekran görüntüsüyle karşılaştırılarak denetlendi. Ardından yerel bir çekirdek yaması dönüştürme yordamının kendisini değiştirdi (64 bitlik işlem başına iki piksel, ara tampon yok): saniyede 44 → 49,5 kare. Bu belleği önbellekli eşlemek de denendi ve bir şey kazandırmadı; o yama başvuru için `kernel/patches/staged/` altında duruyor.
- **İşlemci frekans yöneticisi bu hattı yavaşlatıyor.** Bir kareyi çizmek, birkaç iş parçacığına dağılmış çok sayıda kısa adımdan oluşuyor; hiçbiri meşgul görünmediği için yönetici frekansı düşük bırakıyor. Küçük bir hizmet (`j701f-inputboost`), ekrana dokunulurken ve sonraki 3 saniye boyunca frekans tabanını 1144 MHz'e çıkarıyor; ekran açık olduğu sürece taban 902 MHz (kapalıyken 546 MHz): dokunmadan saniyede 49,5 → 52–53 kare, dokunurken 54.
- **Tarayıcı anahtarları kaydırmayı değiştirmiyor.** GPU rasterleştirme açıkken, kapalıyken ya da hiç anahtar yokken kaydırma sınaması aynı saniyede 45 sonucunu verdi.
- 60'a kalan fark gerçek ekran sürücüsünü gerektiriyor; orada GPU'nun resmi hiç kopyalanmadan panele gider.

Bunu ölçerken iki tuzak: kilit ekranı bütün uygulamaları gizler (gizli bir sınama hiçbir şey çizmez ve hiçbir şey bildirmez) ve Angelfish'e komut satırından verilen bir web adresi, geri yüklenen sekmelerin arkasında bir arka plan sekmesinde açılır.

## Tarayıcıdaki siyah alanlar

Belirti: Angelfish'te kaydırırken siyah dikdörtgenler. Tarayıcı bellek baskısı altında çalışırken çekirdek günlüğünde görülen: art arda Panfrost "Purging …" satırları ve `WARNING … panfrost_gem_open`.

Kanıtların gösterdiği kadarıyla düzenek şöyle:

- Mesa, yeni serbest bırakılan GPU tamponlarını bir önbellekte tutar ve çekirdeğe, bellek azaldığında bunların atılabileceğini ("purge") söyler.
- Uyarının çağrı izi, tarayıcının iki çizim iş parçacığının (`Chrome_InProcGpu` ve `QSGRenderThread`) birbirinden tam da bu atılabilir durumdaki tamponları içe aktardığını gösteriyor.
- Öteki iş parçacığı hâlâ gösterirken atılan bir tamponun artık içeriği yoktur.

Bu, çalışılan açıklamadır, **kanıtlanmış değildir**: otomatik ekran yakalamaları, değişiklikle de değişikliksiz de hiç siyah alan yakalamadı; dolayısıyla bunu ancak tarayıcının kullanılması doğrulayabilir.

Çözüm, bir ayar ekleyen küçük bir yerel çekirdek yaması: `/sys/module/panfrost/parameters/shrinker_purge`

| Değer | Davranış | Bu telefondaki sonuç |
| --- | --- | --- |
| `1` | Özgün davranış: atılabilir işaretli her şeyi at | Tarayıcı çalıştırması başına 3–7 uyarı |
| `0` | Hiç atma | İlk denendi ve vazgeçildi: yalnızca ekran klavyesi 220 MB GPU belleğini kilitli tuttu ve masaüstünün bir sonraki açılışında bir GPU bellek ayırması başarısız oldu, kabuk açılmadı |
| `2` | Yalnızca başka kimsenin başvurmadığı tamponları at; ikinci bir kullanıcının açtığı tampon yeniden "gerekli" olur | **Kullanılan.** 700 MB'lık yapay bellek baskısı altında iki çalıştırmada uyarı yok; atma ise belleği boşaltmayı sürdürüyor (bir denetimde Shmem 270 → 36 MB) |

## Masaüstü açılırken belleğe ne oluyor

Açılış sırasında belleği saniyede bir örneklemek bir sıçrama gösterdi: masaüstü birkaç saniyeliğine 600–900 MB GPU tamponu ayırıyor, sonra neredeyse hepsini bırakıyor. Atma kapalıyken bu sıçrama 1,26 GB'a ulaştı ve geri kalan her şeyi takasa itti; `2` ayarıyla çekirdek bu tamponları atılabilir oldukça geri alıyor. Açılıştan bir dakika sonra:

| | Boş bellek | GPU/paylaşımlı bellek |
| --- | --- | --- |
| Atma kapalı (`0` ayarı) | yaklaşık 485 MB | 568 MB |
| `2` ayarı | yaklaşık 1000 MB | 115 MB |

Sıçrama iki programdan geliyor (çekirdeğin GPU hesabından program başına ölçüldü): ana ekran (plasmashell, bir anlığına yaklaşık 560 MB) ve ekran klavyesi (yaklaşık 240 MB). İkisinde de bunun onda dokuzu, işlerinin çoktan bittiği ve yalnızca Mesa'nın önbelleğinde bekleyen bellek; çekirdeğin geri alabildiği de tam olarak bu.

## Bellek

| Değişiklik | Neden |
| --- | --- |
| RAM'de 1,2 GB sıkıştırılmış takas (zram), her açılışta etkin | Hiç takas yoktu; tek bir ağır sayfa masaüstünü bellek geri kazanımına itiyordu |
| `swappiness` 100, `page-cluster` 0 | RAM'e takas ucuzdur; ondan ileri okuma anlamsızdır |
| …ama ilk 75 saniye `swappiness` 10, ardından bir kez açık geri kazanım | Masaüstü açılırken yukarıda anlatılan GPU sıçraması, çekirdeğin az önce yüklediği masaüstünün 270–290 MB'ını takasa atmasına yol açıyordu. Artık açılışta hiçbir şey takasa gitmiyor ve geride kalan GPU tamponları bir kez geri alınıyor (374 → 101 MB) |
| `earlyoom` hizmeti | RAM ve takas neredeyse tükendiğinde masaüstünün donmasına izin vermek yerine en büyük web işleyicisini sonlandırır; bileşikleyiciye, kabuğa ya da ses hizmetlerine asla dokunmaz |
| Tarayıcı anahtarları (`QTWEBENGINE_CHROMIUM_FLAGS`): düşük donanımlı cihaz kipi, en fazla üç işleyici süreci, dört raster iş parçacığı | Üç sekmeyle tarayıcı belleği (PSS) 782 MB'tan 764 MB'a indi — küçük bir kazanç; süreç sayısını da sınırladığı için korundu |
| Güncelleme bildirici ve takvim alarmı otomatik başlatma girdileri kullanıcı için kapatıldı | Bu telefonda kimsenin kullanmadığı arka plan süreçleri |

## Arka plandaki uygulamalar

Beş dakikadır ön planda olmayan bir uygulama **durdurulur**: penceresini ve durumunu korur ama işlemci zamanı almaz; belleğine artık dokunmadığı için de, başka bir şey yer istediğinde çekirdek o belleği sıkıştırılmış takasa taşıyabilir. Penceresi yeniden öne geldiği anda devam eder. Uygulamalar kapatılmaz.

Bunu kullanıcının oturumundaki küçük bir hizmet yapar (`j701f-freezer`). KWin ona hangi pencerenin önde olduğunu söyler; hizmet bütün süreç ağaçlarını durdurur ve devam ettirir, yani bir tarayıcının yardımcı süreçleri de dahildir.

Asla durdurulmayanlar:

- ana ekran, bileşikleyici, ekran klavyesi, terminaller, telefon ve mesajlaşma uygulaması;
- o anda ses çalan ya da kaydeden her şey;
- ana ekran öndeyken hiçbir şey (böylece görev değiştirici her zaman canlı uygulamaları gösterir);
- ayar dosyasında adı geçen programlar.

KWin durdurulmuş bir uygulamadan yanıt beklerse — örneğin görev değiştiriciden kapatıldığı için — hizmet onu hemen devam ettirir; bir sınamada uygulama istekten yaklaşık iki saniye sonra kapandı.

Kilit ekranı sıradan bir ön plan sayılır: kilitli ekranın arkasında açık bırakılan uygulamalar bekleme süresinden sonra durdurulur. Bilinmesi gereken yan etki: **durdurulmuş bir uygulama mesaj alamaz ve indirmeyi bitiremez.** Ulaşılabilir kalması gereken bir sohbet uygulamasının yeri hariç tutma listesidir.

Ayarlar `~/.config/j701f-freezer.conf` içindedir ve 15 saniyede bir yeniden okunur:

```ini
enabled = 1          # 0 her şeyi kapatır ve durdurulanları devam ettirir
idle_seconds = 300
exclude =            # program adları, virgülle ayrılmış
```

Yaptıkları `~/.local/state/j701f-freezer.log` dosyasına yazılır. Telefonda iki uygulamayla doğrulandı: bekleme süresinden sonra durduruldu, etkinleştirilince devam etti, durdurulmuşken doğru biçimde kapandı. Henüz ölçülmedi: gündelik kullanımda ne kadar bellek ve pil kazandırdığı.

## Depolama

| Değişiklik | Etki |
| --- | --- |
| eMMC eski kip yerine DDR52'de | Sıralı okuma 22 → 60–80 MB/sn |
| Kök dosya sistemi `noatime` ile bağlı | Her dosya okumasında yazma yok |
| İleri okuma 512 KiB | Bir uygulamanın dosyaları açılışta okunurken daha az gidiş geliş |

## Masaüstü

- Canlandırma süresi yarıya indirildi (`AnimationDurationFactor` 0,5).
- KWin bulanıklık ve arka plan kontrastı efektleri olmadan çalışıyor (zaten kapalıydılar).
- Ekran ölçeği %160 (mantıksal 450 × 800). Kesirli ölçekleme her uygulamayı tam sayı olmayan bir çarpanla çizdirir; tam sayı bir ölçeğin fark edilir biçimde daha hızlı olup olmadığı ölçülmedi.

## Video

Donanımsal H.264 çözme Samsung çözücüsü üzerinden çalışıyor (H.264, HEVC ve VP8 yazılımsal çözücüyle birebir aynı resimleri veriyor, MPEG-2 neredeyse aynı; yerel bir yama gerekti, çünkü ana hat sürücüsü H.264 dışındaki her biçimde ilk anahtar kareyi atıyordu. MPEG-4 part 2 başlamıyor) ([ayrıntılar](userspace.md)). 720p bir H.264 dosyası, yazılımsal çözmeye göre yaklaşık 24 kat daha az işlemci zamanı istiyor. `mpv` onu kullanıyor; VLC kullanmıyor (denemesi siyah pencere gösterdi, bkz. [kullanıcı alanı](userspace.md)); tarayıcılar henüz kullanmıyor, yani tarayıcı içindeki video hâlâ işlemcide çözülüyor.

## Ayarlar nerede duruyor

| Telefondaki dosya | Depodaki kaynak |
| --- | --- |
| `/etc/local.d/j701f-tune.start` | `system/tune` |
| `/etc/conf.d/earlyoom` | `system/earlyoom.conf` |
| `~/.config/plasma-workspace/env/j701f-webengine.sh` | `system/session/webengine-env.sh` |
| `/etc/local.d/j701f-gpufreq.start` (CPU ve GPU frekans sınırları) | `system/gpufreq-limit` |
| `/usr/local/sbin/j701f-inputboost` (ayar betiği başlatır) | `system/inputboost` |
| `~/.local/lib/j701f-freezer/`, `~/.config/autostart/j701f-freezer.desktop`, `~/.config/j701f-freezer.conf` | `system/session/freezer/` |

## Henüz yapılmayanlar

- Gerçek bir ekran sürücüsü: bugün her kare önyükleyicinin çerçeve belleğine kopyalanıyor, donanımsal dikey eşzamanlama yok ve parlaklık panel tarafından değil yazılımla uygulanıyor.
- Tarayıcı içinde donanımsal video çözme.
- Standart bir başarım ölçümüyle telefonun Android değerleriyle karşılaştırma.

## Uygulama açılışı, ilk tablo (2026-10-10)

`tools/app-start-bench.sh` telefonda bir uygulamayı başlatır, işlemciyi bir saniye boyunca kullanmayı bırakmasını bekler ve süreyi, harcanan işlemci zamanını ve belleği bildirir. Bir kez dosya önbelleği boşaltıldıktan sonra, bir kez de sıcakken.

| Uygulama | Soğuk | Sıcak | İşlemci zamanı | Bellek |
| --- | --- | --- | --- | --- |
| Ayarlar | 7,3 sn | 4,8 sn | 5 sn | 128 MiB |
| Hesap makinesi | 9,3 sn | 7,3 sn | 6–7 sn | 135 MiB |
| Galeri (Koko) | 7,0 sn | 4,3 sn | 4–5 sn | 100 MiB |
| Podcast (Kasts) | 7,8 sn | 5,3 sn | 5 sn | 139 MiB |
| AudioTube | 9,5 sn | 8,8 sn | 9 sn | 210–220 MiB |
| GNOME Software | 21 sn | 22 sn | 21–24 sn | 160–180 MiB |

Saat, Hava Durumu ve Pure Maps hiç durulmuyor - çizmeyi sürdürüyorlar (Hava Durumu yalnızca sayfasını gösterirken yarım işlemci çekirdeği kullanıyor) - bu yüzden bu ölçü onlara uygulanamıyor. Angelfish'in sayıları tutarsızdı, çünkü web motoru yardımcı süreçlerini geç başlatıyor.

Tablonun söylediği: sıcak açılış soğuktan pek hızlı değil, yani fren depolama değil. Her Qt uygulaması hazır olana kadar dört ila yedi saniye saf işlemci zamanı harcıyor, GTK uygulaması yirmiden fazla. Araç takımlarının içindeki neden henüz aranmadı.

Hesap makinesinin açılışının ilk profili o işlemci zamanının nereye gittiğini gösteriyor: yaklaşık üçte biri C kitaplığının dinamik yükleyicisinde (Alpine'in musl kitaplığı, program başlarken her kitaplığın ve eklentinin her simgesini çözer), beşte biri Qt'nin QML motorunda, beşte biri Qt Core'da. Derlenmiş QML ve gölgelendirici önbellekleri var ve kullanılıyor. Bu, tek bir uygulamanın tek bir profilidir; bir çare denenmedi.

2026-10-13'te doğrudan ölçüldü: programın başka hiçbir şeyi çalışmadan yalnızca yükleyici (`/lib/ld-musl-aarch64.so.1 --list PROGRAM`; her kitaplığı yükler, her simgeyi çözer ve çıkar), her şey dosya önbelleğindeyken altı çalıştırmanın ortancası:

| Program | Kitaplık | Yükleyici süresi |
| --- | --- | --- |
| Hesap makinesi | 94 | 0,54 sn |
| Ayarlar | 97 | 0,57 sn |
| Galeri (Koko) | 134 | 1,09 sn |
| Angelfish | 170 | 1,12 sn |
| GNOME Software | 126 | 0,81 sn |

Bu, programın kendi ilk komutundan önce ödenen kısımdır; bir Qt uygulamasının sonradan yüklediği eklentiler (QML modülleri, platform ve stil eklentileri) aynı yolla çözülür ve profildeki yükleyici payının kalanını oluşturur. Yani her açılışın yarım saniye ile bir saniyesi, önbellek sıcakken bile, başka her şeyden önce yükleyicide geçer; çaresi de bu portta değil, dağıtımın kitaplıklarını nasıl derlediğindedir (daha az ya da önceden bağlanmış simge). Yükleyicinin payı için bu, bu işlemci ve bu dağıtımda tabandır. Aynı gün hesap makinesinin ikinci bir profili (sıcak açılış, 8 saniye, saniyede 499 örnek) resmin tamamını veriyor: yükleyici %27, Qt'nin QML motoru %17, çekirdek %16 (çoğunlukla bellek sayfası verme ve temizleme), Qt Core %15, Qt Gui ve Quick %4 ve %3, GPU sürücüsü %3, hesap makinesinin kendi matematik kitaplığı ile tanımlarını okuduğu XML ayrıştırıcı birlikte %6, yazı tipleri %1. Qt'nin içinde tek bir işlev bile yüzde biri bulmuyor: zaman, binlerce küçük nesnenin oluşturulup birbirine bağlanmasına yayılmış. Kaldırılacak bir sıcak nokta yok. Bugün asıl yardımcı olan hiç başlatmamaktır: dondurucu, yakın zamanda kullanılan uygulamaları bellekte tutar.

## Ana ekran hareketleri (2026-10-10, yerel ekran sürücüsü)

`tools/ui-frame-bench.sh` bir parmak hareketi enjekte eder ve bir şey hareket ederken gerçekten sunulan kareleri sayar.

| Hareket | İlk ölçüm | GPU sınırı geri geldikten sonra |
| --- | --- | --- |
| Üst paneli indirip kaldırma | saniyede 52–54 | 54 |
| Uygulama çekmecesi: parmak kalktıktan sonraki canlandırma | saniyede 20–40 | 55–60 |
| Ana sayfalar arasında sağa sola | saniyede 24–25 | 42 |

İlk sütun, fark edilmeden GPU'su önyükleyicinin 343 MHz'inde tutulan bir telefonda ölçüldü: açılıştan sonra hız sınırlarının yükseltilmesini koruyan bir güvenlik işareti, bilinçli bir yeniden başlatmadan geride kalmıştı ve elle silinene kadar duruyordu. Açılış betiği artık böyle bir işaretin yalnızca bir açılışa mal olmasını sağlıyor. KWin'in bulanıklık efekti bu telefonda etkin değil; karşılaştırma için açmak üst paneli yavaşlattı.
