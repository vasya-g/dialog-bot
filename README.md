# Telegram message mirror bot

Python bot built with [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI) that mirrors incoming Telegram updates to the configured owner chat.

## Features

- Works in private chats, groups, supergroups, and channels where the bot receives updates.
- Mirrors all message content types supported by `telebot` through a catch-all handler.
- Sends two notifications for each message:
  1. Telegram forward/copy of the original message.
  2. Detailed metadata with sent time, user ID, first name, last name, username, chat ID, message ID, and content type.
- Handles edited messages by sending the edited copy and replying to the previously mirrored notification when possible.
- Groups photo albums by `media_group_id` and copies all album items correctly.

## Important Telegram limitation

The Telegram Bot API does **not** deliver an update when an arbitrary user message is deleted from a chat. Because of that, a normal `telebot` bot cannot reliably detect deleted messages or send deletion-time notifications. The code keeps an in-memory mapping of mirrored messages so edit notifications can reply to the older mirrored copy, but delete detection would require an external client/userbot approach that is outside the Bot API.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

- `BOT_TOKEN` — token from BotFather.
- `OWNER_CHAT_ID` — your Telegram user ID or private chat ID where notifications should be sent.

## Run

```bash
python bot.py
```

For groups/supergroups, disable privacy mode in BotFather if you want the bot to receive all group messages.
