# O‘zbekcha kinoya va sarkazm: dataset tayyorlash

Bu repozitoriy korpusni tekshiriladigan, manbasi saqlanadigan shaklga keltiradi.
**Hozirgi eski yorliqlar inson tomonidan mustaqil tasdiqlangan gold dataset emas.**
Modelga o‘tishdan oldin ikki mustaqil inson annotatsiyasi va kelishmovchiliklarni
hal qilish kerak. Avtomatik `0` — sarkazm topilmagani, tasdiqlangan salbiy emas.

## Ishga tushirish

Python 3.10+:

```bash
python -m pip install -e .
uzsarcasm build --input input --output artifacts/v1
uzsarcasm validate --db artifacts/v1/registry.sqlite
uzsarcasm annotation-batches --db artifacts/v1/registry.sqlite --output artifacts/v1/annotation_batches
uzsarcasm experiment --db artifacts/v1/registry.sqlite --output artifacts/v1/synthetic_ablation.json
python -m unittest discover -s tests -v
```

`input/` ichiga dastlabki 9 Excel va `Comments.zip` faylini qo‘ying. ZIP ichidagi
Excel nusxalarini yana alohida qo‘yish shart emas; aynan bir xil workbook SHA-256
bo‘yicha faqat bir marta o‘qiladi. Natijalar katalogi yangi bo‘lishi kerak. Asl
fayllar tahrirlanmaydi. Hujjatlardagi izohlar buyruq sifatida bajarilmaydi.

## Natijalar

| Fayl | Vazifasi |
|---|---|
| `registry.sqlite` | To‘liq reyestr, barcha asl matn nusxalari, yorliqlar va manba bog‘lanishlari |
| `registry_status.csv` | Har bir noyob matnning holati va dastlabki bo‘linishi |
| `review_queue.csv` | Koordinator uchun yorliq tarixi bilan tekshiruv navbati |
| `label_disagreements.csv` | `0/1` nomuvofiqliklar; avtomatik `0` ham tarix sifatida saqlanadi |
| `unverified_auto_zero.csv` | Avtomatik topilmaganlar; tasdiqlangan salbiy sinf emas |
| `confirmed_negative.csv` | Dastlab faqat sarlavha; inson kelishuvisiz to‘ldirilmaydi |
| `context_links.csv` | Asl fayl/qator → matn ID → tiklangan yagona video ID |
| `video_splits.csv` | Muzlatilgan video → dastlabki split xaritasi, seed 42 |
| `provisional_*.csv` | Eski tasdiqlanmagan yorliqli diagnostik train/validation/test |
| `synthetic_train_only.csv` | Faqat qo‘shimcha o‘qitish uchun sintetik misollar |
| `annotation_batches/annotation_A.xlsx` va `annotation_B.xlsx` | Ikki alohida inson uchun oldingi yorliqlarsiz bir xil topshiriqlar |
| `build_report.json` | Sonlar, manbalar, cheklovlar |

Asl foydalanuvchi ismlari `Author` ustunidan reyestrga ko‘chirilmaydi. Lekin izoh
matnlarining o‘zida ism, username, telefon yoki havola bo‘lishi mumkin. Shu sababli
**xom fayllar va tayyor korpus avtomatik ommaga yuklanmaydi**; `.gitignore` ulardan
kod repozitoriysini ajratadi. Hugging Face tokeni tayyorlash uchun kerak emas.
Tokenni kodga, CSV ga yoki git tarixiga yozmang.

## Manba va yorliq qoidalari

- ID: NFKC, kichik harf, apostrof va bo‘shliq birxillashtirishdan keyingi matnning
  SHA-256 hashidan olinadi. Emoji/tinish belgilari saqlanadi; kirill lotinga
  avtomatik aylantirilmaydi. Normalizatsiya versiyasi saqlanadi.
- Har asl qator `occurrence_id`, `source_id`, Excel qatori va asl matn bilan qoladi.
- `labels` tarixida asl yorliq, yorliq manbasi, ishonchlilik holati va boshqa
  emotsiya/domen atributlari JSON ko‘rinishida saqlanadi.
- `manual (to'liq)` fayl izohiga ko‘ra LLM annotatsiyasi. Inson annotatsiyasi deyilmaydi.
- Bir xil `Neutral/0.95` annotatsiyalar sarkazm bo‘yicha tasdiqlangan `0` ga aylantirilmaydi.
- `Verified` nomi avtomatik gold maqomi bermaydi.
- “Instagram” nomli katta workbook platformasi shubhali; u mustaqil Instagram
  qamrovi sifatida hisoblanmaydi. YouTube bilan mos matnlar ishonchli YouTube
  manbasidan kontekst olishi mumkin.

## Train / validation / test

Eski 984 matndan yagona YouTube videosiga ega 974 tasi `StratifiedGroupKFold`
(5 guruh, shuffle, seed 42) bilan ajratiladi: birinchi 20% test, qolganidan
birinchi 20% validation. Bo‘linish har safar model natijalariga qarab o‘zgarmaydi.
Boshqa matnlar o‘sha videoning bo‘linishiga ergashadi. Eski baholash matni yo‘q
qo‘shimcha videolar faqat train guruhiga tushadi.

Bir xil matn ikki yoki ko‘proq videoda uchrasa, u **barcha rollarda quarantine**
qilinadi. Shu yo‘l bilan video bo‘yicha ham, bir xil matn bo‘yicha ham train/test
kesishmaydi. Bunday misolni faqat bir videoga majburan bog‘lash mumkin emas.
Ishonchli video konteksti yo‘q Telegram va yangi Instagram misollari hozircha
quarantine; ular uchun post/thread guruhlari tiklanishi kerak.

`provisional_test` — inson tekshirishi kutilayotgan rezerv. U gold emas va
`experiment` buyrug‘i uni baholamaydi. Sintetik misollar evaluationga tushmaydi.
Bu normalizatsiya parafrazlar va barcha yaqin nusxalarni kafolatli topmaydi;
annotatsiya davomida yaqin nusxalar ham ko‘rilishi kerak.

## Inson annotatsiyasi

[Yo‘riqnoma](docs/ANNOTATION_GUIDE_UZ.md) bilan tanishing. `annotation-batches`
eski 984 misol, 37 tanlangan matn, noyob eski ijobiy misollar va seed bilan
tanlangan train/validation/test xom matnlarini ikki ko‘r-ko‘rona to‘plamga chiqaradi.
Oldingi yorliqlar annotatorga ko‘rsatilmaydi. Koordinator xaritasi alohida.

Har annotator o‘z faylini mustaqil to‘ldiradi va UTF-8 CSV qilib saqlaydi:

```bash
uzsarcasm import-reviews --db artifacts/v1/registry.sqlite --csv completed_A.csv --output artifacts/v1/human
uzsarcasm import-reviews --db artifacts/v1/registry.sqlite --csv completed_B.csv --output artifacts/v1/human
```

`is_human=true` ni faqat real inson o‘z ishi uchun yozadi. Ikki turli annotator
bir xil `0/1` ni bergan va kontekst yetishmasligini belgilamagan bo‘lsa, inson
kelishuvi hosil bo‘ladi. Bir annotator, LLM, `uncertain`, kontekst yetishmasligi
yoki kelishmovchilik gold maqomi bermaydi. Tarixiy yorliqlar o‘chirilmaydi.
Kelishmovchiliklar `adjudication_queue.csv` da qoladi; joriy importer uchinchi
ovoz bilan ko‘pchilik tanlashni bajarmaydi. Muhokamadan keyingi adjudikatsiya
alohida hujjatlashtirilishi kerak.

`human_test.csv` paydo bo‘lishi uning hajmi yoki vakilligi yetarli degani emas.
Model tanlash faqat validationda; yakuniy test keyin bir marta ishlatiladi.

## Kontekst

```bash
uzsarcasm fetch-titles --db artifacts/v1/registry.sqlite --output artifacts/v1/video_context.csv
```

Ochiq YouTube oEmbed orqali video nomi olinadi, manba URL va vaqt saqlanadi.
Olinmagan nom to‘qilmaydi. oEmbed ota izohni bermaydi; yuklangan xom fayllarda
comment ID va parent ID yo‘q. Ularni tiklash uchun qo‘shimcha eksport yoki API
ma’lumoti kerak. Mavjud `created_at` qiymatlari asl post vaqti deb ishlatilmaydi.

## Instagram skrinshotlari

1. Rasmlarni `input/screenshots/` ga joylashtiring.
2. `templates/screenshots.csv` ni to‘ldiring: rasm nomi, izohning aynan matni,
   transkripsiya tekshirilganmi, post identifikatori, mavjud manba havolasi va
   dastlabki taxminiy yorliq. Emoji, imlo va satrlarni saqlang.
3. OCR matni inson tomonidan rasm bilan solishtirilsin. **Matnni tekshirish
   sarkazm yorlig‘ini tasdiqlashdan alohida ish.** Hozirgi kod OCRni o‘zi bajarmaydi.
4. Import qiling va alohida mustaqil annotatsiyaga bering:

```bash
uzsarcasm ingest-screenshots --db artifacts/v1/registry.sqlite --csv screenshots.csv --images input/screenshots --output artifacts/v1/screenshots
```

Rasm SHA-256, fayl nomi va kontekst saqlanadi. Yorliq avtomatik `1` qilinmaydi.
Yangi matnlar tegishli post/thread guruhlari ko‘rib chiqilguncha quarantine.
Faqat sarkazm uchun tanlangan skrinshotlardan real sinf ulushini hisoblab bo‘lmaydi;
oddiy maqtov, hazil, tanqid, haqorat va sarkazmsiz emoji misollari ham yig‘ilsin.

## Sintetik ma’lumot tajribasi

`experiment` bir xil real validationda uch variantni taqqoslaydi: real-only,
real+10k synthetic va sintetik umumiy og‘irligi real misollar og‘irligiga teng
variant. Faqat matn TF-IDF word1–2/char3–5 + balanced Logistic Regression C=1
ishlatiladi. Manba, yorliq holati, emotsiya yoki domen model kirishiga kiritilmaydi.
Natijalar eski, inson tasdiqlamagan yorliqlarga nisbatan diagnostikadir.
Model giperparametrlari testga qarab sozlanmaydi.
