
import logging
from telegram import Update, ChatPermissions, ChatMember, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler
)
from datetime import datetime, timedelta
import sqlite3
import re
import youtube_dl
import os
from pytube import YouTube
import subprocess
import threading

# تمكين التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# توكن البوت - استبدله بتوكن البوت الخاص بك
TOKEN = "7862387777:AAFBIkj58k5jUj_fY-GdsaI1gNZnLCY2N2s"

# حالات المحادثة
SET_WELCOME, SET_RULES, SET_ANTISPAM = range(3)
MUSIC_QUEUE = {}

# تهيئة قاعدة البيانات
def init_db():
    conn = sqlite3.connect('group_bot.db')
    c = conn.cursor()
    
    # جدول الأعضاء
    c.execute('''CREATE TABLE IF NOT EXISTS members
                 (user_id INTEGER, chat_id INTEGER, username TEXT, 
                  warnings INTEGER DEFAULT 0, join_date TEXT, 
                  PRIMARY KEY (user_id, chat_id))''')
    
    # جدول الإعدادات
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (chat_id INTEGER PRIMARY KEY, 
                  welcome_message TEXT,
                  rules TEXT,
                  antispam_enabled INTEGER DEFAULT 1,
                  max_warnings INTEGER DEFAULT 3,
                  music_enabled INTEGER DEFAULT 1)''')
    
    # جدول الأوسمة
    c.execute('''CREATE TABLE IF NOT EXISTS badges
                 (user_id INTEGER, chat_id INTEGER, 
                  badge_name TEXT, PRIMARY KEY (user_id, chat_id, badge_name))''')
    
    # جدول قوائم التشغيل
    c.execute('''CREATE TABLE IF NOT EXISTS playlists
                 (chat_id INTEGER, url TEXT, title TEXT, duration TEXT,
                  PRIMARY KEY (chat_id, url))''')
    
    conn.commit()
    conn.close()

init_db()

# ============ دوال المساعدة للموسيقى ============

def download_audio(url, chat_id):
    try:
        yt = YouTube(url)
        audio_stream = yt.streams.filter(only_audio=True).first()
        
        # إنشاء مجلد للمجموعة إذا لم يكن موجوداً
        if not os.path.exists(f"music/{chat_id}"):
            os.makedirs(f"music/{chat_id}")
        
        # تحميل الصوت
        out_file = audio_stream.download(output_path=f"music/{chat_id}")
        base, ext = os.path.splitext(out_file)
        new_file = base + '.mp3'
        
        # تحويل إلى mp3
        subprocess.run(['ffmpeg', '-i', out_file, '-codec:a', 'libmp3lame', new_file])
        os.remove(out_file)  # حذف الملف الأصلي
        
        return {
            'title': yt.title,
            'duration': str(timedelta(seconds=yt.length)),
            'file_path': new_file
        }
    except Exception as e:
        logger.error(f"Error downloading audio: {e}")
        return None

def play_next(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if chat_id in MUSIC_QUEUE and MUSIC_QUEUE[chat_id]['queue']:
        next_song = MUSIC_QUEUE[chat_id]['queue'].pop(0)
        audio_file = open(next_song['file_path'], 'rb')
        
        # إرسال الأغنية
        context.bot.send_audio(
            chat_id=chat_id,
            audio=audio_file,
            title=next_song['title'],
            duration=next_song['duration'],
            performer="YouTube Audio"
        )
        
        audio_file.close()
        
        # حذف الملف بعد الإرسال
        try:
            os.remove(next_song['file_path'])
        except Exception as e:
            logger.error(f"Error deleting audio file: {e}")
        
        # تحديث رسالة القائمة
        update_queue_message(update, context)

def update_queue_message(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if chat_id in MUSIC_QUEUE and 'queue_msg_id' in MUSIC_QUEUE[chat_id]:
        queue = MUSIC_QUEUE[chat_id]['queue']
        queue_text = "🎵 قائمة التشغيل الحالية:

"
        
        if queue:
            for i, song in enumerate(queue, 1):
                queue_text += f"{i}. {song['title']} ({song['duration']})
"
        else:
            queue_text += "القائمة فارغة حالياً"
        
        try:
            context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=MUSIC_QUEUE[chat_id]['queue_msg_id'],
                text=queue_text
            )
        except Exception as e:
            logger.error(f"Error updating queue message: {e}")

# ============ باقي الأوامر كما هي ============
