import os
import logging
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN_RAW = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_TOKEN = TELEGRAM_TOKEN_RAW.strip()
TOKEN_FORMAT_VALID = bool(__import__("re").fullmatch(r"\d+:[A-Za-z0-9_-]+", TELEGRAM_TOKEN))
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
    if not TELEGRAM_TOKEN:
        return jsonify({"status": "error", "reason": "token_not_configured", "token_length": 0}), 503
    if not TOKEN_FORMAT_VALID:
        return jsonify({"status": "error", "reason": "token_format_invalid", "token_length": len(TELEGRAM_TOKEN), "outer_whitespace_removed": TELEGRAM_TOKEN_RAW != TELEGRAM_TOKEN}), 503
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
    except requests.RequestException as exc:
        logging.exception("Telegram diagnostic request failed.")
        # Return safe diagnostics without ever exposing the bot token.
        details = {"status": "error", "reason": "telegram_request_failed",
                   "error_type": type(exc).__name__}
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            details["telegram_http_status"] = exc.response.status_code
            try:
                body = exc.response.json()
                details["telegram_description"] = body.get("description", "Telegram returned an HTTP error")
            except ValueError:
                details["telegram_description"] = "Telegram returned a non-JSON HTTP error"
        elif isinstance(exc, requests.ConnectionError):
            details["telegram_description"] = "Could not connect to api.telegram.org"
        elif isinstance(exc, requests.Timeout):
            details["telegram_description"] = "Telegram API request timed out"
        else:
            details["telegram_description"] = str(exc)[:250]
        return jsonify(details), 502


@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json(silent=True) or {}
    message = data.get("message")
    logging.info("Telegram webhook received: update_id=%s, has_message=%s", data.get("update_id"), bool(message))

    if not message:
        logging.warning("Telegram update has no message field; update_id=%s", data.get("update_id"))
        return "OK", 200

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "")

    if not chat_id:
        logging.warning("Telegram message has no chat_id; update_id=%s", data.get("update_id"))
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
            logging.error("Telegram sendMessage returned ok=false: %s", result)
            return "Telegram API error", 500
        logging.info("Telegram reply sent successfully for update_id=%s", data.get("update_id"))
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
