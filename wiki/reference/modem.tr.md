# Modem

J701F içinde Samsung Shannon 315 hücresel modem bulunur. Mainline Linux
telefonu açıyor, ancak arama, SMS ve mobil veri henüz çalışmıyor. Modemin
kendi yazılımı vardır; Linux ile ayrılmış bellek ve mailbox üzerinden
haberleşir. Şu anki mainline sistemde bunun sürücüsü ve başlatma hizmeti yok.

İlk geliştirme adımı, RADIO imajının başındaki 512 baytlık tabloyu ana
bilgisayarda salt okunur biçimde inceleyen araçtır. `tools/modem-radio-toc.py`,
`BOOT` ve `MAIN` bölümlerinin sınırlarını doğrular; yazılımlarını kopyalamaz,
telefona dokunmaz. Biçim, herkese açık
[Samsung TOC şablonuna](https://github.com/Comsecuris/shannonRE/blob/master/010/sam.bt)
dayanır. Araç, bozuk başlık testlerini ve bilgisayardaki SM-J701F fabrika CP
paketinin başlığını geçti. Claude telefonun RADIO bölümündeki ilk 512 baytı
USB seri üzerinden yazmadan okudu; başlık fabrika paketiyle birebir aynı.
Araç imzayı doğrulamaz ve modemi başlatmaz.

Tek seferlik salt okunur mailbox tanılama modülü derlenip bir kez yüklendi.
Güvenli monitörün ham dönüşü `0xb` idi; bu CP güç bitleri değil, hata kodu.
CP mailbox kayıtları sıfırdı. Claude'un sonraki sınırlı denemesinde BOOT ve
MAIN ayrılmış CP RAM'ine kopyalandı ve güvenli monitör bunları kabul etti.
Çözülen CP_CTRL_NS değeri `0x06a0`: `PWRON` kapalı; CP'yi başlatma denenmedi.
Modem bağlantısı hâlâ etkin değil. Telefon bölümlerine yazılmadı. Sonraki
isteğe bağlı deneme, güvenli monitör hatalarını çözmeli, bootloader'ın CP
devir bloğunu denetlemeli ve tam IPC el sıkışmasından önce mailbox durumunu
zaman sınırıyla gözlemlemeli.

Fabrika sürücüsü açılış, biçimli komutlar ve radyo dosya hizmeti için SIPC5
kanallarını kullanıyor. Ana bilgisayarda çalışan çerçeve ayrıştırıcısı ve
sentetik NV istek modeli test edildi. Model bütün yazmaları RAM'de tutar ve
EFS'yi okuyamaz. J701F'nin gerçek yanıt biçimi CP başladıktan sonra
ölçülecek. `libsamsung-ipc` yararlı Samsung protokol desteği içeriyor, ancak
J701F arka ucu yok. Plan, bu arka ucu ekleyip sonra `samsungipcd` AT köprüsü
ve ModemManager'ı denemek. Şu anda çalışan modem hizmeti kurulmuş değil.
[Teknik notlar](https://github.com/Burak-GGM/j701f-linux/blob/main/docs/j701f-modem.md)
ve [kullanıcı alanı tasarımı](https://github.com/Burak-GGM/j701f-linux/blob/main/docs/j701f-modem-userspace.md).
