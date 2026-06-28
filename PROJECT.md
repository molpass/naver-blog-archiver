# PROJECT — naver-blog-archiver (master plan)

> Placeholder. The full master plan is delivered separately (Chat). S0 reserves this slot and
> records the S0 reconnaissance outcome below so the next slice starts grounded.

## Stages

- **S0 정찰+스캐폴드** — repo skeleton + recon (this slice). PASS gate met (see catchback).
- **S1 목록 수집기** — collect every logNo across all pages → full index JSON.
- **S2 본문→md (소량)** — parse representative posts (se- components) → md + images.
- **S3 전량 크롤링** — all posts + images, mannerly, resumable, verified against the index.
- **S4 워드프레스** — category-preserving export, comments off.
- **S5 (옵션)** — DeepInfra tags/summary enrichment.

1차 완료선 = S3 (local md archive in hand).

## S0 reconnaissance outcome (decisions for PM)

See `DOC/recon-S0.md` (gitignored) for the full data. Headlines:

1. **The "50-post wall" is NOT reproduced.** `PostTitleListAsync.naver?categoryNo=0` reports
   the true total and paginates fully (deep page verified) — each item already carries its
   `categoryNo`. The upstream list logic completes pagination; it only ever queries
   `categoryNo=0`, which turns out to be sufficient for completeness. S1 is a single
   `categoryNo=0` sweep + a categoryNo→name map (mobile category API), not a per-category
   crawl to "break 50".

2. **betarixm dependency is non-trivial.** Upstream has **no LICENSE**, is poetry-only (not on
   PyPI), and pins **python ^3.12** (our stack is >=3.11). Options: pip-from-git (drags
   3.12 + unlicensed), vendoring (blocked for a public repo by the missing license), or a
   clean-room reimplementation of the `se-` parser (we control license/python; it's the main
   value we need). **Recommendation: clean-room parser, betarixm as reference only** — pending
   PM decision.

3. **WordPress (S4):** no reusable importer/category-map exists in the zeolinex repos; the
   prior 51-post showcase was a one-off (Naver MD 수집 → 카테고리 분류). S4 designs fresh.
