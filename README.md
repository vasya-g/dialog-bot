# Telegram Business secretary mirror bot

Python bot built with [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI) for Telegram Business “secretary/chatbot” mode. When you connect the bot in **Telegram Settings → Business → Chatbots** and give it access to your private chats, Telegram sends those personal-chat events to the bot as Business updates.

## Features

- Reads private chats made available to the bot through Telegram Business chatbot/secretary automation.
- Also supports ordinary bot chats where the bot is directly present.
- Mirrors all message content types supported by `telebot` through catch-all regular and Business handlers. For Business messages the bot re-sends content by `file_id`/text instead of relying on ordinary `forwardMessage`, because Business chats are separate from normal bot chats.
- Sends two notifications for each message:
  1. Telegram forward/copy of the original message when the Bot API allows it.
  2. Detailed metadata with sent time, user ID, first name, last name, username, chat ID, message ID, business connection ID, and content type.
- Handles edited regular and Business messages by sending the edited copy and replying to the previously mirrored notification when possible.
- Handles Telegram Business deletion updates (`deleted_business_messages`) and replies to the previously mirrored message with deletion time, chat data, business connection ID, and deleted message ID.
- Groups photo albums by `media_group_id` and copies all album items correctly.

## Important Telegram Business notes

- The bot must have Business Mode enabled in BotFather.
- Connect it from the Telegram account whose private chats you want to monitor: **Settings → Business → Chatbots**.
- Grant access to the chats you want the bot to process, including permission to read messages. If Telegram only delivers deletion events, reconnect the bot in Business settings and check the granted chat access/rights.
- For Business deletion updates, Telegram sends chat ID and message IDs, but not the full original deleted message object. This bot replies to the earlier mirrored notification when it has it in memory, so the sender details remain visible in the thread.
- The in-memory message map is reset when the process restarts. Use persistent storage if you need deletion/edit replies to survive restarts.

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

For ordinary groups/supergroups, disable privacy mode in BotFather if you want the bot to receive all group messages. This is separate from Telegram Business private-chat automation.
