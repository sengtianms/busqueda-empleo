---
sessionId: session-261112-173847-6v5p
---

# AI Models Summary

### Models Inventory

The user asked which AI models are currently used in the project, in which modules, and for what purpose. The answer was provided based on `config/config.yaml` and `config/.env.template`:

1. **`gemma4:31b-cloud`** (Gemma 4 31B) — Module 3 Evaluation, routed via `ai_cloud`. Three OpenRouter reserve doors with `google/gemma-4-31b-it`.
2. **`gpt-oss:120b-cloud`** (GPT-OSS 120B) — Module 2 Preparation (location classification), routed via `ai_local`. Three OpenRouter reserve doors with `openai/gpt-oss-120b`.
3. **`processing: cloud`** — reserved for future Module 4 (Phase 7, deferred).

No implementation changes are required. This is a read-only informational task.

# Delivery Steps

###   Step 1: Answer the user's question about AI models
The informational question has been fully answered. The response covers all AI models used in the project.