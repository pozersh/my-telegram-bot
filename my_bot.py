from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import re
import os
import psycopg2
from datetime import datetime

# --- Настройки ---
# Бот будет брать эти данные из "секретного хранилища" на сервере Render
TOKEN = os.environ.get('TELEGRAM_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID'))
DATABASE_URL = os.environ.get('DATABASE_URL')
# ------------------

def db_query(query, params=None, fetch=None):
    """Универсальная функция для работы с базой данных"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(query, params)
    if fetch == "one":
        result = cur.fetchone()
    elif fetch == "all":
        result = cur.fetchall()
    else:
        result = None
    conn.commit()
    cur.close()
    conn.close()
    return result

def setup_database():
    """Создает таблицу для черного списка, если ее нет"""
    query = """
    CREATE TABLE IF NOT EXISTS blocklist (
        user_id BIGINT PRIMARY KEY,
        block_date TEXT
    );
    """
    db_query(query)

# --- Основные функции бота ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.from_user.first_name
    await update.message.reply_text(f'Здравствуйте, {user_name}! Я буду рада вас послушать. Можете обратиться ко мне за советом, вопросом и даже поддержкой. Давайте будем друг друга уважать. Если Ваше сообщение в течении двух дней осталось без ответа рекомедую отправить вновь. Хорошего настроения!')

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    
    # Проверка на блокировку в базе данных
    if db_query("SELECT 1 FROM blocklist WHERE user_id = %s", (user.id,), fetch="one"):
        await update.message.reply_text("Вы вели себя неподобающе, так что попали в черный список. Подумайте над своим поведением, Вам запрещено со мной общаться.")
        return

    message = update.message
    await message.forward(chat_id=ADMIN_ID)
    
    hidden_header = f"<ID:{user.id}><MID:{message.message_id}>"
    user_info = f"@{user.username}" if user.username else f"{user.full_name}"
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"👆 Отвечать на ЭТО сообщение.\nСообщение от: {user_info}\n{hidden_header}"
    )
    await message.reply_text('Ваше сообщение было услышано. Ожидайте ответа.')

async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id == ADMIN_ID and update.message.reply_to_message:
        original_message_text = update.message.reply_to_message.text
        try:
            user_id_match = re.search(r"<ID:(\d+)>", original_message_text)
            message_id_match = re.search(r"<MID:(\d+)>", original_message_text)
            if user_id_match and message_id_match:
                user_id = int(user_id_match.group(1))
                message_id = int(message_id_match.group(1))
                await context.bot.copy_message(chat_id=user_id, from_chat_id=ADMIN_ID, message_id=update.message.message_id, reply_to_message_id=message_id)
                await update.message.reply_text('Ответ успешно отправлен.')
            else:
                await update.message.reply_text('Не удалось найти данные. Отвечайте на служебное сообщение с ID.')
        except Exception as e:
            print(e)
            await update.message.reply_text('Произошла ошибка при отправке ответа.')

# --- Админские команды ---

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        user_id_to_block = int(context.args[0])
        block_date = datetime.now().strftime("%Y-%m-%d %H:%M")
        db_query("INSERT INTO blocklist (user_id, block_date) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (user_id_to_block, block_date))
        await update.message.reply_text(f"Пользователь {user_id_to_block} заблокирован.")
    except (IndexError, ValueError):
        await update.message.reply_text("Ошибка! Используйте: /block ID_пользователя")

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        user_id_to_unblock = int(context.args[0])
        db_query("DELETE FROM blocklist WHERE user_id = %s", (user_id_to_unblock,))
        await update.message.reply_text(f"Пользователь {user_id_to_unblock} разблокирован.")
    except (IndexError, ValueError):
        await update.message.reply_text("Ошибка! Используйте: /unblock ID_пользователя")

async def show_blocklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID: return
    blocked_users = db_query("SELECT user_id, block_date FROM blocklist", fetch="all")
    if not blocked_users:
        await update.message.reply_text("Черный список пуст!")
    else:
        message = "🔒 Черный список:\n\n"
        for user_id, block_date in blocked_users:
            message += f"• ID: `{user_id}`\n  (Заблокирован: {block_date})\n"
        await update.message.reply_text(message, parse_mode='Markdown')

def main():
    setup_database() # Убеждаемся, что таблица в базе данных создана
    
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем админские команды
    application.add_handler(CommandHandler("block", block_user))
    application.add_handler(CommandHandler("unblock", unblock_user))
    application.add_handler(CommandHandler("blocklist", show_blocklist))
    
    application.add_handler(CommandHandler("start", start))
    
    user_filter = filters.ALL & ~filters.COMMAND & ~filters.Chat(chat_id=ADMIN_ID)
    application.add_handler(MessageHandler(user_filter, forward_to_admin))
    
    admin_filter = filters.ALL & ~filters.COMMAND & filters.Chat(chat_id=ADMIN_ID)
    application.add_handler(MessageHandler(admin_filter, reply_to_user))
    
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
