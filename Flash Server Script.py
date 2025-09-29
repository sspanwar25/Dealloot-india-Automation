import os
import logging
import asyncio
import base64
import re
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaWebPage
from flask import Flask

# ------------------ Logging ------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------ Environment Variables ------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_BASE64 = os.getenv("SESSION_BASE64")
SOURCE_CHANNELS = [x.strip() for x in os.getenv("FLASH_SOURCE_CHANNELS", "").split(",") if x.strip()]
TARGET_CHAT_IDS = [x.strip() for x in os.getenv("FLASH_TARGET_CHAT_IDS", "").split(",") if x.strip()]

if not all([API_ID, API_HASH, SESSION_BASE64, SOURCE_CHANNELS, TARGET_CHAT_IDS]):
    logger.error("❌ Required Flash environment variables not set")
    exit(1)

# ------------------ Session File ------------------
if SESSION_BASE64:
    with open("flash_session.session", "wb") as f:
        f.write(base64.b64decode(SESSION_BASE64))
    logger.info("✅ flash_session.session file created from SESSION_BASE64")

# ------------------ Templates ------------------
TEMPLATES = {
    "amazon": {"emoji": "🔌", "intro": "⚡ Unbeatable offers waiting for you!\n🚀 Hurry before stock runs out!", "hashtags": "#Amazon #LootDeal #DealLootIndia"},
    "flipkart": {"emoji": "📦", "intro": "⚡ Mega discounts are live now!\n🚀 Grab your favorite products before stock runs out!", "hashtags": "#Flipkart #LootDeal #DealLootIndia"},
    "myntra": {"emoji": "👗", "intro": "⚡ Trendy picks at stunning discounts!\n🚀 Hurry, limited stock available!", "hashtags": "#Myntra #StyleDeal #DealLootIndia"},
    "ajio": {"emoji": "👜", "intro": "⚡ Stylish collections at killer prices!\n🚀 Shop now before the best picks vanish!", "hashtags": "#Ajio #FashionDeal #DealLootIndia"},
    "meesho": {"emoji": "💰", "intro": "⚡ Best budget picks at crazy low prices!\n🚀 Shop more, save more!", "hashtags": "#Meesho #BudgetDeal #DealLootIndia"},
    "jiomart": {"emoji": "🛒", "intro": "⚡ Grocery & essentials at lowest prices!\n🚀 Order now and save big!", "hashtags": "#JioMart #LootDeal #DealLootIndia"}
}

PLATFORM_KEYWORDS = {
    "amazon": ["amazon.in", "amzn.to", "amazon"],
    "flipkart": ["flipkart.com", "fkrt", "flipkart"],
    "myntra": ["myntra.in", "myntra"],
    "ajio": ["ajio.in", "ajio"],
    "meesho": ["meesho.com", "meesho"],
    "jiomart": ["jiomart.com", "jiomart"]
}

MAX_CAPTION = 1024
processed_messages = set()

# ------------------ Telegram Client ------------------
client = TelegramClient("flash_session", API_ID, API_HASH)

# ------------------ Helper Functions ------------------
def detect_platform(text):
    if not text:
        return None
    text_lower = text.lower().replace(" ", "")
    for platform, keywords in PLATFORM_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return platform
            pattern = rf"{re.escape(kw)}[\w./-]*"
            if re.search(pattern, text_lower):
                return platform
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

def format_template(platform, message_text):
    follow_line = "👉 Follow @DealLoot_India for 🔥 daily loot deals!"
    first_line = f"{TEMPLATES[platform]['emoji']} {platform.capitalize()} Loot Deal" if platform in TEMPLATES else f"{platform.capitalize() if platform else ''} Loot Deal"
    intro_lines = TEMPLATES[platform]["intro"].split("\n") if platform in TEMPLATES else []
    header = "\n".join([first_line] + intro_lines)
    template_parts = [header, message_text, follow_line, TEMPLATES[platform]["hashtags"] if platform in TEMPLATES else "#DealLootIndia #LootDeal"]
    return "\n\n".join(template_parts)

async def send_to_targets(message_text, media=None):
    for target in TARGET_CHAT_IDS:
        try:
            if media:
                caption_text = message_text[:MAX_CAPTION]
                await client.send_file(target, file=media, caption=caption_text)
                remaining_text = message_text[MAX_CAPTION:]
                if remaining_text.strip():
                    await client.send_message(target, remaining_text)
            else:
                await client.send_message(target, message_text)
            logger.info(f"✅ Sent to {target}")
        except Exception as e:
            logger.error(f"❌ Failed sending to {target}: {e}")

# ------------------ Event Handlers ------------------
@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handle_flash_source(event):
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
    final_text = format_template(platform, message_text)
    await send_to_targets(final_text, media)

# ------------------ Keep Alive Flask Server ------------------
app = Flask("flash_server")

@app.route("/")
def home():
    return "Flash server bot is running."

# ------------------ Main ------------------
async def main():
    await client.start()
    logger.info("✅ Flash Telegram client started")
    await client.run_until_disconnected()

if __name__ == "__main__":
    from threading import Thread
    Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8081)))).start()
    asyncio.run(main())
