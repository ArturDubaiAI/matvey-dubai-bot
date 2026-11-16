import os
import logging
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
WEBHOOK_URL = "https://matvey-dubai-bot.onrender.com/telegram"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None


@app.route("/", methods=["GET"])
def home():
    return "Matvey Dubai Bot is running!"


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "telegram_token_configured": bool(TELEGRAM_TOKEN)
    }), 200


@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json(silent=True) or {}
    message = data.get("message")

    if not message:
        return "OK", 200

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "")

    if not chat_id:
        return "OK", 200

    if text.startswith("/start"):
        answer = (
            "Здравствуйте! Я Матвей, AI-ассистент по недвижимости в Дубае. "
            "Чем могу помочь?"
        )
    else:
        answer = (
            "Спасибо за сообщение! Я Матвей, AI-ассистент по недвижимости в Дубае. "
            "Расскажите, пожалуйста, что именно вас интересует."
        )

    if not TELEGRAM_API:
        logging.error("TELEGRAM_TOKEN is not configured.")
        return "Token not configured", 500

    try:
        response = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": answer},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            logging.error("Telegram sendMessage failed: %s", result)
            return "Telegram API error", 500
    except requests.RequestException:
        logging.exception("Failed to send message to Telegram.")
        return "Telegram request failed", 500

    return "OK", 200


if __name__ == "__main__":
    if TELEGRAM_API:
        try:
            response = requests.post(
                f"{TELEGRAM_API}/setWebhook",
                json={"url": WEBHOOK_URL},
                timeout=15,
            )
            response.raise_for_status()
            logging.info("Telegram webhook setup: %s", response.text)
        except requests.RequestException:
            logging.exception("Failed to set Telegram webhook.")
    else:
        logging.warning("TELEGRAM_TOKEN is not configured.")

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
    )
