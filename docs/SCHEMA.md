# Registry schema

- `sources`: original workbook/member/sheet, SHA-256, rows and role.
- `texts`: deterministic normalized text ID, representative text, quality flags.
- `occurrences`: every nonempty original row, original text, source row/key,
  declared/resolved platform, status, original video/post IDs, time and likes.
- `labels`: append-only original label, binary candidate if meaningful, original
  label-source string, verification status, origin, original attributes JSON.
- `registry_status`: aggregated candidate disagreements, automatic non-detections,
  human verification/confirmed-negative indicators, reliable video count,
  group, frozen provisional split or quarantine reason.
- `post_links`, `tokens`, `cues`, `post_cues`, `legacy_annotations`: original
  auxiliary relations, not inferred linguistic or human correctness.
- `context`: video title retrieval result/source/time; missing parent status.
- `video_splits`: one provisional partition per video, seed 42.
- `human_reviews`, `human_resolution`: created on explicit human import; originals
  are not overwritten. Two independent, agreeing human labels required.
- `screenshot_evidence`: created on screenshot import; image checksum, transcription
  status, post key, source URL and selection-bias note.

`has_label_conflict` means historical binary candidates disagree, including weak
machine non-detections. It does not mean equally credible human judgments disagree.
The latter is represented by unresolved `human_resolution` after human import.

SQL examples:

```sql
-- Provenance of one text, including every original row
SELECT * FROM occurrences WHERE text_id = :text_id;
SELECT * FROM labels WHERE text_id = :text_id;

-- Existing automatic zero must not be treated as a confirmed negative
SELECT count(*) FROM labels WHERE verification_status='auto_not_detected';
SELECT count(*) FROM registry_status WHERE confirmed_negative=1;

-- Metadata to investigate, not missing context to fabricate
SELECT * FROM context WHERE title_status <> 'fetched';
```
