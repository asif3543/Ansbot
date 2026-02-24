import telebot
username = "@Kaamkarkaam_bot"
TOKEN = "8732499343:AAF2Zg6qj1gtPZdWfLygzdX3OVgnW6DHlF4"
bot = telebot.TeleBot(8732499343:AAF2Zg6qj1gtPZdWfLygzdX3OVgnW6DHlF4)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message,"Anime Bot Ready 😈")

bot.polling()
