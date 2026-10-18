# Anthropic auth conflict fix — bledi.tn
# Problem: both ANTHROPIC_AUTH_TOKEN and ANTHROPIC_API_KEY may be set.
# Per Anthropic docs: unset one.
# This file uses ANTHROPIC_API_KEY mode (token kept), so remove ANTHROPIC_AUTH_TOKEN.
# If switching to auth-token mode: unset ANTHROPIC_API_KEY, then `claude /logout` and say "No" to API key.
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL:-http://localhost:20128}
ANTHROPIC_MODEL=${ANTHROPIC_MODEL:-gemini/gemini-2.5-flash-lite}
# Unset auth token to avoid conflict; keep API_KEY
# (run: unset ANTHROPIC_AUTH_TOKEN  or  export ANTHROPIC_AUTH_TOKEN= before switching)
# Auth conflict note: both ANTHROPIC_AUTH_TOKEN and ANTHROPIC_API_KEY set breaks auth. Keep API_KEY only (current); unset ANTHROPIC_AUTH_TOKEN. If using auth-token mode: unset ANTHROPIC_API_KEY + claude /logout + say No. Session runs through 127.0.0.1:20128 — not eligible for new auto-mode billing.
