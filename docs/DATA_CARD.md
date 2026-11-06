# Dataset card — preparation v1

Status: private preparation artifacts, **not a released human-gold benchmark**.
Languages: Uzbek intended; Latin/Cyrillic, mixed language and non-Uzbek content
remain. Script presence is not a language detector. Task: binary presence of
irony/sarcasm, plus uncertain human annotation.

Original sources: supplied workbooks and Comments.zip. File checksums, sheet names,
row numbers and original decisions are retained. Source text may be copyrighted
or personal; no license for redistribution is assumed. Code and aggregate
summaries may be kept separately from private data.

Key limitations: automated zeros mean non-detection, LLM labels are not independent
human judgments, old Neutral annotations are uniform placeholders, synthetic
examples follow limited templates, purported Instagram raw workbook substantially
overlaps YouTube, Telegram is PUBG-heavy, video titles/parent comments may be
unavailable. Existing small "Verified" labels require re-annotation.

Safety of evaluation: frozen video groups, multivideo-text quarantine, no synthetic
evaluation rows, no unconfirmed row marketed as gold. Exact normalized duplicates
are handled; semantic/near duplicates still need audit. Source/platform/domain
coverage remains skewed. No production accuracy claim is made.

For screenshots: retain image provenance privately, manually validate transcription,
record sampling selection, recover post/thread context and collect non-sarcastic
controls. Positive-only screenshots cannot establish natural class prevalence.

Versioning: preserve input hashes, normalization version, code commit, seed, split
map, review history and human resolution. Adding new sources requires reviewing
cross-source duplicates and frozen test membership before building a new version.
