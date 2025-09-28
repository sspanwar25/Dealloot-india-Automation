import os
import logging
import base64
from telethon import TelegramClient, events
from flask import Flask
from threading import Thread

# ------------------ Logging ------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ------------------ Environment Variables ------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_BASE64 = os.getenv("SESSION_BASE64")

SOURCE_CHANNELS = [x.strip() for x in os.getenv("SOURCE_CHANNEL_USERNAME", "").split(",") if x.strip()]
TARGET_CHAT_IDS = [x.strip() for x in os.getenv("TARGET_CHAT_ID", "").split(",") if x.strip()]

PROMO_TEXT = os.getenv(
    "PROMO_TEXT",
    "Follow @Deallootindia_offical for 🔥 daily loot deals!"
)

# ------------------ Session Handling ------------------
if not SESSION_BASE64:
    logger.error("❌ SESSION_BASE64 not found in environment variables")
    exit(1)

session_bytes = base64.b64decode(SESSION_BASE64)
with open("final_session.session", "wb") as f:
    f.write(session_bytes)

client = TelegramClient("final_session", API_ID, API_HASH)

# ------------------ Forwarding Logic ------------------
@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handler(event):
    for target in TARGET_CHAT_IDS:
        try:
            if event.message.message and not event.message.media:
                text_with_promo = f"{event.message.message}\n\n{PROMO_TEXT}"
                await client.send_message(target, text_with_promo)
            elif event.message.media:
                caption = (event.message.message or "") + f"\n\n{PROMO_TEXT}"
                await client.send_file(
                    target,
                    event.message.media,
                    caption=caption
                )
            logger.info(f"✅ Sent to {target}")
        except Exception as e:
            logger.error(f"❌ Error sending to {target}: {e}")

# ------------------ Flask (Keep Alive) ------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ------------------ Start ------------------
if __name__ == "__main__":
    Thread(target=run_flask).start()
    logger.info("🚀 Starting Telegram client...")
    with client:
        client.run_until_disconnected()
