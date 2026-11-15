import os
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

@app.route("/", methods=["GET"])
def home():
    return "Matvey Dubai Bot is running!"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.json

    if not data or "message" not in data:
        return "OK"

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")

    answer = "Здравствуйте! Я Матвей, AI-ассистент по недвижимости в Дубае. Чем могу помочь?"

    if TELEGRAM_TOKEN:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": answer}
        )

    return "OK"

 if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
