"""Telegram message mirror bot using pyTelegramBotAPI.

The bot copies/forwards every message it can receive to the configured owner
chat and sends a metadata notification. Telegram's Bot API does not expose
regular message deletion events. Telegram Business, however, sends
deleted_business_messages updates for connected private chats.
"""

from __future__ import annotations

import os
import threading
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
from typing import DefaultDict

import telebot
from dotenv import load_dotenv
from telebot import types

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_CHAT_ID = int(os.environ["OWNER_CHAT_ID"])
ALBUM_FLUSH_DELAY = float(os.getenv("ALBUM_FLUSH_DELAY", "1.2"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Maps original (chat_id, message_id) to the first notification message sent to
# the owner. It lets edited-message notifications reply to the old copy.
mirrored_messages: dict[tuple[str, int, int], int] = {}

# Buffers media groups because Telegram sends album items as separate updates.
album_buffer: DefaultDict[str, list[types.Message]] = defaultdict(list)
album_timers: dict[str, threading.Timer] = {}
album_lock = threading.Lock()

ALL_CONTENT_TYPES = [
    "text",
    "audio",
    "document",
    "photo",
    "sticker",
    "video",
    "video_note",
    "voice",
    "location",
    "contact",
    "venue",
    "animation",
    "dice",
    "poll",
    "new_chat_members",
    "left_chat_member",
    "new_chat_title",
    "new_chat_photo",
    "delete_chat_photo",
    "group_chat_created",
    "supergroup_chat_created",
    "channel_chat_created",
    "migrate_to_chat_id",
    "migrate_from_chat_id",
    "pinned_message",
    "invoice",
    "successful_payment",
    "connected_website",
    "passport_data",
    "proximity_alert_triggered",
    "video_chat_scheduled",
    "video_chat_started",
    "video_chat_ended",
    "video_chat_participants_invited",
    "web_app_data",
    "message_auto_delete_timer_changed",
    "forum_topic_created",
    "forum_topic_closed",
    "forum_topic_reopened",
    "forum_topic_edited",
    "general_forum_topic_hidden",
    "general_forum_topic_unhidden",
    "write_access_allowed",
    "users_shared",
    "chat_shared",
    "story",
    "external_reply",
    "quote",
    "paid_media",
    "giveaway_created",
    "giveaway",
    "giveaway_winners",
    "giveaway_completed",
    "boost_added",
    "chat_background_set",
    "checklist",
    "checklist_tasks_done",
    "checklist_tasks_added",
]


def format_user(user: types.User | None) -> str:
    """Return HTML metadata for a Telegram user."""
    if user is None:
        return "<b>User:</b> unknown"

    username = f"@{user.username}" if user.username else "—"
    return "\n".join(
        [
            f"<b>User ID:</b> <code>{user.id}</code>",
            f"<b>First name:</b> {escape(user.first_name or '—')}",
            f"<b>Last name:</b> {escape(user.last_name or '—')}",
            f"<b>Username:</b> {escape(username)}",
        ]
    )


def format_message_info(message: types.Message, event: str = "New message") -> str:
    """Build detailed HTML notification for a message."""
    sent_at = datetime.fromtimestamp(message.date, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )
    edit_at = ""
    if getattr(message, "edit_date", None):
        edited_at = datetime.fromtimestamp(message.edit_date, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        edit_at = f"\n<b>Edited at:</b> {edited_at}"

    return "\n".join(
        [
            f"<b>{escape(event)}</b>",
            f"<b>Sent at:</b> {sent_at}{edit_at}",
            f"<b>Chat:</b> {escape(message.chat.title or message.chat.first_name or str(message.chat.id))}",
            f"<b>Chat ID:</b> <code>{message.chat.id}</code>",
            f"<b>Message ID:</b> <code>{message.message_id}</code>",
            f"<b>Business connection:</b> <code>{escape(str(getattr(message, 'business_connection_id', '—') or '—'))}</code>",
            f"<b>Type:</b> <code>{escape(message.content_type)}</code>",
            format_user(message.from_user),
        ]
    )


def copy_or_forward_message(message: types.Message, reply_to_message_id: int | None = None) -> int | None:
    """Forward the message to preserve Telegram navigation, falling back to copy."""
    try:
        forwarded = bot.forward_message(
            OWNER_CHAT_ID,
            message.chat.id,
            message.message_id,
        )
        return forwarded.message_id
    except telebot.apihelper.ApiTelegramException:
        copied = bot.copy_message(
            OWNER_CHAT_ID,
            message.chat.id,
            message.message_id,
            reply_to_message_id=reply_to_message_id,
        )
        return copied.message_id


def send_metadata(message: types.Message, event: str, reply_to_message_id: int | None = None) -> int:
    """Send detailed information about the message to the owner."""
    details = bot.send_message(
        OWNER_CHAT_ID,
        format_message_info(message, event),
        reply_to_message_id=reply_to_message_id,
        disable_web_page_preview=True,
    )
    return details.message_id


def mirror_message(message: types.Message, event: str = "New message") -> None:
    """Mirror a single message and remember its owner-side notification."""
    if message.from_user and message.from_user.is_bot:
        return

    business_connection_id = getattr(message, "business_connection_id", None) or "regular"
    original_key = (business_connection_id, message.chat.id, message.message_id)
    previous_owner_message_id = mirrored_messages.get(original_key)
    owner_copy_id = copy_or_forward_message(message, previous_owner_message_id)
    metadata_id = send_metadata(message, event, owner_copy_id or previous_owner_message_id)
    mirrored_messages[original_key] = owner_copy_id or metadata_id


def flush_album(media_group_id: str) -> None:
    """Send a complete album after Telegram delivers all media group items."""
    with album_lock:
        messages = album_buffer.pop(media_group_id, [])
        album_timers.pop(media_group_id, None)

    for index, message in enumerate(sorted(messages, key=lambda item: item.message_id), start=1):
        mirror_message(message, f"New album item {index}/{len(messages)}")


def buffer_album_message(message: types.Message) -> bool:
    """Buffer album messages and return True when processing is deferred."""
    media_group_id = getattr(message, "media_group_id", None)
    if not media_group_id:
        return False

    with album_lock:
        album_buffer[media_group_id].append(message)
        old_timer = album_timers.get(media_group_id)
        if old_timer:
            old_timer.cancel()

        timer = threading.Timer(ALBUM_FLUSH_DELAY, flush_album, args=(media_group_id,))
        timer.daemon = True
        album_timers[media_group_id] = timer
        timer.start()
    return True


@bot.message_handler(content_types=ALL_CONTENT_TYPES)
def handle_message(message: types.Message) -> None:
    """Catch all regular messages that Telegram sends to the bot."""
    if buffer_album_message(message):
        return
    mirror_message(message)


@bot.edited_message_handler(content_types=ALL_CONTENT_TYPES)
def handle_edited_message(message: types.Message) -> None:
    """Send edited regular messages as replies to the previous mirrored notification."""
    mirror_message(message, "Message edited")


@bot.business_message_handler(content_types=ALL_CONTENT_TYPES)
def handle_business_message(message: types.Message) -> None:
    """Catch messages from private chats connected through Telegram Business."""
    if buffer_album_message(message):
        return
    mirror_message(message, "New business message")


@bot.edited_business_message_handler(content_types=ALL_CONTENT_TYPES)
def handle_edited_business_message(message: types.Message) -> None:
    """Catch edited messages from Telegram Business private chats."""
    mirror_message(message, "Business message edited")


def format_deleted_business_message(deleted: types.BusinessMessagesDeleted, message_id: int) -> str:
    """Build a deletion notification for a Telegram Business deleted message."""
    deleted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return "\n".join(
        [
            "<b>Business message was deleted</b>",
            f"<b>Deleted at:</b> {deleted_at}",
            f"<b>Business connection:</b> <code>{escape(deleted.business_connection_id)}</code>",
            f"<b>Chat:</b> {escape(deleted.chat.title or deleted.chat.first_name or str(deleted.chat.id))}",
            f"<b>Chat ID:</b> <code>{deleted.chat.id}</code>",
            f"<b>Deleted message ID:</b> <code>{message_id}</code>",
            "<b>User data:</b> Telegram does not include the original sender in the deletion update; "
            "see the earlier mirrored message above when available.",
        ]
    )


@bot.deleted_business_messages_handler(func=lambda _: True)
def handle_deleted_business_messages(deleted: types.BusinessMessagesDeleted) -> None:
    """Notify the owner when Telegram Business reports deleted private-chat messages."""
    for message_id in deleted.message_ids:
        original_key = (deleted.business_connection_id, deleted.chat.id, message_id)
        previous_owner_message_id = mirrored_messages.get(original_key)
        bot.send_message(
            OWNER_CHAT_ID,
            format_deleted_business_message(deleted, message_id),
            reply_to_message_id=previous_owner_message_id,
            disable_web_page_preview=True,
        )


if __name__ == "__main__":
    print("Bot is running. Press Ctrl+C to stop.")
    bot.infinity_polling(
        skip_pending=True,
        allowed_updates=[
            "message",
            "edited_message",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
        ],
    )
