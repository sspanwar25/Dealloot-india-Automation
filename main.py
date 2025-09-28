import os
import logging
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaWebPage
import re
from flask import Flask
import imghdr

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PRIVATE_GROUP_ID = int(os.getenv("PRIVATE_GROUP_ID"))
EARNKARO_BOT_USERNAME = os.getenv("EARNKARO_BOT_USERNAME")
PERSONAL_BOT_USERNAME = os.getenv("PERSONAL_BOT_USERNAME")
SOURCE_CHANNEL_USERNAME = os.getenv("SOURCE_CHANNEL_USERNAME")

required_vars = [BOT_TOKEN, API_ID, API_HASH, PRIVATE_GROUP_ID,
                 EARNKARO_BOT_USERNAME, PERSONAL_BOT_USERNAME, SOURCE_CHANNEL_USERNAME]

if not all(required_vars):
    logger.error("❌ Required environment variables not set")
    exit(1)

# Templates & Keywords (same as previous)
TEMPLATES = {
    "amazon": {"emoji": "🔌", "intro": "⚡ Unbeatable offers waiting for you!\n🚀 Hurry before stock runs out!", "hashtags": "#Amazon #LootDeal #DealLootIndia"},
    "flipkart": {"emoji": "📦", "intro": "⚡ Mega discounts are live now!\n🚀 Grab your favorite products before stock runs out!", "hashtags": "#Flipkart #LootDeal #DealLootIndia"},
    "myntra": {"emoji": "👗", "intro": "⚡ Trendy picks at stunning discounts!\n🚀 Hurry, limited stock available!", "hashtags": "#Myntra #StyleDeal #DealLootIndia"},
    "ajio": {"emoji": "👜", "intro": "⚡ Stylish collections at killer prices!\n🚀 Shop now before the best picks vanish!", "hashtags": "#Ajio #FashionDeal #DealLootIndia"},
    "meesho": {"emoji": "💰", "intro": "⚡ Best budget picks at crazy low prices!\n🚀 Shop more, save more!", "hashtags": "#Meesho #BudgetDeal #DealLootIndia"},
    "jiomart": {"emoji": "🛒", "intro": "⚡ Grocery & essentials at lowest prices!\n🚀 Order now and save big!", "hashtags": "#JioMart #LootDeal #DealLootIndia"}
}

PLATFORM_KEYWORDS = { ... }  # use your previous mapping
CATEGORY_KEYWORDS = { ... }  # use your previous mapping
CATEGORY_TEMPLATES = { ... }  # use your previous mapping

# Telegram Client
client = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
processed_messages = set()

# Helper Functions
def detect_platform(text):
    if not text:
        return None
    text_lower = text.lower().replace(" ", "")
    for platform, keywords in PLATFORM_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower or re.search(rf"{re.escape(kw)}[\w./-]*", text_lower):
                return platform
    return None

def detect_category(text):
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in text_lower for k in keywords):
            return category
    return None

def extract_links(event_message):
    urls = []
    if event_message.message:
        urls.extend(re.findall(r'https?://\S+', event_message.message))
    if hasattr(event_message, "entities") and event_message.entities:
        for entity in event_message.entities:
            if hasattr(entity, "url") and entity.url:
                urls.append(entity.url)
    return urls

def format_template(platform, category, message_text):
    follow_line = "👉 Follow @Deallootindia_bot for 🔥 daily loot deals!"
    if category and category in CATEGORY_TEMPLATES:
        first_line = f"{CATEGORY_TEMPLATES[category]['emoji']} {platform.capitalize()} {category.capitalize()} Deal"
    else:
        first_line = f"{TEMPLATES[platform]['emoji']} {platform.capitalize()} Loot Deal" if platform in TEMPLATES else f"{platform.capitalize() if platform else ''} Loot Deal"
    intro_lines = TEMPLATES[platform]["intro"].split("\n") if platform in TEMPLATES else []
    header = "\n".join([first_line] + intro_lines)
    return "\n\n".join([header, message_text, follow_line, TEMPLATES[platform]["hashtags"] if platform in TEMPLATES else "#DealLootIndia #LootDeal"])

MAX_CAPTION = 1024

async def send_to_earnkaro(message_text, media=None):
    try:
        if media:
            caption_text = message_text[:MAX_CAPTION]
            await client.send_file(EARNKARO_BOT_USERNAME, file=media, caption=caption_text)
            remaining_text = message_text[MAX_CAPTION:]
            if remaining_text.strip():
                await client.send_message(EARNKARO_BOT_USERNAME, remaining_text)
        else:
            await client.send_message(EARNKARO_BOT_USERNAME, message_text)
        logger.info("✅ Sent to EarnKaro bot")
    except Exception as e:
        logger.error(f"❌ Failed sending to EarnKaro bot: {e}")

# Event Handlers
@client.on(events.NewMessage(chats=SOURCE_CHANNEL_USERNAME))
async def handle_source(event):
    msg_key = (event.message.chat_id, event.message.id)
    if msg_key in processed_messages:
        return
    processed_messages.add(msg_key)

    message_text = event.message.message or ""
    links = extract_links(event.message)
    if links:
        message_text += "\n" + "\n".join(links)
    media = event.message.media
    if isinstance(media, MessageMediaWebPage):
        media = None
    platform = detect_platform(message_text)
    category = detect_category(message_text)
    final_text = format_template(platform, category, message_text)

    try:
        await client.send_message(PRIVATE_GROUP_ID, final_text)
        await send_to_earnkaro(final_text, media)
    except Exception as e:
        logger.error(f"❌ Auto forward failed: {e}")

@client.on(events.NewMessage(chats=PERSONAL_BOT_USERNAME))
async def handle_manual(event):
    try:
        message_text = event.message.message or ""
        links = extract_links(event.message)
        if links:
            message_text += "\n" + "\n".join(links)
        media = event.message.media
        if isinstance(media, MessageMediaWebPage):
            media = None
        platform = detect_platform(message_text)
        category = detect_category(message_text)
        final_text = format_template(platform, category, message_text)
        await send_to_earnkaro(final_text, media)
        await event.reply("✅ Sent manually to EarnKaro bot")
        logger.info(f"Manual message forwarded: Platform={platform}, Category={category}")
    except Exception as e:
        logger.error(f"❌ Manual Send Error: {e}")

# Flask Keep-Alive
app = Flask("")

@app.route("/")
def home():
    return "Bot is running."

async def main():
    logger.info("✅ Telegram bot started")
    await client.run_until_disconnected()

if __name__ == "__main__":
    from threading import Thread
    Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))).start()
    asyncio.run(main())
