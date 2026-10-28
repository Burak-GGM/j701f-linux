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
Güvenli monitör üzerinden CP güç kaydı `0xb`, CP mailbox kayıtları sıfır
okundu; modül sonra kendiliğinden çıktı. Modem bağlantısı hâlâ etkin değil.
Ana bilgisayarda `Module.symvers` bulunmadığından sembol uyarıları vardı;
Claude gerçek deneme için telefonun çekirdek ağacına karşı yeniden derledi.
Sonraki aşamalar: modüler CP
sürücüsü, sınırları denetlenen yazılım yükleyici ve en son hücresel kullanıcı alanı.
Modem açılışı ayrıca güvenlik isteği ve IPC el sıkışması gerektirir. Cihaza
özgü NV verisi özel bir kopyada tutulacak; ilk geliştirmede değişiklikler
yalnızca RAM'de kalacak. [Teknik notlar](https://github.com/Burak-GGM/j701f-linux/blob/main/docs/j701f-modem.md).
