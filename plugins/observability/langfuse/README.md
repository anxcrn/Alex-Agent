# Langfuse Observability Plugin

This plugin ships bundled with Alex but is **opt-in** — it only loads when
you explicitly enable it.

## Enable

Pick one:

```bash
# Interactive: walks you through credentials + SDK install + enable
alex tools  # → Langfuse Observability

# Manual
pip install langfuse
alex plugins enable observability/langfuse
```

## Required credentials

Set these in `~/.alex/.env` (or via `alex tools`):

```bash
ALEX_LANGFUSE_PUBLIC_KEY=pk-lf-...
ALEX_LANGFUSE_SECRET_KEY=sk-lf-...
ALEX_LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or your self-hosted URL
```

Without the SDK or credentials the hooks no-op silently — the plugin fails
open.

## Verify

```bash
alex plugins list                 # observability/langfuse should show "enabled"
alex chat -q "hello"              # then check Langfuse for a "Alex turn" trace
```

## Optional tuning

```bash
ALEX_LANGFUSE_ENV=production       # environment tag
ALEX_LANGFUSE_RELEASE=v1.0.0       # release tag
ALEX_LANGFUSE_SAMPLE_RATE=0.5      # sample 50% of traces
ALEX_LANGFUSE_MAX_CHARS=12000      # max chars per field (default: 12000)
ALEX_LANGFUSE_DEBUG=true           # verbose plugin logging
```

## Disable

```bash
alex plugins disable observability/langfuse
```
