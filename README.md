# Matvey Dubai AI Agent

Telegram AI agent for Dubai residential and commercial real estate.

## Current capabilities in code
- Multilingual text conversations and language-aware voice transcription/replies.
- Per-chat conversation history.
- Structured CRM tables for owner listings, client enquiries and partner agents.
- Direct-listing URL guard for Bayut, Property Finder and Dubizzle generic pages.
- Administrator-only diagnostics and CRM export.
- Specialist child-agent profiles with isolated conversation histories and dedicated Telegram webhooks.

## Required environment variables
- `TELEGRAM_TOKEN`: main BotFather token.
- `OPENAI_API_KEY`: OpenAI API key.
- `ADMIN_TELEGRAM_IDS`: comma-separated numeric Telegram user IDs authorized for administrator mode.
- `MATVEY_DB_PATH`: optional SQLite path. For Render persistence, mount a persistent disk and point this to its mount path, e.g. `/var/data/matvey_objects.db`.

Each child-agent profile declares its own token environment variable, such as `TELEGRAM_TOKEN_LEASING_SPECIALIST`. Add the corresponding BotFather token as a protected Render environment variable, then run `/activateagent leasing_specialist` as an authorized administrator.

## Administrator commands
- `/myid`
- `/adminstatus`
- `/stats`
- `/exportdb`
- `/agents`
- `/createagent Name | Specialization | Language | Extra instructions`
- `/trainagent agent_key | Additional instructions`
- `/activateagent agent_key`

A child-agent profile is not a running bot until a separate BotFather token is configured and Telegram confirms its webhook.

## Verification
Run:
```bash
python -m py_compile main.py
python -m unittest discover -s tests -v
```
