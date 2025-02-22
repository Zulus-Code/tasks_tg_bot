import gspread
import os
from dotenv import load_dotenv
from urllib.parse import quote, unquote
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# Загрузка переменных окружения
load_dotenv()

# Конфигурация из .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_SHEETS_CREDS = os.getenv("GOOGLE_SHEETS_CREDS")
MAIN_SHEET_NAME = "Tasks"  # Убедитесь, что название листа верное

# Подключение к Google Sheets
def connect_to_sheets(sheet_name="Выполнение"):
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDS, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        
        try:
            return spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=3)
            if sheet_name == "Выполнение":
                worksheet.append_row(["Задача", "Дата", "Результат"])
            return worksheet
    except Exception as e:
        raise Exception(f"Ошибка подключения к Google Sheets: {e}")

# Кодирование задачи для callback_data
def encode_task(task: str, max_bytes: int) -> str:
    encoded = quote(task)
    encoded_bytes = encoded.encode('utf-8')[:max_bytes]
    return encoded_bytes.decode('utf-8', 'ignore')

# Декодирование задачи из callback_data
def decode_task(encoded_task: str) -> str:
    return unquote(encoded_task)

# Получение задач на сегодня
def get_today_tasks(sheet):
    try:
        days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        today_index = datetime.today().weekday()
        today_col = days[today_index] if today_index != 6 else "Вс"

        data = sheet.get_all_values()
        if not data or len(data[0]) < 1:
            return []

        headers = data[0]
        if today_col not in headers:
            return []

        col_index = headers.index(today_col)
        tasks = []

        for row in data[1:]:
            if len(row) > col_index and row[col_index].strip().upper() == "TRUE":
                tasks.append(row[0].strip())

        return tasks
    except Exception as e:
        print(f"Ошибка при получении задач: {e}")
        return []

# Генерация кнопок
def create_task_buttons(task):
    # Максимальная длина для encoded_task в байтах (64 - длина префикса)
    max_bytes = 57  # cancel| занимает 7 символов -> 64-7=57
    encoded_task = encode_task(task, max_bytes)
    
    keyboard = [
        [
            InlineKeyboardButton("✔ Выполнено", callback_data=f"done|{encoded_task}"),
            InlineKeyboardButton("✘ Отмена", callback_data=f"cancel|{encoded_task}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Обработчик /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sheet = connect_to_sheets(MAIN_SHEET_NAME)
        tasks = get_today_tasks(sheet)
        
        if tasks:
            for task in tasks:
                await update.message.reply_text(
                    text=f"Задача: {task}",
                    reply_markup=create_task_buttons(task)
                )
        else:
            await update.message.reply_text("🎉 Отличные новости! Сегодня задач нет.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {str(e)}")

# Обработчик кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        if "|" not in data:
            raise ValueError("Неверный формат данных")
        
        action, encoded_task = data.split("|", 1)
        task = decode_task(encoded_task)
        
        if action not in ["done", "cancel"]:
            raise ValueError("Неверное действие")

        emoji_result = "✔" if action == "done" else "✘"
        
        if log_task_result(task, emoji_result):
            await query.edit_message_text(text=f"{query.message.text}\nСтатус: {emoji_result}")
        else:
            await query.edit_message_text(text=f"{query.message.text}\n⚠️ Ошибка сохранения!")
    except Exception as e:
        print(f"Ошибка обработки кнопки: {e}")
        await query.edit_message_text(text="⚠️ Произошла ошибка. Попробуйте снова.")

# Логирование результата
def log_task_result(task_name, result):
    try:
        sheet = connect_to_sheets("Выполнение")
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([task_name, current_time, result])
        return True
    except Exception as e:
        print(f"Ошибка записи в таблицу: {e}")
        return False

# Запуск бота
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.run_polling()

if __name__ == "__main__":
    main()