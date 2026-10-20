# 0004 — A provider-agnostic reader with no tools

Date: 2026-10-14. Status: accepted.

## Context
The hackathon reader worked only with AkashML. It sent `tool_choice`, `temperature` and `max_completion_tokens`, which Ollama and current Claude models don't accept.

## Decision
- **One seam.** `ReaderClient.complete(request) -> str`.
- **Two adapters.** An OpenAI-compatible one (httpx) covers OpenAI, Ollama, LM Studio, vLLM, OpenRouter, Groq and Gemini's compatible endpoint. An Anthropic one uses the official SDK as an optional extra.
- **Containment.** The model never gets tools. Its output must be exactly `{"flags": [...], "evidence": [...]}`, which leaves no field to put a verdict in. A per-call canary sits in the system prompt. There is one call per skill.
- **Off by default.** The user's own key is read from the environment variable they name.

## Consequences
- The reader can be talked into silence, but never into ALLOW.
- A provider's safety refusal is reported as its own reason.
- Every call is counted in the preflight before it is made (§6.6).
