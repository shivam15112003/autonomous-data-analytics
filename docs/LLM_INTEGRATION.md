# LLM Integration

The LLM is the **reasoning/orchestration layer**. It decides methodology and interprets
evidence. It does not compute metrics, train models, or see raw row data beyond the
aggregated profile.

## Responsibilities

- **Stage 1**: given profile + method catalog, return a declarative JSON analysis plan.
- **Stage 2**: given computed results JSON, return narrative sections grounded in those numbers.

## Stage-1 prompt

Built by `build_stage1_prompt`: system instruction + `METHOD_CATALOG` + truncated
profile JSON (6000 chars) + optional target hint, ending with "Return ONLY the JSON plan object."

## Stage-2 prompt

Inline in `obtain_stage2_sections`: instruction to use only provided numbers plus the
results JSON (6000 chars). Expected keys: `executive_summary`, `key_findings`,
`recommendations`, `limitations`.

## Modes

| Mode | Implementation | Status |
|---|---|---|
| `off` | `build_default_plan` + `deterministic_sections` | **Implemented**, default, deterministic |
| `api` | `gemini_api_generate` (stdlib `urllib` POST to `generativelanguage.googleapis.com`) | **Implemented**; needs key |
| `browser` | `gemini_browser_generate` (Selenium Chrome) | **Implemented, experimental** |

Multi-LLM support (OpenAI, Claude, local models) is **architecturally extensible**
(swap `gemini_*_generate` for another client returning text) but **not implemented**.
Do not claim those providers as supported.

### Browser automation

Browser-based Gemini integration provides a cost-conscious experimentation path during
development, while API-based integration provides a conventional programmatic integration path.

- Intended primarily for experimentation/development, not unattended production.
- Depends on the external web UI (selectors may change; failures fall back to offline).
- May be less stable than the official API.
- Requires `pip install selenium` + a local Chrome; honors `GEMINI_URL`,
  `GEMINI_STAGE2_URL`, `GEMINI_BROWSER_PROFILE`, `GEMINI_REQUIRE_LOGIN`, `GEMINI_RETRY_DELAY_SECONDS`.
- Use according to applicable service terms/policies.

## Offline behavior and fallbacks

- `--gemini-mode off`: no network, no browser, fully deterministic.
- API/browser failure at either stage → validated default plan / template sections with
  `fallback-offline` source and a logged warning. The pipeline always completes locally
  when dependencies allow.

## Error handling

- `extract_json_object` tolerates markdown fences and surrounding prose; unparseable
  output triggers fallback rather than a crash.
- `validate_plan` drops unsupported values per-field and records warnings in
  `gemini_plan.json` — never executes LLM content (`no exec/eval` by design).

## Security

- API key lookup order: `--gemini-key-file` → `gemini_api_key.txt` → `GEMINI_API_KEY` → `GOOGLE_API_KEY`.
- Never commit `gemini_api_key.txt` (git-ignored). Only `gemini_api_key.txt.example` is tracked.
- Prompts send the aggregated profile and results summary, not full raw datasets.
- Browser mode uses a local profile directory; do not commit profile data or cookies.
