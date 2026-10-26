# Kamera

!!! success "Durum: iki kamera da sıradan birer Linux kamerası (2026-10-10)"
    Ana hat çekirdeğinde Plasma Camera'da canlı önizleme, fotoğraf çekme ve arka/ön kamera arasında geçiş çalışıyor (enjekte dokunuşlarla denendi). **Video kaydı çalışmıyor** - dosya boş çıkıyor. Telefonun sahibi onunla fotoğraf çekti; fotoğraflar tepetaklak çıktı, döndürme düzeltildi ve düzeltmeyi doğrulayan bir fotoğraf hâlâ bekleniyor. Kamera işi, sahibinin isteğiyle duraklatıldı (2026-10-13).

## Ne çalışıyor

İki sensör de libcamera'ya "Internal back camera" ve "Internal front camera" olarak görünüyor; libcamera üzerine kurulu uygulamalar - en başta Plasma Camera - onları görüyor. Sürücü açılışta yükleniyor.

| | Arka | Ön |
| --- | --- | --- |
| Sensör | Samsung S5K3L2, 13 MP | Samsung S5K5E3, 5 MP |
| Sunulan kip | 2072 × 1552 (3,2 MP), saniyede 30 kare | 1280 × 960 (1,2 MP), saniyede 30 kare |

Renk, pozlama ve beyaz dengesi libcamera'nın yazılımsal görüntü işlemesiyle işlemcide yapılıyor; arka kamerada kare başına yaklaşık 50 ms.

## Nasıl çalışıyor

Samsung'un kamera yazılımından hiçbir şey kullanılmıyor - ne sürücüsü ne de kapalı görüntü işlemci yazılımı.

1. **Sensör.** Üreticinin sırasıyla güç verilir ve I2C üzerinden üreticinin bir kipe ait yazmaç tablolarıyla programlanır.
2. **CSI-2 alıcısı.** Bu yonga setinin alıcısının kendi DMA çıkışı var; ham Bayer karelerini doğrudan belleğe yazıyor, paketlemesi kapatıldığında düz 16 bitlik örnekler olarak - standart bir V4L2 ham biçimi. Başka bir donanım bloğuna gerek yok.
3. **`tools/kmod/j701f_camera.c`.** Her sensör için bir medya aygıtı, bir sensör alt aygıtı (pozlama ve kazanç denetimleri) ve bir yakalama video düğümü. Alıcı sırayla iki arabelleğe yazar, küçük bir iş parçacığı biten her kareyi uygulamaya kopyalar.
4. **libcamera** (Alpine'in paketi, değiştirilmemiş): genel işlem hattı ve yazılımsal görüntü işleme; sonra uygulama.

## Bulunması gerekenler

- **Saatler.** Kamera bloğunun saat denetleyicisinin bizim ağacımızda sürücüsü yok ve önyükleyici seçicilerini 26 MHz osilatörde bırakıyor. Üç seçici gerçek saatlere çevrilene kadar kareler sağlama hatalarıyla geliyordu.
- **Bloğun IOMMU'su**, video çözücününki gibi, sayfa tablosu olmadan etkin başlıyor; sürücü yakalama sırasında onu adresleri geçirecek şekilde ayarlıyor.
- **Ön kameranın alıcısı**, sensör yayın yaptığı halde hiçbir şey görmüyordu: üreticinin PHY sürücüsü bir sistem yazmacında ana hat PHY sürücüsünün bilmediği bir bit daha kuruyor.
- **libcamera genel işlem hattında yalnızca bildiği platform sürücülerini kabul ediyor.** Bu yüzden medya aygıtı sürücü adını `qcom-camss` olarak veriyor; listede yazılımsal işlemesi açık olan bir giriş. Bunun dışında Qualcomm'la ilgisi yok; temiz seçenek, o listede bir satırı daha olan bir libcamera.
- **Bir dma-buf sağlayıcısı.** libcamera'nın yazılımsal işlemesi buna ihtiyaç duyuyor ve BOOT'taki çekirdekte yok; çekirdeğin `udmabuf` sürücüsü ayrı bir modül olarak derlendi, çekirdeğin dışa aktarmadığı bir işleve ihtiyaç duyan tek denetimi çıkarılarak.
- **GPU mu işlemci mi.** GPU yolunda libcamera'nın deneme programı bu telefonda yaklaşık her üç başlatmadan birinde durdu; oturum `LIBCAMERA_SOFTISP_MODE=cpu` ayarlıyor.

## Yolda yapılan hatalar

- İki sensörün paylaştığı bir GPIO'yu iki aygıttan "paylaşımlı" istemek, modül yeniden yüklendikten sonra bozuldu ve çekirdeği çökertti. Anahtar artık aygıt ağacında bir regülatör.
- Paketsiz düzenin bir denemesi arabelleğinin 140 kB ötesine yazdı: boyut koruması piksel başına baytı değil sensör kipini denetliyordu. Telefon hemen yeniden başlatıldı; arabellekler artık düzene göre boyutlanıyor.
- Yüklü bırakılan bir deneme modülü, ilk anlık çekim başlatıcılarının telefon sahibinde "FileNotFoundError" vermesine yol açtı.

## Eksikler

- Tam çözünürlük (şimdilik sensör başına tek kip), otomatik odak (arka mercek motoru sürülmüyor), çekim sırasında flaş.
- Sensör ayarı: renk matrisi ve mercek gölgeleme düzeltmesi yok; libcamera iki sensörü de tanımıyor ve bunu söylüyor.
- Otomatik pozlama yavaş tırmanıyor: loş bir odada resmin aydınlanması birkaç saniye sürüyor.
- Görüntü döndürmesi: arka kamera için ilk tahmin fotoğrafları tepetaklak verdi (telefon sahibinin bildirimi); şimdi 270°. Ön kameranın 90° değeri ayna varsayımıdır, denetlenmedi.
- Plasma Camera'da video kaydı boş dosya üretiyor; nedeni bulunamadı.
- Bloğun saatleri, güç alanı ve IOMMU'su için yazmaç yazımları yerine düzgün sürücüler; yoklama yerine alıcının kesmesi; kare başına kopyasız çalışma.
- libcamera yerine PipeWire'ın kamera kapısını ya da düz V4L2'yi kullanan uygulamalar denenmedi.

## Neresi nerede

| Yol | İçerik |
| --- | --- |
| `kernel/dts/exynos7870-j7velte-camera.dts` | iki sensör düğümü: hatlar, beslemeler, GPIO'lar, saatler, D-PHY'ler, yön |
| `tools/kmod/j701f_camera.c`, `s5k3l2-tables.h`, `s5k5e3-tables.h`, `gen-s5k3l2-tables.py` | sürücü ve dönüştürülmüş üretici tabloları |
| `tools/kmod/udmabuf-out-of-tree.patch` | çekirdeğin udmabuf sürücüsünü modül olarak derlemek için yapılan değişiklik |
| `system/camera/` | modüllerin açılış yükleme betiği, udev kuralı, oturum ortamı; `j701f-photo` (önceki anlık çekim aracı) |
| `tools/kmod/j701f_cam_probe.c`, `j701f_cam_frame.c`, `j701f_cam_stream.c` | devreye alma sırasındaki üç deneme modülü |
| `build/kernel/vendor-camera-reference/` | başvurulan üretici dosyaları (deponun parçası değil) |
