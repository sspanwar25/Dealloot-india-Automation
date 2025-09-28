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
PHONE = os.getenv("PHONE_NUMBER")
SOURCE_CHANNELS = [x.strip() for x in os.getenv("SOURCE_CHANNEL_USERNAME").split(",")]
TARGET_CHAT_IDS = [x.strip() for x in os.getenv("TARGET_CHAT_ID").split(",")]
SESSION_BASE64 = os.getenv("SESSION_BASE64")

required_vars = [API_ID, API_HASH, PHONE, SOURCE_CHANNELS, TARGET_CHAT_IDS]
if not all(required_vars):
    logger.error("❌ Required environment variables not set")
    exit(1)

# ------------------ Session File ------------------
if SESSION_BASE64:
    with open("final_session.session", "wb") as f:
        f.write(base64.b64decode(SESSION_BASE64))
    logger.info("✅ final_session.session file created from SESSION_BASE64")

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
    "amazon": ["amazon.in", "amzn.to", "amazon", "amzn", "amazn"],
    "flipkart": ["flipkart.com", "fkrt", "flipkart", "flpkrt", "fkrt.xyz", "fktr.in"],
    "myntra": ["myntra.in", "myntr.it", "myntra", "myntr"],
    "ajio": ["ajio.in", "ajio"],
    "meesho": ["meesho.com", "msho.in", "meesho", "msho"],
    "jiomart": ["jiomart.com", "jiomart"]
}

CATEGORY_KEYWORDS = {
    "electronics": ["air fryer", "watch", "earbuds", "headphones", "electronic", "mobile", "laptop", "tv", "led", "smarttv", "smart tv", "home appliance"],
    "fashion": ["trouser", "shirt", "t-shirt", "dress", "jeans", "fashion", "clothing"],
    "kitchenware": ["cookware", "pan", "cooker", "kitchen", "utensil", "pressure", "oven"],
    "beauty": ["shampoo", "cream", "soap", "makeup", "deodorant", "skincare", "perfume"]
}

CATEGORY_TEMPLATES = {
    "electronics": {"emoji": "🔌", "intro": ["⚡ Amazing electronics deals!", "🚀 Grab them before they run out!"]},
    "fashion": {"emoji": "👗", "intro": ["⚡ Trendy picks at stunning discounts!", "🚀 Hurry, limited stock available!"]},
    "kitchenware": {"emoji": "🍳", "intro": ["⚡ Cookware & kitchen essentials at best prices!", "🚀 Upgrade your kitchen today!"]},
    "beauty": {"emoji": "💄", "intro": ["⚡ Beauty & personal care deals!", "🚀 Pamper yourself with best offers!"]}
}

# ------------------ Telegram Client ------------------
client = TelegramClient("final_session", API_ID, API_HASH)
processed_messages = set()
MAX_CAPTION = 1024

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
    follow_line = "👉 Follow @Deallootindia_offical for 🔥 daily loot deals!"
    if category and category in CATEGORY_TEMPLATES:
        first_line = f"{CATEGORY_TEMPLATES[category]['emoji']} {platform.capitalize()} {category.capitalize()} Deal"
    else:
        first_line = f"{TEMPLATES[platform]['emoji']} {platform.capitalize()} Loot Deal" if platform in TEMPLATES else f"{platform.capitalize() if platform else ''} Loot Deal"
    intro_lines = TEMPLATES[platform]["intro"].split("\n") if platform in TEMPLATES else []
    header = "\n".join([first_line] + intro_lines)
    template_parts = [header, message_text, follow_line, TEMPLATES[platform]["hashtags"] if platform in TEMPLATES else "#DealLootIndia #LootDeal"]
    return "\n\n".join(template_parts)

# ------------------ Send Functions ------------------
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

    await send_to_targets(final_text, media)

@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handle_manual(event):
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

    await send_to_targets(final_text, media)

# ------------------ Keep Alive Flask Server ------------------
app = Flask("")

@app.route("/")
def home():
    return "Bot is running."

# ------------------ Main ------------------
async def main():
    await client.start()
    logger.info("✅ Telegram client started")
    await client.run_until_disconnected()

if __name__ == "__main__":
    from threading import Thread
    Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))).start()
    asyncio.run(main())
