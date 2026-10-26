# Bu wikiyi güncel tutmak

## Kural

**Proje değiştiğinde wiki de aynı işin içinde değişir.** Yeni bir sürücü, telefonda yeni bir betik, farklı bir çekirdek sürümü, yeni bulunan bir tuzak — her biri, iş bitti sayılmadan önce buraya girer. Bu, projeye dokunan herkes için geçerlidir; insanlar için de yapay zekâ yardımcıları için de.

Wiki insanlar için yazılır. Orada olmayan biri tarafından okunabilir kalmalıdır: bir şeye ne yapıldığını söylemeden önce onun ne olduğunu açıklayın, anahtar sözcük listesi yerine cümle kurun ve adım adım dökümü dışarıda bırakın.

## Ne nereye girer

| Değişikliğin türü | Güncellenecek yer |
| --- | --- |
| Bir donanım çalışmaya başlıyor ya da bozuluyor | [Donanım ve durum](reference/hardware.md); manşetlik bir kalemse [ana sayfadaki](index.md) tablo da |
| Yeni ya da değişen çekirdek yaması, yapılandırma seçeneği, aygıt ağacı katmanı | [Çekirdek, yamalar, aygıt ağacı](reference/kernel.md) |
| Telefona kurulan yeni ya da değişen dosya, paket tercihi, denetim | [Kullanıcı alanı](reference/userspace.md) |
| Açılış akışı, bölümler, yeni bir güvenlik düzeneği | [Açılış zinciri ve güvenlik ağları](reference/boot-chain.md) |
| Yeni araç ya da değişen iş akışı | [Araçlar ve iş akışı](reference/tools.md) |
| Anlaşılması gerçekten zaman alan bir sorun | [Dersler ve tuzaklar](reference/lessons.md) |
| Yepyeni bir çalışma alanı (modem, kamera, ekran sürücüsü…) | *Yolculuk*'ta yeni bir bölüm; `mkdocs.yml`'e eklenir |

*Yolculuk* bölümleri tarihtir. Bir kademe bittiğinde onları uzatın; önceki bölümleri bugüne uysun diye yeniden yazmayın — başvuru sayfaları bunun içindir.

## İki dil

Her sayfa iki kez vardır: asıl metin olan İngilizce `sayfa.md` ve Türkçe `sayfa.tr.md`. İkisini de değiştirin. Yalnızca biri güncellenebiliyorsa İngilizce sayfayı güncelleyin ve bunu Türkçe sayfanın en üstünde belirtin; böylece kimse bayat bir çeviriyi doğru sanmaz.

Komutlar, dosya adları, yazmaç adları ve çekirdek terimleri iki dilde de olduğu gibi kalır.

## Aynı anda birden fazla kişi çalışırken

İki kişi ya da yardımcı projede aynı anda çalışırken, telefonu ve çekirdek derleme ağacını `tools/coord.sh` üzerinden paylaşır: her ortak kaynak için bir kilit, kimin ne yaptığını söyleyen bir pano ve sorular için bir mesaj kutusu. Kurallar `docs/coordination/README.md` içindedir; o klasör çalışma bilgisayarında kalır, herkese açık depoya girmez. Büyük bir düzenlemeden önce wiki sayfasını panoda sahiplenin; böylece iki düzenleme çakışmaz.

## `docs/` ile ilişki

`docs/` çalışma notlarını tutar: uzun, tarihli, ayrıntılı, iş yapılırken yazılmış. Özellikle `docs/j701f-mainline.md` tam günlüktür ve belirli bir yardımcının eklediği bölümler kimin yazdığıyla işaretlidir. O notlar kaynaktır; wiki özettir. Çeliştiklerinde telefonu denetleyin ve ikisini de düzeltin.

## Herkese açık depo

Proje 2026-10-26'dan beri GitHub'da GPL-2.0-only lisansıyla yayımlanır. Bir şey gönderilmeden önce firmware, bölüm yedeği, parola ya da anahtar ve ev ağı ayrıntısı içermediği denetlenir: bunlar git'in yok saydığı yollarda kalır (`build/`, `original/`, `tools/downloads/`, `docs/coordination/`, `.phone-ip`). Notlardaki IP adresleri `192.168.1.0/24` aralığını kullanır.

`main` dalına yapılan her gönderimde GitHub birim testlerini ve `mkdocs build --strict` derlemesini çalıştırır; ikisi de geçerse derlenen wiki <https://burak-ggm.github.io/j701f-linux/> adresinde yayımlanır (`.github/workflows/ci.yml`). Böylece katı derlemeden geçmeyen bir sayfa herkese açık siteye hiç ulaşmaz.

## Wikiyi derlemek

```sh
python3 -m venv build/wiki-venv
build/wiki-venv/bin/pip install -r wiki/requirements.txt

# http://127.0.0.1:8000 adresinde canlı önizleme
build/wiki-venv/bin/mkdocs serve

# build/wiki-site/ içinde statik site
build/wiki-venv/bin/mkdocs build --strict
```

`--strict`, kırık bağlantıları ve eksik sayfaları hataya çevirir. Bir değişikliği bitirmeden önce çalıştırın.

## Üslup

- Şu an neyin doğru olduğunu ve bunun nasıl bilindiğini söyleyin. "Telefonda doğrulandı", "yazıldı ama denenmedi" ve "başlanmadı" üç ayrı durumdur; ayrı tutun.
- Sayıları birimleriyle verin.
- Sır kaydetmeyin: parola yok, Wi-Fi anahtarı yok, seri numarası yok, gerçek MAC adresi yok.
- Sayfaları bir oturuşta okunacak kadar kısa tutun. Bir sayfa bunu aşarsa bölün.
