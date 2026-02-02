from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
import os

# 1. Definisikan 'app' terlebih dahulu
app = FastAPI()

# 2. Tambahkan Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Pengaturan Telegram
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot_client = TelegramClient('bot_session', int(API_ID), API_HASH)

# 4. Fungsi-fungsi lainnya (startup, register, root)
@app.on_event("startup")
async def startup_event():
    await bot_client.start(bot_token=BOT_TOKEN)

@app.post("/register")
async def register(request: Request):
    data = await request.json()
    # ... isi kode kirim telegram kamu ...
    return {"status": "success"}