from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient, events
import os

app = FastAPI()

# Izinkan Frontend mengakses Backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ambil Variabel dari Railway (Pastikan sudah diisi di tab Variables)
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Inisialisasi Bot Client (Gunakan int untuk API_ID agar tidak error)
bot_client = TelegramClient('bot_session', int(API_ID), API_HASH)

@app.on_event("startup")
async def startup_event():
    # Menjalankan bot saat server mulai (Ini yang bikin garis merah hilang)
    await bot_client.start(bot_token=BOT_TOKEN)
    print("Backend Berhasil Online dan Bot Berjalan!")

@app.post("/register")
async def register(request: Request):
    try:
        data = await request.json()
        nama = data.get("name")
        phone = data.get("phone")
        
        # Kirim notifikasi ke Telegram kamu
        await bot_client.send_message('me', f"Ada pendaftar baru!\nNama: {nama}\nNomor: {phone}")
        
        return {"status": "success", "message": "Data terkirim"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/")
async def root():
    return {"message": "Server Hijau dan Aktif!"}

# Handler untuk interaksi bot jika diperlukan
@bot_client.on(events.CallbackQuery(data=b'req'))
async def handler(event):
    await event.answer("Meminta OTP...", alert=False)