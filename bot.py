import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import os

load_dotenv()

URL_BASE = os.getenv("URL_BASE")

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

def gen_markup():
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(InlineKeyboardButton(
        "Authorize me", url=f'{URL_BASE}authorize'))
    return markup


@bot.message_handler(commands=['start'])
def send_welcome(message):

    bot.send_message(chat_id=message.from_user.id,
                     text="Hi here! Please authorize me to set up a Gmail integration.", reply_markup=gen_markup())


bot.polling()
