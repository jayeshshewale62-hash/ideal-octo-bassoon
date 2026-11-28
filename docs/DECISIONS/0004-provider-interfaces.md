# ADR 0004: Provider interfaces, disabled by default

**Status:** Accepted (Milestone 2)

## Decision
- Four provider kinds: `image`, `tts`, `asr`, `llm`. Each has an abstract interface with
  typed request/result dataclasses.
- Every kind ships `none` (disabled: `enabled` is False and calls raise
  `ProviderUnavailableError`) and `mock` (deterministic, offline, used in tests).
- Real providers are listed in the catalogue as *planned*, with a milestone. Selecting one
  raises a clear `ProviderUnavailableError` instead of failing later.
- Selection comes from `config/providers.yaml`, overridden by a project's `settings.yaml`.
- `allow_network: false` (the default) makes every network provider unavailable. Turning
  it on needs owner approval.
- Credentials are read only from environment variables listed in `credentials_env`.
  Secret-looking option names fail validation. Error messages name the missing variables
  and never print values.
- Generated outputs carry provenance, which the asset schema requires for `ai_generated`
  assets.
