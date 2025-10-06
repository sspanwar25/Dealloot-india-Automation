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
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PRIVATE_GROUP_ID = os.getenv("PRIVATE_GROUP_ID")
EARNKARO_BOT_USERNAME = os.getenv("EARNKARO_BOT_USERNAME")
PERSONAL_BOT_USERNAME = os.getenv("PERSONAL_BOT_USERNAME")
SOURCE_CHANNEL_USERNAME = os.getenv("SOURCE_CHANNEL_USERNAME")
SESSION_BASE64 = os.getenv("SESSION_BASE64")

# Validate required variables
required_vars = [API_ID, API_HASH, PRIVATE_GROUP_ID, EARNKARO_BOT_USERNAME, PERSONAL_BOT_USERNAME, SOURCE_CHANNEL_USERNAME]
if not all(required_vars):
    logger.error("❌ Required environment variables not set")
    exit(1)

API_ID = int(API_ID)
PRIVATE_GROUP_ID = int(PRIVATE_GROUP_ID)

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

MAX_CAPTION = 1024
processed_messages = set()

# ------------------ Telegram Client ------------------
client = TelegramClient("final_session", API_ID, API_HASH)

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

# <--- बदलाव: यह फंक्शन अब केवल उन फॉलो लाइनों को हटाएगा जो सोर्स से आती हैं
def clean_incoming_message(text):
    """Removes specific unwanted follow lines from the source message."""
    unwanted_patterns = [
        r"👉 Follow @lootshoppingxyz for 🔥 daily loot deals!"
        # भविष्य में आप यहाँ और भी पैटर्न जोड़ सकते हैं
    ]
    for pattern in unwanted_patterns:
        text = re.sub(pattern, '', text)
    return text.strip()

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

# ------------------ Event Handlers ------------------
# <--- बदलाव: यह कॉमन फंक्शन दोनों हैंडलर्स के लिए मैसेज प्रोसेस करेगा
async def process_message(event):
    msg_key = (event.message.chat_id, event.message.id)
    if msg_key in processed_messages:
        return None, None
    processed_messages.add(msg_key)

    # स्टेप 1: ओरिजिनल मैसेज टेक्स्ट प्राप्त करें
    message_text = event.message.message or ""

    # स्टेप 2: केवल सोर्स से आने वाली अवांछित फॉलो लाइन को हटाएँ
    cleaned_message_text = clean_incoming_message(message_text)

    # स्टेप 3: मीडिया को संभालें
    media = event.message.media
    if isinstance(media, MessageMediaWebPage):
        media = None

    # स्टेप 4: प्लेटफॉर्म और कैटेगरी का पता लगाएं
    platform = detect_platform(cleaned_message_text)
    category = detect_category(cleaned_message_text)

    # स्टेप 5: अपने टेम्प्लेट का उपयोग करके फाइनल टेक्स्ट बनाएं
    # यहाँ हम 'cleaned_message_text' का उपयोग कर रहे हैं जिसमें न तो डुप्लीकेट लिंक हैं और न ही अवांछित फॉलो लाइन
    final_text = format_template(platform, category, cleaned_message_text)
    
    return final_text, media

@client.on(events.NewMessage(chats=SOURCE_CHANNEL_USERNAME))
async def handle_source(event):
    final_text, media = await process_message(event)
    if final_text:
        try:
            await client.send_message(PRIVATE_GROUP_ID, final_text, file=media) # <--- मीडिया को भी प्राइवेट ग्रुप में भेजा
            await send_to_earnkaro(final_text, media)
        except Exception as e:
            logger.error(f"❌ Auto forward failed: {e}")

@client.on(events.NewMessage(chats=PERSONAL_BOT_USERNAME))
async def handle_manual(event):
    final_text, media = await process_message(event)
    if final_text:
        try:
            await send_to_earnkaro(final_text, media)
            await event.reply("✅ Sent manually to EarnKaro bot")
            logger.info(f"Manual message forwarded: Platform={detect_platform(final_text)}, Category={detect_category(final_text)}")
        except Exception as e:
            logger.error(f"❌ Manual Send Error: {e}")

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
