import os
import logging
import asyncio
import base64
import re
import requests
import google.generativeai as genai
import json
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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # <-- यह बहुत ज़रूरी है

# Validate required variables
required_vars = [API_ID, API_HASH, PRIVATE_GROUP_ID, EARNKARO_BOT_USERNAME, PERSONAL_BOT_USERNAME, SOURCE_CHANNEL_USERNAME, GEMINI_API_KEY]
if not all(required_vars):
    logger.error("❌ Required environment variables not set (including GEMINI_API_KEY)")
    exit(1)

API_ID = int(API_ID)
PRIVATE_GROUP_ID = int(PRIVATE_GROUP_ID)

# ------------------ Gemini AI कॉन्फ़िगरेशन ------------------
model = None # पहले मॉडल को None पर सेट करें
try:
    if not GEMINI_API_KEY:
        logger.error("❌ GEMINI_API_KEY is not set. AI features will be disabled.")
    else:
        genai.configure(api_key=GEMINI_API_KEY)
        # <-- FIX: 'gemini-pro' को नवीनतम मॉडल 'gemini-1.5-flash' से बदला गया है।
        # यह तेज़, कुशल और समर्थित है।
        model = genai.GenerativeModel('gemini-1.5-flash')
        logger.info("✅ Gemini AI Model ('gemini-1.5-flash') initialized successfully.")
except Exception as e:
    logger.error(f"❌ Failed to initialize Gemini AI: {e}")
    # मॉडल None ही रहेगा, और कोड बिना AI के चलेगा

# ------------------ Session File ------------------
if SESSION_BASE64:
    with open("final_session.session", "wb") as f:
        f.write(base64.b64decode(SESSION_BASE64))
    logger.info("✅ final_session.session file created from SESSION_BASE64")

# ------------------ Templates (अब सिर्फ हैशटैग के लिए) ------------------
TEMPLATES = {
    "amazon": {"hashtags": "#Amazon #LootDeal #DealLootIndia"},
    "flipkart": {"hashtags": "#Flipkart #LootDeal #DealLootIndia"},
    "myntra": {"hashtags": "#Myntra #StyleDeal #DealLootIndia"},
    "ajio": {"hashtags": "#Ajio #FashionDeal #DealLootIndia"},
    "meesho": {"hashtags": "#Meesho #BudgetDeal #DealLootIndia"},
    "jiomart": {"hashtags": "#JioMart #LootDeal #DealLootIndia"}
}

PLATFORM_KEYWORDS = {
    "amazon": ["amazon.in", "amzn.to", "amazon", "amzn", "amazn"],
    "flipkart": ["flipkart.com", "fkrt", "flipkart", "flpkrt", "fkrt.xyz", "fktr.in"],
    "myntra": ["myntra.in", "myntr.it", "myntra", "myntr"],
    "ajio": ["ajio.in", "ajio"],
    "meesho": ["meesho.com", "msho.in", "meesho", "msho"],
    "jiomart": ["jiomart.com", "jiomart"]
}

MAX_CAPTION = 1024
processed_messages = set()
client = TelegramClient("final_session", API_ID, API_HASH)

# ------------------ Helper Functions ------------------

def resolve_short_link(url):
    try:
        response = requests.head(url, allow_redirects=True, timeout=5)
        return response.url
    except requests.RequestException:
        return url

def detect_platform(text):
    if not text: return None
    urls = re.findall(r'https?://\S+', text)
    full_text_to_check = text
    if urls:
        final_url = resolve_short_link(urls[0])
        full_text_to_check += " " + final_url
    text_lower = full_text_to_check.lower().replace(" ", "")
    for platform, keywords in PLATFORM_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return platform
    return None

# <-- AI फंक्शन, अब इंट्रो लाइन भी बनाएगा
def get_ai_generated_details(text):
    # अगर मॉडल इनिशियलाइज़ नहीं हुआ है, तो डिफ़ॉल्ट वैल्यू लौटाएं
    if not model:
        logger.warning("⚠️ Gemini AI model not available. Using default details.")
        return "Deal", "✨", "⚡ Amazing deal waiting for you!\n🚀 Hurry, grab it now!"

    product_info = "\n".join(text.split('\n')[:4])
    
    prompt = f"""
    Analyze the following product information from an Indian shopping deal. Your task is to generate a JSON object with three keys: "category", "emoji", and "intro_lines".

    Instructions:
    1.  "category": Determine the most appropriate single-word category (e.g., Electronics, Fashion, Kitchen, Beauty, Home).
    2.  "emoji": Provide a single, suitable emoji that best represents the product.
    3.  "intro_lines": Create two short, exciting, and creative introductory lines for the deal, separated by a newline character (\\n).

    Example 1:
    Product: "boAt Airdopes 141, TWS Earbuds with 42H Playtime"
    Response: {{"category": "Electronics", "emoji": "🎧", "intro_lines": "🎶 Immerse yourself in pure sound!\\n🚀 Grab these top-rated earbuds at a steal!"}}

    Example 2:
    Product: "Puma Men's Regular Fit T-Shirt"
    Response: {{"category": "Fashion", "emoji": "👕", "intro_lines": "🔥 Upgrade your style with this classic Puma tee!\\n🚀 Limited stock, shop now!"}}
    
    Product Information:
    ---
    {product_info}
    ---

    Your JSON Response:
    """
    
    try:
        response = model.generate_content(prompt)
        # प्रतिक्रिया में से JSON को सुरक्षित रूप से निकालने के लिए Regex का उपयोग करें
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            json_text = match.group(0)
            result = json.loads(json_text)
            return result.get("category", "Deal"), result.get("emoji", "🔥"), result.get("intro_lines", "⚡ Amazing deal waiting for you!")
        else:
             raise ValueError("No valid JSON found in the response")
    except Exception as e:
        logger.error(f"❌ Gemini AI Error: {e}")
        return "Deal", "✨", "⚡ Amazing deal waiting for you!\n🚀 Hurry, grab it now!"

def clean_incoming_message(text):
    # आप यहां और भी पैटर्न जोड़ सकते हैं जिन्हें हटाना है
    unwanted_patterns = [r"👉 Follow @\w+ for 🔥 daily loot deals!"]
    for pattern in unwanted_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return text.strip()

# <-- अपडेटेड टेम्प्लेट फंक्शन, अब AI से मिली जानकारी का उपयोग करेगा
def format_template(platform, category, emoji, intro_lines, message_text):
    follow_line = "👉 Follow @Deallootindia_offical for 🔥 daily loot deals!"
    platform_name = platform.capitalize() if platform else "Hot"
    category_name = category.capitalize()
    
    first_line = f"{emoji} {platform_name} {category_name} Deal"
    hashtags = TEMPLATES.get(platform, {}).get("hashtags", "#DealLootIndia #LootDeal")

    header = f"{first_line}\n{intro_lines}"
    template_parts = [header, message_text.strip(), follow_line, hashtags]
    return "\n\n".join(filter(None, template_parts))

async def send_to_earnkaro(message_text, media=None):
    try:
        if media:
            await client.send_file(EARNKARO_BOT_USERNAME, file=media, caption=message_text[:MAX_CAPTION])
            # अगर कैप्शन बहुत लंबा है तो बाकी का हिस्सा अलग मैसेज में भेजें
            if len(message_text) > MAX_CAPTION:
                await client.send_message(EARNKARO_BOT_USERNAME, message_text[MAX_CAPTION:])
        else:
            await client.send_message(EARNKARO_BOT_USERNAME, message_text)
        logger.info("✅ Sent to EarnKaro bot")
    except Exception as e:
        logger.error(f"❌ Failed sending to EarnKaro bot: {e}")

# ------------------ Event Handlers ------------------
async def process_message(event):
    msg_key = (event.message.chat_id, event.message.id)
    if msg_key in processed_messages: return None, None
    processed_messages.add(msg_key)

    message_text = event.message.message or ""
    cleaned_message_text = clean_incoming_message(message_text)

    media = event.message.media
    if isinstance(media, MessageMediaWebPage): media = None

    platform = detect_platform(cleaned_message_text)
    category, emoji, intro_lines = get_ai_generated_details(cleaned_message_text)
    
    final_text = format_template(platform, category, emoji, intro_lines, cleaned_message_text)
    
    return final_text, media

@client.on(events.NewMessage(chats=SOURCE_CHANNEL_USERNAME))
async def handle_source(event):
    final_text, media = await process_message(event)
    if final_text:
        try:
            # प्राइवेट ग्रुप और Earnkaro बॉट दोनों को भेजें
            await client.send_message(PRIVATE_GROUP_ID, final_text, file=media)
            logger.info(f"✅ Forwarded message to private group: {PRIVATE_GROUP_ID}")
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
        except Exception as e:
            logger.error(f"❌ Manual Send Error: {e}")
            await event.reply(f"❌ Error: {e}")

# ------------------ Keep Alive Flask Server ------------------
app = Flask("")
@app.route("/")
def home():
    return "Bot is alive and running!"

# ------------------ Main ------------------
async def main():
    await client.start()
    logger.info("✅ Telegram client started and bot is ready!")
    await client.run_until_disconnected()

if __name__ == "__main__":
    from threading import Thread
    # Flask सर्वर को एक अलग थ्रेड में चलाएं
    flask_thread = Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080))))
    flask_thread.daemon = True
    flask_thread.start()
    
    # मुख्य asyncio लूप चलाएं
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
