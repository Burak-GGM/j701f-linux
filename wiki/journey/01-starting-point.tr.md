# 1. Başlangıç noktası

## Telefon

| | |
| --- | --- |
| Model | Samsung Galaxy J7 Neo / J7 Core, SM-J701F (`j7velte`) |
| Yonga seti | Samsung Exynos 7870, 8 × Cortex-A53 |
| GPU | ARM Mali-T830 MP1 |
| Bellek / depolama | 2 GB RAM (yaklaşık 1,6 GB kullanılabilir), 16 GB eMMC |
| Ekran | 720 × 1280 AMOLED, EA8061S panel |
| Fabrika yazılımı | Samsung 3.18 çekirdekli Android |

Böyle bir telefon, açılış süreci hiç de dost canlısı olmayan küçük bir bilgisayardır. BIOS menüsü yoktur, "USB'den başlat" yoktur. İlk çalışan program Samsung'un önyükleyicisi **S-BOOT**'tur ve yalnızca iki bölümden birinde duran, Android açılış imajına benzeyen bir şeyi başlatır: `BOOT` (normal açılış) ya da `RECOVERY` (Power + Home + Ses Açma basılıyken açılış).

## Hedef

Uzun vadeli hedef kullanılabilir bir Linux telefondu: güncel bir çekirdek, grafik bir masaüstü ve donanımın olabildiğince fazlası çalışır halde. Bu, tek adımda denenemeyecek kadar büyük; o yüzden iş, her biri bir sonrakine geçmeden önce *kanıtlanabilen* aşamalara bölündü:

1. Telefonda kendi yazdığımız herhangi bir programı çalıştırmak.
2. Komut yazabileceğimiz bir kabuk elde etmek.
3. Eski üretici çekirdeği üzerinde gerçek bir Linux dağıtımı çalıştırmak.
4. Üretici çekirdeğini güncel bir çekirdekle değiştirmek.
5. GPU'yu ve bir masaüstünü çalıştırmak.
6. Kalan donanımı sürücü sürücü ayağa kaldırmak.

## Hiç çiğnenmeyen kurallar

Telefonlar "tuğla" olabilir: özel donanım olmadan kurtarılamayacak bir duruma düşebilir. Birkaç kural bunun olmasını engelledi:

!!! danger "Asla yazılmayan bölümler"
    Bölüm tablosu (PIT), önyükleyici (BL / sboot), EFS (telefonun kimlik ve kalibrasyon verileri), TrustZone, modem yazılımı ve RPMB'ye hiç dokunulmaz. Yalnızca `BOOT`, `RECOVERY` ve `USERDATA` yazılır; onlar da ancak önce boyut ve özet (hash) denetimi yapan araçlarla.

- **Her zaman çalışan bir bölüm kalsın.** Denemeler açılabilir iki bölümden birine yapılır, diğeri bilinen sağlam sistemi tutar. Yeni çekirdek açılmazsa diğer bölümün tuş kombinasyonu telefonu geri getirir.
- **Yazmadan önce oku.** Bu portta kullanılan hemen her bilgi — bölüm boyutları, bellek düzeni, yazmaç adresleri, gerilimler — bir veri sayfasından alınmak ya da tahmin edilmek yerine önce çalışan telefondan okundu ve depoya kaydedildi.
- **Önce doğrula, sonra güven.** İmajlar sabitlenmiş özetlerle derlenir, bilgisayarda doğrulanır ve yazıldıktan sonra telefondan geri okunur.

## Masada ne olmalı

- Bir Linux bilgisayar, bir USB kablosu ve telefon.
- Download Mode'dan bölüm yazmak için [Odin](https://en.wikipedia.org/wiki/Odin_(firmware_flashing_software)) ya da Heimdall. Yalnızca en ilk imaj ve acil durumlar için gerekir.
- Başlangıç noktası olarak bu telefon için hazırlanmış bir özel recovery imajı. Proje bir **OrangeFox** recovery derlemesiyle başladı, çünkü içinde tam bu modelde açıldığı bilinen bir çekirdek ve aygıt ağacı var.

Sonraki bölüm bu recovery imajını söküp içine kendi programımızı koyuyor.
