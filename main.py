
import os
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
WEBHOOK_URL = "https://matvey-dubai-bot.onrender.com/telegram"


@app.route("/", methods=["GET"])
def home():
    return "Matvey Dubai Bot is running!"


@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.json

    if not data or "message" not in data:
        return "OK"

    chat_id = data["message"]["chat"]["id"]
    answer = "Здравствуйте! Я Матвей, AI-ассистент по недвижимости в Дубае. Чем могу помочь?"

    if TELEGRAM_TOKEN:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": answer},
            timeout=15
        )

    return "OK"


if __name__ == "__main__":
    if TELEGRAM_TOKEN:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
            json={"url": WEBHOOK_URL},
            timeout=15
        )
        print("Telegram webhook setup:", response.text)

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
