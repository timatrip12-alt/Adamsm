# Telegram Link Checker Bot

This repository contains a Telegram bot that validates t.me links from uploaded
text files. The bot uses Telethon for link validation and python-telegram-bot
for the bot API.

## One-time session setup

Before running the bot, create a Telethon session in your terminal:

```
python create_session.py
```

This script stores the session string in `config.json`. Keep this file private.

## Run the bot

```
python bot.py
```

## Bot usage

1. Start the bot with `/start`.
2. Upload a `.txt` file containing t.me links.
3. Receive a file with valid links.

## Notes

- If you prefer authorizing inside the bot, `/auth_telethon` is still available.
- Session data is stored in `config.json` and should not be committed.
