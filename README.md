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

Up to 50 child-agent profiles can be created. Profiles can be created either with the `/createagent` command or a natural-language administrator instruction. Each child-agent profile declares its own token environment variable, such as `TELEGRAM_TOKEN_LEASING_SPECIALIST`. Add the corresponding BotFather token as a protected Render environment variable, then run `/activateagent leasing_specialist` as an authorized administrator.

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


## Telegram group lead monitoring (new)
- Add Matvey to each permitted Telegram group. Group message visibility requires Telegram BotFather privacy mode to be disabled for the bot, or the bot to be made an administrator where appropriate; group administrators must authorize the addition.
- Configure `TELEGRAM_MONITORED_CHAT_IDS` as a comma-separated allow-list of numeric group chat IDs. The bot silently ignores all groups not on this list and never replies into monitored community groups.
- Group messages are screened for real-estate intent, then GPT classifies owner/renter/buyer/agent signals. Only qualifying, deduplicated messages are stored in `group_property_leads`.
- Source message links are saved where Telegram exposes a public group username or a private supergroup message path.
- Optional WhatsApp Cloud API owner alerts require protected environment variables: `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, and `WHATSAPP_OWNER_NUMBER`. Optional `WHATSAPP_GRAPH_API_VERSION` defaults to `v21.0`.
- WhatsApp credentials and group IDs are not created automatically. Add them securely in the hosting environment. Respect group rules, user privacy and Telegram anti-spam requirements.
- This integration does not join groups by link, bypass private-group access, or scrape historical messages. It processes new messages delivered to the configured bot webhook after the bot has been added and authorized.
