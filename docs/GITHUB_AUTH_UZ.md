# GitHub yozish huquqini ulash

1. https://github.com/settings/personal-access-tokens/new ni oching.
   GitHub sozlamalarida: Developer settings → Personal access tokens → Fine-grained tokens.
2. Resource owner: `salohiddinovamuslimakhon267-beep`. Token nomi va amal qilish
   muddatini tanlang. Repository access → Only select repositories → `sarcasm`.
3. Repository permissions → Contents → Read and write. Metadata read-only
   avtomatik bo‘lishi mumkin. Generate token.
4. Tokenni shu Codex ish muhitining maxfiy credential/secret sozlamasiga kiriting.
   Mavjud `GH_TOKEN` qiymatini yangilang. Tokenni chatga yoki Git fayliga yozmang.
   Sozlama tashqi HTTP credential domenlarini so‘rasa, GitHub API va yuklash uchun
   `github.com`, `api.github.com`, `uploads.github.com` ishlatiladi.
5. Sozlamani saqlang va shu ish muhitiga qo‘llang. Muhitdagi tekshiruv:

```bash
gh auth status
gh api repos/salohiddinovamuslimakhon267-beep/sarcasm --jq '.permissions.push'
```

Muvaffaqiyatli autentifikatsiya va `true` yozish huquqini bildiradi.
Fine-grained token faqat tanlangan repozitoriy va tanlangan muddat uchun bo‘lsin.
Ish muhitida `Secrets`/`Credentials` sozlamasi ko‘rinmasa, ishlatilayotgan Codex
ilovasi va sozlamalar oynasi nomini aniqlashtirish kerak; yo‘q menyuni taxmin qilmang.

Dataset fayli 100 MiB dan katta; Release asset sifatida yuklanadi:

```bash
bash scripts/publish_dataset_release.sh /absolute/path/to/work/delivery
```

Skript autentifikatsiyani avval tekshiradi, kod branchini push qiladi, dataset
Release assetini yuklaydi va haqiqiy yuklab olish havolalarini chiqaradi.
Mavjud yangi v1.1 arxivini avtomatik tanlaydi. Git credential helper sifatida
`gh auth git-credential` faqat shu push buyrug‘i uchun qo‘llanadi.
