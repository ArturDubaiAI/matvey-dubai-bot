import io
import logging
import os
import re
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Accept a raw BotFather token, but never log or return it.
TELEGRAM_TOKEN_RAW = os.environ.get("TELEGRAM_TOKEN", "")
TOKEN_MATCHES = re.findall(
    r"(?<![A-Za-z0-9_])([0-9]{8,12}:[A-Za-z0-9_-]{30,})(?![A-Za-z0-9_-])",
    TELEGRAM_TOKEN_RAW,
)
TELEGRAM_TOKEN = TOKEN_MATCHES[0] if len(TOKEN_MATCHES) == 1 else ""
TOKEN_FORMAT_VALID = len(TOKEN_MATCHES) == 1
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
WEBHOOK_URL = "https://matvey-dubai-bot.onrender.com/telegram"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"

SYSTEM_INSTRUCTIONS = (
    "Ты Матвей, полезный AI-ассистент по недвижимости в Дубае. "
    "Отвечай на русском языке, если пользователь пишет по-русски; "
    "подстраивай язык под пользователя. Будь дружелюбным, конкретным и честным. "
    "Помогай разобраться с покупкой, продажей, арендой, районами, ипотекой и "
    "инвестициями в недвижимость Дубая. Не выдумывай актуальные цены, наличие "
    "объектов, доходность, законы или условия сделок. Если данных не хватает, "
    "задай один короткий уточняющий вопрос. Не выдавай себя за лицензированного "
    "юриста, финансового консультанта или агента. Пиши компактно и по делу."
)


def safe_telegram_error(label, exc):
    """Log Telegram failures without printing request URLs or bot tokens."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    logging.error("%s: error_type=%s http_status=%s", label, type(exc).__name__, status)


def telegram_send(chat_id, text):
    if not TELEGRAM_API:
        raise RuntimeError("Telegram token is not configured")
    response = requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000]},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError("Telegram sendMessage returned ok=false")


def openai_answer(user_text):
    if not OPENAI_API_KEY:
        return None
    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4.1-mini",
            "instructions": SYSTEM_INSTRUCTIONS,
            "input": user_text[:12000],
            "max_output_tokens": 700,
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()

    # Responses API usually supplies output_text; retain a safe fallback parser.
    answer = payload.get("output_text")
    if not answer:
        chunks = []
        for item in payload.get("output", []):
            for part in item.get("content", []):
                if part.get("type") == "output_text" and part.get("text"):
                    chunks.append(part["text"])
        answer = "\n".join(chunks)
    if not answer:
        raise RuntimeError("OpenAI returned no text output")
    return answer.strip()


def telegram_voice_to_text(message):
    if not TELEGRAM_API:
        raise RuntimeError("Telegram token is not configured")
    voice = message.get("voice") or message.get("audio")
    if not voice or not voice.get("file_id"):
        return None

    file_info_response = requests.get(
        f"{TELEGRAM_API}/getFile",
        params={"file_id": voice["file_id"]},
        timeout=20,
    )
    file_info_response.raise_for_status()
    file_info = file_info_response.json()
    if not file_info.get("ok"):
        raise RuntimeError("Telegram getFile returned ok=false")
    file_path = file_info.get("result", {}).get("file_path")
    if not file_path:
        raise RuntimeError("Telegram did not return a voice file path")

    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    audio_response = requests.get(download_url, timeout=40)
    audio_response.raise_for_status()

    transcription_response = requests.post(
        OPENAI_TRANSCRIPTIONS_URL,
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        data={"model": "gpt-transcribe"},
        files={"file": ("telegram-voice.ogg", io.BytesIO(audio_response.content), "audio/ogg")},
        timeout=90,
    )
    transcription_response.raise_for_status()
    transcript = transcription_response.json().get("text", "").strip()
    return transcript or None


@app.route("/", methods=["GET"])
def home():
    return "Matvey Dubai Bot is running!"


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "telegram_token_configured": bool(TELEGRAM_TOKEN),
        "openai_api_key_configured": bool(OPENAI_API_KEY),
    }), 200


@app.route("/openai-status", methods=["GET"])
def openai_status():
    """Check whether the configured OpenAI key is accepted; never expose credentials."""
    if not OPENAI_API_KEY:
        return jsonify({"status": "error", "reason": "api_key_not_configured"}), 503
    try:
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            timeout=15,
        )
        if response.ok:
            return jsonify({"status": "ok", "openai_api_key_valid": True}), 200
        try:
            error_data = response.json().get("error", {})
        except (ValueError, AttributeError):
            error_data = {}
        return jsonify({
            "status": "error",
            "openai_api_key_valid": False,
            "http_status": response.status_code,
            "error_type": error_data.get("type"),
            "error_code": error_data.get("code"),
            "error_param": error_data.get("param"),
        }), 502
    except requests.RequestException as exc:
        logging.error("OpenAI key diagnostic failed: error_type=%s", type(exc).__name__)
        return jsonify({"status": "error", "reason": "openai_connection_failed"}), 502


@app.route("/telegram-status", methods=["GET"])
def telegram_status():
    """Safe diagnostic endpoint; never returns credentials."""
    if not TELEGRAM_TOKEN_RAW.strip():
        return jsonify({"status": "error", "reason": "token_not_configured"}), 503
    if not TOKEN_FORMAT_VALID:
        return jsonify({
            "status": "error",
            "reason": "token_format_invalid_or_multiple_tokens",
            "token_length": len(TELEGRAM_TOKEN_RAW.strip()),
        }), 503
    try:
        me_response = requests.get(f"{TELEGRAM_API}/getMe", timeout=10)
        webhook_response = requests.get(f"{TELEGRAM_API}/getWebhookInfo", timeout=10)
        me_response.raise_for_status()
        webhook_response.raise_for_status()
        me = me_response.json()
        webhook = webhook_response.json()
        if not me.get("ok") or not webhook.get("ok"):
            return jsonify({
                "status": "telegram_api_error",
                "getMe_ok": me.get("ok"),
                "getWebhookInfo_ok": webhook.get("ok"),
            }), 502
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
            "openai_api_key_configured": bool(OPENAI_API_KEY),
        }), 200
    except requests.RequestException as exc:
        safe_telegram_error("Telegram diagnostic request failed", exc)
        details = {
            "status": "error",
            "reason": "telegram_request_failed",
            "error_type": type(exc).__name__,
        }
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            details["telegram_http_status"] = exc.response.status_code
            details["telegram_description"] = "Telegram returned an HTTP error"
        elif isinstance(exc, requests.ConnectionError):
            details["telegram_description"] = "Could not connect to api.telegram.org"
        elif isinstance(exc, requests.Timeout):
            details["telegram_description"] = "Telegram API request timed out"
        else:
            details["telegram_description"] = "Telegram request failed"
        return jsonify(details), 502


@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json(silent=True) or {}
    message = data.get("message") or data.get("edited_message")
    logging.info(
        "Telegram webhook received: update_id=%s, has_message=%s",
        data.get("update_id"), bool(message),
    )

    if not message:
        return "OK", 200

    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        logging.warning("Telegram message has no chat_id; update_id=%s", data.get("update_id"))
        return "OK", 200

    if not TELEGRAM_API:
        logging.error("TELEGRAM_TOKEN is missing or invalid")
        return "Token not configured", 500

    incoming_text = (message.get("text") or message.get("caption") or "").strip()

    try:
        if incoming_text.startswith("/start"):
            answer = (
                "Здравствуйте! Я Матвей, AI-ассистент по недвижимости в Дубае. "
                "Могу помочь с покупкой, продажей, арендой и инвестициями. "
                "Напишите вопрос или отправьте голосовое сообщение."
            )
        elif not OPENAI_API_KEY:
            answer = (
                "Telegram подключён, но AI-ключ пока не настроен. "
                "Добавьте OPENAI_API_KEY в Environment Variables на Render."
            )
        else:
            if message.get("voice") or message.get("audio"):
                transcript = telegram_voice_to_text(message)
                if not transcript:
                    answer = "Не удалось разобрать голосовое сообщение. Попробуйте записать его ещё раз."
                else:
                    answer = openai_answer(transcript)
            elif incoming_text:
                answer = openai_answer(incoming_text)
            else:
                answer = "Пока понимаю текст и голосовые сообщения. Отправьте, пожалуйста, текст или голос."
        if not answer:
            answer = "Не получилось подготовить ответ. Попробуйте ещё раз."
        telegram_send(chat_id, answer)
        logging.info("Telegram reply sent successfully for update_id=%s", data.get("update_id"))
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        response_url = getattr(exc.response, "url", "") or ""
        if "api.openai.com" in response_url:
            # Log only structured, non-secret error metadata; never log response text or credentials.
            try:
                error_data = exc.response.json().get("error", {})
            except (ValueError, AttributeError):
                error_data = {}
            logging.error(
                "OpenAI API error: http_status=%s endpoint=%s error_type=%s error_code=%s error_param=%s",
                status,
                getattr(exc.response, "request", None).path_url.split("?")[0]
                if getattr(exc.response, "request", None) is not None else "unknown",
                error_data.get("type"),
                error_data.get("code"),
                error_data.get("param"),
            )
        else:
            logging.error("Message processing HTTP error: service_status=%s", status)
        if status == 401 and "api.openai.com" in response_url:
            user_message = "OpenAI не принял API-ключ. Проверьте OPENAI_API_KEY в Render."
        elif status == 429 and "api.openai.com" in getattr(exc.response, "url", ""):
            user_message = "Сейчас OpenAI не может обработать запрос: проверьте баланс и лимиты API."
        else:
            user_message = "Произошла техническая ошибка. Попробуйте отправить сообщение ещё раз."
        try:
            telegram_send(chat_id, user_message)
        except Exception as send_exc:
            safe_telegram_error("Failed to send error reply", send_exc)
        return "OK", 200
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        logging.error("Message processing failed: error_type=%s", type(exc).__name__)
        try:
            telegram_send(chat_id, "Не удалось обработать сообщение. Попробуйте ещё раз чуть позже.")
        except Exception as send_exc:
            safe_telegram_error("Failed to send error reply", send_exc)
        return "OK", 200
    except Exception as exc:
        logging.error("Unexpected message processing error: error_type=%s", type(exc).__name__)
        try:
            telegram_send(chat_id, "Возникла внутренняя ошибка. Попробуйте ещё раз.")
        except Exception as send_exc:
            safe_telegram_error("Failed to send error reply", send_exc)
        return "OK", 200

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
            logging.info("Telegram webhook setup succeeded; http_status=%s", response.status_code)
        except requests.RequestException as exc:
            safe_telegram_error("Failed to set Telegram webhook", exc)
    elif TELEGRAM_TOKEN_RAW.strip():
        logging.error("TELEGRAM_TOKEN format is invalid or multiple tokens were supplied.")
    else:
        logging.warning("TELEGRAM_TOKEN is not configured.")

    if not OPENAI_API_KEY:
        logging.warning("OPENAI_API_KEY is not configured; AI replies are disabled.")

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
