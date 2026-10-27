# Alpine dağıtım imajını oluşturma

Dağıtım oluşturucusu, SM-J701F'nin `USERDATA` bölümü için Alpine 3.24 ve Plasma Mobile içeren tam bir kök dosya sistemi hazırlar. Bilgisayarda çalışır ve telefona bağlanmaz. Ayrı kurulum aracı, imajı yalnızca kendi cihaz ve veri kaybı denetimlerinden sonra yazar.

Depo kökünde `python3 tools/build-release.py` çalıştırılır. Docker, `gzip`, `blkid` ve `e2fsck` gereklidir. Derleyicileri, Git'i, Neovim'i ve tanılama araçlarını eklemek için `--development` kullanılır. `--modules-dir PATH`, kurulu çekirdekle eşleşen yerel modülleri ekler; oluşturucu telefondan kopyalanmış Samsung aygıt yazılımı dosyasını dışarıda bırakır. Eşleşen doğal ekran modülleri ve çekirdek özeti varsa imaj, korumalı doğal ekran geçişini açar. Bunlar yoksa masaüstü firmware framebuffer'ını kullanır; Panfrost yine GPU işlemeyi sağlar. Kişisel kurulumda `--wifi-firmware-dir PATH` aynı telefondan çıkarılmış üç Broadcom dosyasını, `--mfc-firmware-file FILE` video çözücünün aygıt yazılımını, `--umtprd-binary FILE` ise USB dosya aktarımı için AArch64 uMTP-Responder çalıştırılabilir dosyasını ekler. Bu yerel ekler `release.json` içinde imajı yeniden dağıtılamaz olarak işaretler: yok sayılan `build/` dizininde tutulmalı, internete yüklenmemelidir. Genel derlemede USB MTP yapılandırması vardır ancak yanıtlayıcı program bulunmadığı için kurulana kadar MTP çalışmaz. Genel Alpine aygıt yazılımı paketi sıkıştırılmış dosyalar ve genel bir kart profili içerdiğinden, yeni genel kurulumda Wi-Fi henüz garanti edilemez. Herkesin kullanacağı sürümde kart aygıt yazılımını ve MTP programını sağlamak için lisansa uygun ayrı yollar gerekir.

Oluşturucu, sabitlenmiş Alpine 3.24.0 minirootfs dosyasının sağlama toplamını ve sürüm imzasını doğrular; ardından AArch64 paketlerini Alpine 3.24 `main` ve `community` depolarından çözer. Paket listeleri `system/release/base-packages.txt`, `system/apps/core.txt` ve isteğe bağlı `system/apps/optional-development.txt` dosyalarından gelir. Sabitlenmiş bir Alpine Docker imajı, farklı mimariye paket kurar. `system/release/` içindeki betikler telefona özgü açılış dosyalarını, OpenRC servislerini, masaüstü ayarlarını, SD kart bağlantısını ve yerel hesabı ekler. Hedef mimarinin paket kurulum betikleri x86 bilgisayarda çalıştırılamadığı için bir defalık servis, telefondaki ilk masaüstü girişinden önce yerel önbellekleri oluşturur.

Bu ilk önbellek oluşturma işlemi telefonun eMMC'sinde masaüstünün açılmasını birkaç dakika geciktirebilir. İlerleme ve hatalar `/var/log/j701f-release-firstboot.log` dosyasına yazılır; başarılı olunca sonraki açılışlarda atlanır.

Çıktılar `build/release/` dizinindedir:

| Dosya | Amaç |
| --- | --- |
| `userdata.ext4.gz` | Kurtarma kurucusu ve FAT32 SD kartı için sıkıştırılmış ext4 imajı |
| `userdata.ext4.gz.sha256` | Taşıma dosyasının özeti |
| `userdata.ext4.sha256` | Geri okumada karşılaştırılacak, açılmış bölüm imajının özeti |
| `release.json` | Cihaz, bölüm boyu, UUID, kaynak doğrulaması, paket listesi ve özetler |

Açılmış imaj tam 23.314.432 sektördür; bu telefonda ölçülen `USERDATA` boyudur. ext4 UUID'si `4ce26b55-8a59-4fb7-aad4-919a5c2cefeb`, `/etc/j701f-system-version` değeri `BURAK_ALPINE_0_1` olarak kalır. Mevcut BOOT yükleyicisi ikisini de zorunlu tutar. Oluşturucu boyutu, UUID'yi ve dosya sistemini `e2fsck -fn` ile doğrular; sıkıştırılmış dosyanın FAT32 tek-dosya sınırına sığdığını da denetler. BOOT ve RECOVERY'ye dokunmaz.

Dağıtıma kayıtlı Wi-Fi ağı, kullanıcı SSH anahtarı, SSH sunucu anahtarı, parola veya telefona özel makine kimliği kopyalanmaz. Yerel `burak-alpine` hesabı boş parolayla ve otomatik grafik girişle başlar; kullanıcı parola belirleyene kadar otomatik ekran kilidi kapalıdır. SSH yalnızca bu hesabın açık anahtarla girişine izin verir; kurulumdan sonra anahtar eklenmelidir. İmaj, geliştirme telefonunun parolasız `sudo` politikasını da korur; açık masaüstüne fiziksel erişim yönetici yetkisi verir. Sahibi Wi-Fi'yi Plasma'dan ayarlayana kadar yeni sistem çevrimdışı başlayabilir. Dağıtıma özel Wi-Fi yöneticisi, çevrimdışıyken NetworkManager'ı açık tutar; böylece ilk ağ grafik arayüzden eklenebilir.

Oluşturma işlemi bilgisayarda doğrulanır. Başarılı bir imaj oluşturma işlemi, yeni kurulumun açıldığını veya TWRP/OrangeFox'un ZIP'i kabul ettiğini tek başına kanıtlamaz. Bunlar ayrı telefon testleri gerektirir ve kurulum belgelerinde kaydedilir.
