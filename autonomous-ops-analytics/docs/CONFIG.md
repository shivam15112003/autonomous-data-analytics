# Configuration

## Gemini modes
- `--gemini-mode off`     : fully local / deterministic
- `--gemini-mode api`     : Gemini API (requires key)
- `--gemini-mode browser` : Selenium browser automation

## API key
Provide an API key via file:
- `gemini_api_key.txt` (one line, ignored by git)

Or via environment variables:
- `GEMINI_API_KEY`
- `GOOGLE_API_KEY`

## Browser mode URLs
Override Gemini URLs via env vars:
- `GEMINI_URL` (Stage-1 browser)
- `GEMINI_STAGE2_URL` (Stage-2 browser)

Login gating:
- `GEMINI_REQUIRE_LOGIN=1` forces interactive login flow (not recommended for unattended runs)

Retry delay:
- `GEMINI_RETRY_DELAY_SECONDS` (default ~20s)

## Large CSV “big-mode”
(Only used if your pipeline supports it.)

Suggested environment variables:
- `OPS_BIGMODE_COL_THRESHOLD`   (default 2000)
- `OPS_BIGMODE_FILE_MB`         (default 800)
- `OPS_BIGMODE_SAMPLE_ROWS`     (default 1000)
- `OPS_BIGMODE_TOP_NUMERIC`     (default 300)
- `OPS_BIGMODE_TOP_CATEGORICAL` (default 40)

## Wide correlation guardrails
- `OPS_MAX_CORR_COLS` (default 500) limits correlation matrix size.

## Large clustering guardrails
- `OPS_CLUSTER_MAX_FIT_ROWS` limits how many rows are used for fitting when row counts are huge.
