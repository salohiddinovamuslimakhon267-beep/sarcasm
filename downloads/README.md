# Yuklab olish — dataset v1.1

- **sarcasm_dataset_v1_1.zip**: barcha tayyorlangan jadvallar, annotatsiya fayllari,
  manba/yorliq tarixi va SQLite reyestri. SQLite `registry.sqlite.xz` shaklida
  qo‘shimcha siqilgan; Excel va CSV lar ZIP ichida to‘g‘ridan-to‘g‘ri ochiladi.
- **Skrinshot_izohlari_v1_1.xlsx**: yangi 124 izohning birlashtirilgan jadvali.
- **annotation_A.xlsx**, **annotation_B.xlsx**: ikki mustaqil annotator uchun
  eski yorliqlari ko‘rsatilmagan 2 792 ta bir xil topshiriq.
- **screenshot_second_review_blind.csv**: yangi 124 izoh uchun oldingi yorliqlarsiz
  mustaqil qayta baholash fayli.
- **sarcasm_pipeline_code.zip**: datasetni tayyorlash kodi.
- **SHA256SUMS.txt**: yuklab olingan fayllarni tekshirish uchun hashlar.

Umumiy reyestr: 155 578 noyob matn, 652 256 asl matn nusxasi. Bu tayyorlash
versiyasi: eski yorliqlar va yangi dastlabki annotatsiyalar inson-gold baholash
to‘plami sifatida tasdiqlanmagan. `Noaniq` yozuvlar `0` deb olinmagan.

SQLite kerak bo‘lsa, ZIP ochilgach `prepared_v1_1` katalogida quyidagini bajaring:

```bash
python -c "import lzma,shutil; s=lzma.open('registry.sqlite.xz','rb'); d=open('registry.sqlite','wb'); shutil.copyfileobj(s,d); s.close(); d.close()"
```

Yuklab olish uchun GitHub fayl sahifasidagi **Download raw file** tugmasini bosing
(yoki Release izohidagi to‘g‘ridan-to‘g‘ri havolalardan foydalaning).
