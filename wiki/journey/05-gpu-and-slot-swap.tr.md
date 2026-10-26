# 5. GPU ve bölüm takası

**Hedef:** donanım hızlandırmalı grafik, sonra da yeni çekirdeği telefonun normal çekirdeği yapmak.

## Panfrost

Bu telefondaki Mali-T830, ARM'ın "Midgard" ailesine ait. ARM'ın kendi sürücüsü kapalıdır ve yalnızca Android'e hizmet eder. **Panfrost** açık kaynaklı karşılığıdır: bir çekirdek sürücüsü ve Mesa içinde OpenGL ES sağlayan bir kullanıcı alanı parçası.

Panfrost'un başlaması için aygıt ağacının GPU'yu doğru tarif etmesi gerekir: yazmaç adresi (`0x11400000`), üç kesme, `CMU_G3D` saat denetleyicisinden gelen saatleri ve güç kaynağı (PMIC'in `BUCK2` regülatörü). Bunların her biri, açılmadan önce üretici çekirdeğinin canlı telefonda bildirdikleriyle karşılaştırıldı.

Bir endişe gereksiz çıktı. GPU kendi güç alanında durur ve mainline'da Exynos 7870'in güç alanları için sürücü yoktur. Ama önyükleyici o alanı açık bırakıyor, yani GPU'ya doğrudan erişilebildi.

Kanıt küçük bir sınama programıydı: `tools/panfrost-render-probe.c`. GPU'yu ekransız açar, 64×64'lük bir dokuya dama tahtası çizer, geri okur ve 4.096 pikselin hepsini karşılaştırır. Çıktısı:

```text
GL_RENDERER = Mali-T830 MC1 (Panfrost)
PANFROST_T830_RENDER_PASS
```

Böyle bir sınama önemlidir, çünkü "sürücü yüklendi" ile "GPU doğru pikseller çiziyor" farklı iddialardır.

## Bölümleri takas etmek

O ana kadar düzen *BOOT = üretici çekirdeği, RECOVERY = denemeler* idi. Mainline çekirdek kurulu sistemi başlatabildiğine göre roller tersine çevrildi:

| Bölüm | Önce | Sonra |
| --- | --- | --- |
| `BOOT` (normal açılış) | üretici 3.18 | **mainline** |
| `RECOVERY` (Power + Home + Ses Açma) | denemeler | **üretici 3.18, yedek olarak** |

Takas telefonun kendisinden, üzerine yazacağı şeyin özetini denetleyen, yazan ve her şeyi geri okuyan korumalı bir betikle yapıldı. Eski `BOOT` imajının bir kopyası telefonda ve bilgisayarda bir Odin arşivi olarak saklanıyor.

Bu düzenin çok pratik bir yararı var: **yeni çekirdekler kablo ya da Download Mode olmadan kurulabiliyor.** Yöntem şu hale geldi:

1. Çalışan mainline sistemden `RECOVERY`'deki üretici sistemine yeniden başlat.
2. Oradan yeni imajı `BOOT`'a yaz ve doğrula.
3. Normal biçimde yeniden başlat.

`tools/run-boot-update.sh` üçünü de ağ üzerinden yapar. Yeni bir çekirdek başarısız olursa, recovery tuş kombinasyonunu basılı tutmak üretici sistemini geri getirir; oradan önceki imaj yeniden yazılabilir. Bu güvenlik ağına gerçekten, birden fazla kez ihtiyaç duyuldu — bkz. [8. bölüm](08-sound.md).

## Dokunmatik

Dokunmatik ekran bir Melfas MIP4 denetleyicisi ve mainline'da sürücüsü var. Yine de bir parmağın bir şeyi oynatabilmesi için üç ayrı düzeltme gerekti:

1. **Yanlış kesme türü.** Aygıt ağacı "düşen kenar" diyordu; yonga ise okunana kadar hattını düşük tutar, yani "düşük seviye" gerekir. Yanlış ayarla ilk kesme son kesme oluyordu.
2. **Çok erken soruldu.** Sürücü yongayı, başlamayı bitirmeden sorguladı ve anlamsız yanıt aldı. Küçük bir yama sürücüye açabileceği bir güç kaynağı ve 300 ms'lik bir bekleme verir.
3. **Masaüstü tarafından reddedildi.** Yonga bir eksen için sıfır çözünürlük bildiriyordu; masaüstünün kullandığı girdi kitaplığı böyle aygıtları reddeder. Bir başka küçük yama eksik değeri diğer eksenden kopyalar.

Bunların hiçbiri hata iletisi olarak görünmezdi. Her biri gerçekte ne geldiğine bakılarak bulundu: kesme sayıları, ham paketler, girdi kitaplığının hata ayıklama çıktısı.

## Mainline'da Wi-Fi

Wi-Fi yongası SDIO veri yolundaki bir Broadcom BCM43430'dur; aygıt ağacında tarif edilip yazılım dosyaları verildiğinde mainline `brcmfmac` sürücüsü tarafından desteklenir. İki şey kaydedilmeye değer:

- "Ne olur ne olmaz" diye kopyalanan bir pin yapılandırması yonganın güç-etkinleştirme hattını düşüğe çekti ve onu kapalı tuttu. Fazladan yapılandırmayı kaldırmak sorunu çözdü. Daha fazla tarif her zaman daha iyi değildir.
- Yonganın gerçek MAC adresi, bu projenin hiç okumadığı EFS bölümünde durur. Bunun yerine aygıt ağacında sabit, yerel olarak yönetilen bir adres ayarlanır. Yan etkisi olarak yönlendirici telefona hep aynı IP adresini verir.

Depolama, GPU, dokunmatik ve ağ yeni çekirdekte çalışınca telefon bir masaüstü için hazırdı.
