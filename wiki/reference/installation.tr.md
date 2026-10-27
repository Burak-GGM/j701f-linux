# Dağıtımın kurulumu

Kurulum yalnızca **Samsung SM-J701F (`j7velte`)** modelini hedefler. Alpine 3.24 dosya sistemini 11,12 GiB büyüklüğündeki `USERDATA` bölümüne yazar. Mevcut mainline BOOT çekirdeği ve projenin RAM kurtarması korunur. Stok Android telefona önce bu iki uyumlu bileşenin kurulması gerekir; yalnız DATA kurulumu stok Android'i bu dağıtıma dönüştürmez.

!!! danger "USERDATA tamamen silinir"
    Kurulum Android verilerini, dahili depolama dosyalarını, önceki Linux kurulumunu, hesapları ve Wi-Fi ayarlarını yok eder. Gerekli dosyaları başka yerde saklayın. Güç kesintisi veya başarısız yazma, kurtarmadan ya da Download Mode'dan onarılana kadar telefonu **brick edebilir; normal açılış çalışmayabilir**. Dosyaları başka J7 varyantlarında kullanmayın. DATA kurucusu PIT, bootloader, EFS, modem, BOOT veya RECOVERY bölümlerine yazmaz.

## DATA imajını oluşturma

Docker ve `e2fsprogs` bulunan Linux bilgisayarda, depo kökünden:

```sh
python3 tools/build-release.py --development \
  --modules-dir build/release-scratch/modules
```

`--development`, derleyiciyi, Git'i ve tanılama araçlarını telefonda tutar. İsteğe bağlı modül dizini, kurulu çekirdeğin tam sürümü için derlenmiş modülleri içermelidir; genel dağıtım imajında bunu atlayın. Derleme sabitlenmiş ve imzası doğrulanmış Alpine minirootfs dosyasını denetler, AArch64 paketlerini çözer, telefona özgü servisleri kurar ve `build/release/userdata.ext4.gz`, iki SHA-256 dosyası ile `release.json` üretir. ZIP yolu, cihazda doğrulandıktan sonra [grafik kurtarma](recovery.md) sayfasında anlatılacaktır.

Sıkıştırılmış dosya FAT32'nin tek dosya için 4 GiB sınırının altında kalmalıdır. Tam ext4 imajı tam olarak 23.314.432 sektördür ve mevcut BOOT aktarımının beklediği UUID'yi taşır. Derleme kayıtlı Wi-Fi ağlarını, SSH anahtarlarını veya parolaları kopyalamaz. Yeni kurulum ilk başta çevrimdışı açılır; ağı telefonda sonradan yapılandırın.

## Çalışan J701F Linux üzerinden otomatik yeniden kurulum

Bu yol, telefonda projenin Linux sisteminin çalışmasını, sabitlenmiş SSH anahtarıyla erişimi, takılı harici SD kartı ve USB bağlantısını gerektirir. Hazırlanmış bir cihazı yeniden kurmak içindir. Adresi `--phone-ip` (veya `J701F_PHONE_IP`) ile belirtin; doğrulanmış SSH anahtarını `build/phone-ssh-known-hosts` içinde tutun (veya `--known-hosts` verin). Önce planı inceleyin:

```sh
python3 scripts/install-release.py --release build/release
```

Veriyi silerek kurmak için iki açık seçeneği de kullanın:

```sh
python3 scripts/install-release.py --release build/release --phone-ip PHONE_IP \
  --execute --erase-userdata --backup-userdata --reboot
```

Araç imajı kontrol eder, SD karta kopyalar, SD kopyasını doğrular, RAM kurtarmasını açar, modeli ve bölüm boyutunu kontrol eder, depolamayı değiştirmeden önce açılmış imajın tamamını doğrular, yalnız `USERDATA` bölümünü yazar ve **tüm** bölümün geri okunan SHA-256 değerini oluşturulan imajla karşılaştırır. `--backup-userdata` önce eski bölümün tam kopyasını SD karta 1 GB'lık parçalar hâlinde kaydedip doğrular; yaklaşık 12 GiB ek boş alan gerekir. Bu parçalar eski veriyi düz biçimde içerir: kartı özel tutun ve geri dönüş gerekmeyince dosyaları kaldırın. Bir kontrol başarısız olursa kurtarma açık kalır. `--reboot` yalnız geri okuma başarılıysa yeni sistemi açar. İşlem boyunca USB ve güç bağlı kalsın.

MTP/FUSE bulunan bilgisayarda daha hızlı kopya için telefonun USB MTP alanını bağlayıp **harici SD depolama dizinini** `--mtp-sd /path/to/SD-card` olarak verin. Kurucu yeniden başlatmadan önce yine her dosyayı telefondaki fiziksel SD bağlantısından doğrular. Bu seçenek yoksa dosyalar SSH üzerinden aktarılır. Uzun yedekleme ve yazma işlemi bağımsız kurtarma oturumunda çalışır; geçici USB seri kopması devam eden bölüm yazımını iptal etmez.

Örneğin Linux bilgisayarda `jmtpfs` varsa yerel Linux dosya sisteminde `mkdir -p "$HOME/j701f-mtp"` ardından `jmtpfs "$HOME/j701f-mtp"` çalıştırın. Kurulum komutuna `--mtp-sd "$HOME/j701f-mtp/SD-card"` ekleyin. Kurucu telefonun USB kipini değiştirmeden önce bilgisayardaki MTP bağlantısını ayırır. Telefonda USB MTP servisi çalışmalı ve harici SD kart takılı olmalıdır.

Yeni yerel hesabın parolası veya kayıtlı SSH yetkisi yoktur. Parolasız kilit ekranında kalmamak için otomatik ekran kilidi başlangıçta kapalıdır. Cihazda parola oluşturduktan sonra Sistem Ayarları'ndan ekran kilidini açın. Bu telefonun donanım deneme imajı yerel firmware içerdiği için dağıtılamaz olarak işaretlenmiştir; yalnız genel imajı veya her kullanıcının kendi cihazından firmware çıkarma yönergelerini yayımlayın.

## SD kartla adım adım kurulum

Normal Linux çalışmıyor ancak projenin kurtarması ve USB seri konsolu çalışıyorsa bu yol kullanılabilir.

1. `userdata.ext4.gz`, `userdata.ext4.gz.sha256`, `userdata.ext4.sha256`, `release.json` ve `scripts/install-release-on-recovery.sh` dosyalarını harici SD kartın `j701f-release/` dizinine kopyalayın.
2. Projenin kurtarmasını açın, USB'yi bağlayın ve bilgisayarda `python3 tools/usb-console.py` çalıştırın. `: > /run/recovery-state/stay` ile kurtarmayı açık tutun.
3. SD kartı `sh /recovery/scripts/storage.sh mount-sd` ile bağlayın. Kurtarmanın MTP ve Wi-Fi yardımcılarını `sh /recovery/scripts/mtp.sh down` ve `sh /recovery/scripts/wifi.sh down` komutlarıyla durdurun. MTP durunca USB yeniden bağlanabilir. Eski DATA bağlıysa `umount /mnt/root` ile ayırın.
4. Silmeden önce kontrol edin: `sh /mnt/sd/j701f-release/install-release-on-recovery.sh --erase-userdata`. Sonunda `DRY RUN ONLY` görünmelidir.
5. Yazın ve doğrulayın: `sh /mnt/sd/j701f-release/install-release-on-recovery.sh --execute --erase-userdata`. `WRITTEN AND VERIFIED` sonucunu ve `/mnt/sd/j701f-release/install.status` içindeki `PASS` değerini bekleyin. Ardından kurtarmada **Reboot system** seçin.

Yazma başarısız olursa telefonu kurtarmada bırakıp görünen hata ile `install.status` dosyasını inceleyin. Eksik yazılmış DATA bölümünün açılacağını varsaymayın. Bu adımlar tam J701F aygıt ağacını, uyumlu BOOT aktarımını, `USERDATA` bölüm adını ve boyutunu, bağlı olmayan hedefi, gzip bütünlüğünü ve SHA-256 değerlerini kontrol eder.

## Kurulum öncesi DATA yedeğine dönme

Kurulumda `--backup-userdata` kullanıldıysa harici SD kartta `j701f-backups/preinstall-userdata-YYYYMMDD-HHMMSS.part.aa` ile `.al` arasında 12 parça ve eşleşen `.sha256` bulunur. **Önceki USERDATA bölümünün tamamını** geri yüklemek için projenin RAM kurtarmasını açıp açık tutun, fiziksel SD kartı bağlayın, yukarıdaki gibi MTP ve Wi-Fi yardımcılarını durdurun ve `/mnt/root` bağlıysa ayırın. Geri yükleme betiği SD karttaki `j701f-release/` dizinine kopyalanmıştır.

Önce hiçbir şey yazmadan 12 parçanın tümünü ve bölümün SHA-256 değerini doğrulayın:

```sh
sh /mnt/sd/j701f-release/restore-userdata-on-recovery.sh \
  --backup-id preinstall-userdata-YYYYMMDD-HHMMSS --restore-userdata
```

Zaman damgasını gerçek yedek adıyla değiştirin. Eski bölümü yazmak için komutu `--execute` ekleyerek tekrarlayın; bu işlem **şimdiki USERDATA bölümünü siler**. Araç telefonu ve bölüm boyutunu denetler, bağlı DATA'yı reddeder, yazmadan önce her yedek parçasını doğrular, ardından geri yüklenen bölümün tamamını yeniden okur. Yeniden başlatmadan önce `RESTORED AND VERIFIED` ile ilgili `.restore.status` dosyasında `PASS` görünün. Başarısız işlemden sonra kurtarma inceleme için açık kalır.

**Gerçek cihazda ilk çalıştırma (2026-10-27): otomatik yeniden kurulum çalışıyor.** Projenin kendi telefonunda `scripts/install-release.py --execute --erase-userdata --backup-userdata --reboot` eski USERDATA'nın doğrulanmış 12 parçalık yedeğini aldı, sürümü yaklaşık beş dakikada yazdı, bölümün tamamını eşleşen SHA-256 ile geri okudu ve yeni sistemi başlattı; sistem yerel ekran sürücüsüyle Plasma Mobile'a kendiliğinden giriyor. Yolda bulunan dört hata giderildi (kurtarmanın USB seri portu tanınmıyordu, MTP'yi durdurmak USB bağlantısını koparıyordu, bir parola yaşı alanı otomatik girişi engelliyordu ve bir SD denetimi seri çıktıyı yanlış ayrıştırıyordu); kurtarmayla ilk bağlantı kaybolursa `--from-recovery` sürümü yeniden kopyalamadan devam eder. Kurtarma ZIP'i ve stok Android'den ilk kurulum henüz donanımda çalıştırılmadı.
