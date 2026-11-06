# Mustaqil annotatsiya yo‘riqnomasi

Maqsad: izohda kinoya/sarkazm borligini aniqlash. Dastlab ikkalasi bitta ijobiy
sinf; ular orasidagi nozik farq uchun hozir majburiy yorliq qo‘yilmaydi.

- `1`: yuzaki ma’no bilan nazarda tutilgan ma’no orasida sezilarli nomuvofiqlik,
  istehzo, masxara yoki kinoyali baho bor. Matn yoki berilgan kontekst dalil bo‘lsin.
- `0`: to‘g‘ridan-to‘g‘ri xabar, samimiy maqtov, oddiy iltimos, ochiq tanqid,
  haqorat yoki kinoyasiz hazil. `😂` yoki katta harflar o‘zi ijobiy yorliq emas.
- `uncertain`: kontekst yetarli emas yoki ikkala talqin ham asosli.

Sun’iy misollar:

| Matn | Yorliq | Sabab |
|---|---|---|
| Zo‘r xizmat, ikki soatdan beri hech kim javob bermadi. | 1 | Maqtov va vaziyat zid |
| Ikki soatdan beri javob bermadingiz, bu yomon xizmat. | 0 | To‘g‘ridan-to‘g‘ri tanqid |
| Rahmat, juda tez javob berdingiz! | uncertain | Kontekstsiz samimiy yoki kinoyali bo‘lishi mumkin |
| Tug‘ilgan kuning bilan 😂 | 0 | Kulgi emojisi sarkazmni isbotlamaydi |

`label`: `0`, `1`, `uncertain`.
`is_human`: insonning o‘zi bajargan ish uchun `true`.
`needs_context`: `true` yoki `false`.
`rationale`: qarorning qisqa sababi; `1` bo‘lsa kinoyani bildirgan qismni ko‘rsating.
`confidence`: ixtiyoriy 1–3; yagona doimiy 0.95 qo‘ymang. Importer bu ballni gold
maqomining o‘rniga ishlatmaydi.

A va B ikki turli inson bo‘lsin. Ular bir-birining javobini, oldingi model
natijasini va eski yorliqlarni ko‘rmasin. Ish boshlashdan oldin alohida 50 ta
pilot misolda ta’riflarni muhokama qiling; pilotni yakuniy testga qo‘shmang.

Koordinator avval annotatorlar kelishuvini va `uncertain` ulushini hisoblaydi,
keyin kelishmovchiliklarni kontekst bilan hal qiladi. `uncertain` ni majburan
`0` ga aylantirmang. Tasdiqlangan testni keyin modelga qarab qayta belgilamang;
xato topilsa, yangi dataset versiyasi va o‘zgarish sababini yozing.
