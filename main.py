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


@app.route("/telegram-status", methods=["GET"])
def telegram_status():
    """Safe diagnostic endpoint; never returns the bot token."""
    if not TELEGRAM_API:
        return jsonify({"status": "error", "reason": "token_not_configured"}), 503
    try:
        me_response = requests.get(f"{TELEGRAM_API}/getMe", timeout=10)
        webhook_response = requests.get(f"{TELEGRAM_API}/getWebhookInfo", timeout=10)
        me_response.raise_for_status()
        webhook_response.raise_for_status()
        me = me_response.json()
        webhook = webhook_response.json()
        if not me.get("ok") or not webhook.get("ok"):
            return jsonify({"status": "telegram_api_error", "getMe_ok": me.get("ok"), "getWebhookInfo_ok": webhook.get("ok")}), 502
        info = webhook.get("result", {})
        return jsonify({
            "status": "ok",
            "bot_username": me.get("result", {}).get("username"),
            "webhook_url": info.get("url"),
            "pending_update_count": info.get("pending_update_count"),
            "last_error_date": info.get("last_error_date"),
            "last_error_message": info.get("last_error_message"),
            "max_connections": info.get("max_connections"),
            "allowed_updates": info.get("allowed_updates"),
        }), 200
    except requests.RequestException:
        logging.exception("Telegram diagnostic request failed.")
        return jsonify({"status": "error", "reason": "telegram_request_failed"}), 502


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
