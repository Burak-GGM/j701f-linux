# 2. Recovery bölümünde Linux

**Hedef:** telefona kendi yazdığımız bir programı çalıştırtmak ve onunla konuşabilmek.

## Android açılış imajı, birbirine yapıştırılmış üç dosyadır

`RECOVERY` bölümü bir *Android açılış imajı* tutar: küçük bir başlık, bir Linux çekirdeği, sıkıştırılmış bir **initramfs** (RAM'de yaşayan minik bir kök dosya sistemi) ve bu telefonda ayrıca bir aygıt ağacı tablosu. Önyükleyici hepsini belleğe yükler ve çekirdeğe atlar. Çekirdek initramfs'i açar ve içindeki `/init` dosyasını ilk süreç olarak çalıştırır.

Bu, mümkün olan en kolay giriş noktasını verir: **çekirdeği ve aygıt ağaçlarını olduğu gibi bırak, yalnızca initramfs'i değiştir.** Çekirdek bu telefonu sürmeyi zaten biliyor; biz yalnızca neyi çalıştıracağını değiştiriyoruz.

Projenin ilk araçları tam olarak bunu yapar. `tools/recovery.py` OrangeFox imajını ayrıştırır (düzeni `docs/recovery-image-format.md` içinde belgeli) ve derleme, içine şunları barındıran yeni bir initramfs koyar:

- statik bir **BusyBox** (bir kabuk ve yüz kadar küçük Unix aracını tek dosyada sunan program),
- `/proc`, `/sys` ve `/dev`'i bağlayan bir `/init` kabuk betiği,
- ve kendi yazdığımız tek bir satır.

İmaj Odin ile `RECOVERY`'ye yazılır, telefon Power + Home + Ses Açma ile başlatılır ve çekirdek günlüğünde şu görünür:

```text
HELLO FROM BURAK'S J701F LINUX RECOVERY
```

İlk kilometre taşının tamamı bu satırdır. Zincirin çalıştığını kanıtlar: bizim derlememiz, yazma aracı, önyükleyicinin imajı kabul etmesi ve çekirdeğin bizim `/init`'imizi çalıştırması.

## USB üzerinden kabuk

Kimsenin göremediği bir selamın pek faydası yok — ekran hâlâ siyahtı. Telefonla konuşmanın en hızlı yolu, onu bir USB seri adaptörü gibi davranmaya ikna etmektir. Üretici çekirdeği Android'in USB gadget altyapısını destekliyor; `/init` bir **ACM** işlevi açar ve üzerinde bir kabuk başlatır. Bilgisayarda yeni bir aygıt, `/dev/ttyACM0` belirir ve `tools/usb-console.py` onu açar:

```text
$ uname -a
Linux (none) 3.18.140-SIMPLE-KERNEL_V1.0 ... aarch64
```

Bu andan itibaren telefon içeriden incelenebilir: bölüm boyutları, çekirdek yapılandırması, canlı aygıt ağacı, GPU gerilimleri. Sonraki aşamaların ihtiyaç duyduğu bilgilerin çoğu bu kabuk üzerinden toplandı.

## Ekranı çalıştırmak

Ekran, kabuktan daha zor çıktı. Çekirdek bir çerçeve belleği, `/dev/fb0` sunuyordu, ama içine çizmek hiçbir şey göstermiyordu. Bu araştırma, projenin nasıl çalıştığına iyi bir örnek:

1. Çerçeve belleğinin neye benzediğini varsaymak yerine telefona sor (720×1280, piksel başına 32 bit, belirli bir kanal sırası).
2. Her çağrının *başarılı* döndüğünü ama panelin siyah kaldığını fark et — başarı kodu kanıt değildir.
3. İlgili üretici ekran sürücüsünü oku, sonra `FBIOPUT_VSCREENINFO` ile mevcut kipi yeniden uygulamayı dene. Sürücü bildirdiği biçim bilgilerini düzeltti ve kullanıcı ekranda görüntü oluştuğunu doğruladı.

Kip etkinleştirilince pikseller belirdi. Ayrı bir denemede çizicideki kırmızı ve mavi kanallar yer değiştirdi: kullanıcı turuncu/yeşil yerine amaçlanan mavi/yeşil çubuğu gördü. Bunun üstüne proje, dokunmatik klavyeli küçük bir ekran terminali kurdu; böylece telefon bilgisayarsız da kullanılabildi. Bir de güç menüsü eklendi (yeniden başlat, Download Mode, kapat).

## Bu aşama ne kazandırdı

- Projenin geri kalanı boyunca işe yarayan bir kurtarma ortamı.
- Telefonun içine bakmanın güvenli bir yolu.
- Derle → yaz → aç döngüsüne güven.

Hâlâ *üreticinin* çekirdeği kullanılıyor. Recovery imajı kalıcı olarak yazılı, ama çalışan kök dosya sistemi RAM'de: kabukta yapılan değişiklikler ve geçici yüklemeler yeniden başlatınca kayboluyor. Sonraki bölüm kalıcı bir kök dosya sistemi ekliyor.

!!! info "Depodaki ayrıntılar"
    Bu aşamanın çalışma notları: `docs/boot-chain.md`, `docs/recovery-image-format.md`, `docs/usb-console.md`, `docs/ondevice-terminal.md` ve `docs/hardware-status.md`.
