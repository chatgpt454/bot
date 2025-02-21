import logging
import asyncio
import nest_asyncio
import requests
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from io import BytesIO
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# ✅ Telegram Bot Token
TELEGRAM_TOKEN = '7457980064:AAH6Oxvo9deuM8qyjEqChhLefTPjYJCmmM0'

# ✅ Exchange Rate API (используется бесплатный API)
EXCHANGE_API_KEY = 'https://api.exchangerate-api.com/v4/latest/USD'

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Хранение данных пользователей
user_data = {}

# Поддерживаемые валюты
currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'UAH', 'RUB']

# Используем только украинский язык
default_language = 'UA'

# Переведенные категории и кнопки (украинский)
# Главное меню теперь включает 11 кнопок:
# 0: "➕ Додати дохід", 1: "➖ Додати витрати",
# 2: "📊 Баланс", 3: "📋 Історія",
# 4: "💱 Конвертер валют", 5: "💳 Борги",
# 6: "🏦 Кредити", 7: "💲 Вибір валюти",
# 8: "💡 Фінансові поради", 9: "⏰ Напоминання",
# 10: "❓ Help"
categories = {
    'UA': {
        'income': ['💰 Зарплата', '💸 Бонус', '💵 Фріланс', '💲 Інвестиції', '🎁 Подарунки', '🏆 Приз'],
        'expense': ['🍔 Їжа', '🏠 Оренда', '🚗 Транспорт', '🎉 Розваги', '💡 Комунальні', '📱 Телефон', '🛍 Шопінг', '💊 Здоров’я', '💻 Підписки'],
        'buttons': {
            'main': [
                "➕ Додати дохід", "➖ Додати витрати",
                "📊 Баланс", "📋 Історія",
                "💱 Конвертер валют", "💳 Борги",
                "🏦 Кредити", "💲 Вибір валюти",
                "💡 Фінансові поради", "⏰ Напоминання",
                "❓ Help"
            ]
        }
    }
}

# Финансовые советы (украинский)
financial_tips = {
    'UA': {
        'Savings': ["Окладайте 10% від доходу.", "Використовуйте додатки для бюджету.", "Скорочуйте непотрібні витрати."],
        'Investments': ["Почніть з індексних фондів.", "Диверсифікуйте свій портфель.", "Інвестуйте на довгий термін."],
        'Debt Management': ["Спочатку погашайте борги з високими відсотками.", "Уникайте нових боргів.", "Домовляйтесь про кращі умови."],
        'Expense Optimization': ["Відстежуйте свої витрати.", "Використовуйте купони та знижки.", "Обмежте витрати на ресторани."],
        'Business Ideas': ["Розпочніть побічний бізнес.", "Інвестуйте в електронну комерцію.", "Спробуйте фріланс."],
        'Random Tips': ["Завжди відкладай на непередбачені витрати.", "Навчіться управляти своїми фінансами.", "Регулярно переглядай бюджет."]
    }
}

# Функция для генерации текстового финансового отчёта
def generate_financial_report(user_id):
    data = user_data[user_id]
    income_list = data.get("income", [])
    expense_list = data.get("expense", [])
    total_income = sum(t["amount"] for t in income_list)
    total_expense = sum(t["amount"] for t in expense_list)
    balance = total_income - total_expense
    num_income = len(income_list)
    num_expense = len(expense_list)
    avg_income = total_income / num_income if num_income > 0 else 0
    avg_expense = total_expense / num_expense if num_expense > 0 else 0

    income_categories = {}
    for t in income_list:
        income_categories[t["category"]] = income_categories.get(t["category"], 0) + t["amount"]
    expense_categories = {}
    for t in expense_list:
        expense_categories[t["category"]] = expense_categories.get(t["category"], 0) + t["amount"]
    top_income = sorted(income_categories.items(), key=lambda x: x[1], reverse=True)[:3]
    top_expense = sorted(expense_categories.items(), key=lambda x: x[1], reverse=True)[:3]

    report = f"📊 **Фінансовий звіт:**\n"
    report += f"Загальний дохід: {total_income} {data['currency']}\n"
    report += f"Загальні витрати: {total_expense} {data['currency']}\n"
    report += f"Баланс: {balance} {data['currency']}\n\n"
    report += f"Кількість доходів: {num_income}, середній дохід: {avg_income:.2f} {data['currency']}\n"
    report += f"Кількість витрат: {num_expense}, середня витрата: {avg_expense:.2f} {data['currency']}\n\n"
    report += f"Топ 3 категорії доходів:\n"
    for cat, amt in top_income:
        report += f"- {cat}: {amt} {data['currency']}\n"
    report += f"\nТоп 3 категорії витрат:\n"
    for cat, amt in top_expense:
        report += f"- {cat}: {amt} {data['currency']}\n"

    if balance < 0:
        report += "\n⚠️ Увага! Ваші витрати перевищують дохід. Розгляньте можливість зниження витрат."
    else:
        report += "\n✅ Ваш баланс позитивний. Продовжуйте контролювати свої витрати."
    return report

# Функция для получения курсов валют
def get_exchange_rates(base_currency):
    try:
        response = requests.get(f"https://api.exchangerate-api.com/v4/latest/{base_currency}")
        data = response.json()
        return data.get('rates', {})
    except Exception as e:
        print(f"Error fetching exchange rates: {e}")
        return {}

# Фоновая задача для уведомлений по долгам/кредитам
async def check_debts(app):
    while True:
        now = datetime.now()
        for user_id, data in user_data.items():
            for debt_type in ["loans", "credits"]:
                for debt in data.get("debts", {}).get(debt_type, []):
                    if not debt.get("notified") and (debt["due_date"] - now).days <= 2:
                        try:
                            await app.bot.send_message(
                                chat_id=user_id,
                                text=f"🔔 Нагадування: {debt_type[:-1].capitalize()} '{debt['description']}' на суму {debt['amount']} {data['currency']} має термін погашення {debt['due_date'].strftime('%Y-%m-%d')}."
                            )
                            debt["notified"] = True
                        except Exception as e:
                            print(f"Error sending debt notification: {e}")
        await asyncio.sleep(60)

# Фоновая задача для уведомлений по напоминанням
async def check_reminders(app):
    while True:
        now = datetime.now()
        for user_id, data in user_data.items():
            for rem in data.get("reminders", []):
                if not rem.get("notified") and rem["due_date"] <= now:
                    try:
                        await app.bot.send_message(
                            chat_id=user_id,
                            text=f"⏰ Напоминання: {rem['text']}\n(Час: {rem['due_date'].strftime('%Y-%m-%d %H:%M')})"
                        )
                        rem["notified"] = True
                    except Exception as e:
                        print(f"Error sending reminder notification: {e}")
        await asyncio.sleep(60)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {
        "income": [],
        "expense": [],
        "currency": "USD",
        "language": default_language,
        "awaiting_input": None,
        "awaiting_edit": None,
        # Для боргів: зберігаємо окремо гроші, які ви дали (loans) і взяли (borrowed)
        "debts": {"loans": [], "borrowed": []},
        # Для кредитів: введення спрощено – сума, опис, термін (місяців)
        "credits": [],
        # Для напоминань
        "reminders": []
    }
    main_buttons = [
        "➕ Додати дохід", "➖ Додати витрати",
        "📊 Баланс", "📋 Історія",
        "💱 Конвертер валют", "💳 Борги",
        "🏦 Кредити", "💲 Вибір валюти",
        "💡 Фінансові поради", "⏰ Напоминання",
        "❓ Help"
    ]
    keyboard = [
        [KeyboardButton(main_buttons[0]), KeyboardButton(main_buttons[1])],
        [KeyboardButton(main_buttons[2]), KeyboardButton(main_buttons[3])],
        [KeyboardButton(main_buttons[4]), KeyboardButton(main_buttons[5])],
        [KeyboardButton(main_buttons[6]), KeyboardButton(main_buttons[7])],
        [KeyboardButton(main_buttons[8]), KeyboardButton(main_buttons[9])],
        [KeyboardButton(main_buttons[10])]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("💵 Виберіть дію:", reply_markup=reply_markup)

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **Інструкція користування ботом**\n\n"
        "➕ **Додати дохід** – Оберіть категорію доходу та введіть суму.\n"
        "➖ **Додати витрати** – Оберіть категорію витрат та введіть суму.\n"
        "📊 **Баланс** – Отримайте детальний звіт про доходи, витрати та баланс.\n"
        "💱 **Конвертер валют** – Введіть суму для конвертації (поточна валюта використовується для розрахунку).\n"
        "💲 **Вибір валюти** – Оберіть валюту для обліку.\n"
        "💳 **Борги** – Записуйте, що ви дали в борг (➕ Віддав) або взяли (➕ Брав), формат: сума, опис, дата (YYYY-MM-DD).\n"
        "🏦 **Кредити** – Записуйте кредити, формат: сума, опис, термін (в місяцях); дата погашення обчислюється автоматично.\n"
        "⏰ **Напоминання** – Додавайте заплановані напоминання, формат: текст, YYYY-MM-DD HH:MM.\n"
        "📋 **Історія** – Перегляньте список усіх транзакцій з можливістю редагування/видалення.\n"
        "💡 **Фінансові поради** – Отримайте випадкову пораду для покращення фінансів.\n"
        "❓ **Help** – Ця інструкція.\n\n"
        "Використовуйте команди /start та /help для початку роботи."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# Обработчик текстових повідомлень
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    main_buttons = categories[default_language]['buttons']['main']
    
    # Якщо текст збігається з кнопками головного меню, скидаємо стани
    if text in main_buttons:
        user_data[user_id]["awaiting_input"] = None
        user_data[user_id]["awaiting_edit"] = None

    # Якщо очікується введення для редагування запису
    if user_data[user_id].get("awaiting_edit"):
        try:
            new_value = text
            edit_info = user_data[user_id]["awaiting_edit"]
            trans_type = edit_info["type"]
            trans_id = edit_info["id"]
            updated = False
            if trans_type in ["income", "expense"]:
                try:
                    new_amount = float(new_value)
                    for trans in user_data[user_id][trans_type]:
                        if trans["id"] == trans_id:
                            trans["amount"] = new_amount
                            updated = True
                            await update.message.reply_text(f"✅ Запис '{trans['category']}' оновлено на {new_amount} {user_data[user_id]['currency']}.")
                            break
                except ValueError:
                    await update.message.reply_text("⚠️ Введіть число для редагування цієї транзакції.")
                    return
            elif trans_type in ["debt", "credit"]:
                try:
                    new_amount = float(new_value)
                    key = "loans" if trans_type == "debt" else None
                    if trans_type == "debt":
                        for d in user_data[user_id]["debts"]["loans"]:
                            if d["id"] == trans_id:
                                d["amount"] = new_amount
                                updated = True
                                await update.message.reply_text(f"✅ Запис оновлено на {new_amount} {user_data[user_id]['currency']}.")
                                break
                    else:
                        for d in user_data[user_id]["credits"]:
                            if d["id"] == trans_id:
                                d["amount"] = new_amount
                                # Перераховуємо дату погашення на основі терміну
                                months = d.get("term", 0)
                                d["due_date"] = datetime.now() + timedelta(days=30*months)
                                updated = True
                                await update.message.reply_text(f"✅ Кредит оновлено на {new_amount} {user_data[user_id]['currency']}.")
                                break
                except ValueError:
                    await update.message.reply_text("⚠️ Введіть число для редагування цієї записи.")
                    return
            elif trans_type == "reminder":
                for r in user_data[user_id]["reminders"]:
                    if r["id"] == trans_id:
                        r["text"] = new_value
                        updated = True
                        await update.message.reply_text(f"✅ Напоминання оновлено на: {new_value}")
                        break
            if not updated:
                await update.message.reply_text("⚠️ Запис не знайдено.")
            user_data[user_id]["awaiting_edit"] = None
        except Exception as e:
            await update.message.reply_text("⚠️ Сталася помилка при редагуванні.")
        return

    # Якщо очікується введення для додавання запису/конвертації/напоминання
    if user_data[user_id].get("awaiting_input"):
        action, category = user_data[user_id]["awaiting_input"]
        try:
            if action in ['income', 'expense', 'convert']:
                amount = float(text)
                transaction = {
                    "id": int(datetime.now().timestamp() * 1000),
                    "category": category,
                    "amount": amount,
                    "timestamp": datetime.now()
                }
                if action == 'income':
                    user_data[user_id]['income'].append(transaction)
                    await update.message.reply_text(f"✅ {category} на {amount} {user_data[user_id]['currency']} додано.")
                elif action == 'expense':
                    user_data[user_id]['expense'].append(transaction)
                    await update.message.reply_text(f"✅ {category} на {amount} {user_data[user_id]['currency']} додано.")
                elif action == 'convert':
                    rates = get_exchange_rates(user_data[user_id]['currency'])
                    converted = {cur: round(amount * rate, 2) for cur, rate in rates.items() if cur in currencies}
                    result = "\n".join([f"{cur}: {amt}" for cur, amt in converted.items()])
                    await update.message.reply_text(f"💱 Результати конвертації:\n{result}")
            elif action == 'debt':
                # Формат: сума, опис, дата (YYYY-MM-DD)
                parts = [p.strip() for p in text.split(",")]
                if len(parts) != 3:
                    raise ValueError
                debt_amount = float(parts[0])
                description = parts[1]
                due_date = datetime.strptime(parts[2], "%Y-%m-%d")
                debt_record = {
                    "id": int(datetime.now().timestamp() * 1000),
                    "amount": debt_amount,
                    "description": description,
                    "due_date": due_date,
                    "timestamp": datetime.now(),
                    "notified": False
                }
                user_data[user_id]["debts"]["loans"].append(debt_record)
                await update.message.reply_text(f"✅ Запис (віддав) на {debt_amount} {user_data[user_id]['currency']} додано. Термін: {due_date.strftime('%Y-%m-%d')}")
            elif action == 'borrow':
                # Формат: сума, опис, дата (YYYY-MM-DD)
                parts = [p.strip() for p in text.split(",")]
                if len(parts) != 3:
                    raise ValueError
                debt_amount = float(parts[0])
                description = parts[1]
                due_date = datetime.strptime(parts[2], "%Y-%m-%d")
                debt_record = {
                    "id": int(datetime.now().timestamp() * 1000),
                    "amount": debt_amount,
                    "description": description,
                    "due_date": due_date,
                    "timestamp": datetime.now(),
                    "notified": False
                }
                user_data[user_id]["debts"]["borrowed"].append(debt_record)
                await update.message.reply_text(f"✅ Запис (брав) на {debt_amount} {user_data[user_id]['currency']} додано. Термін: {due_date.strftime('%Y-%m-%d')}")
            elif action == 'credit':
                # Формат: сума, опис, термін (в місяцях)
                parts = [p.strip() for p in text.split(",")]
                if len(parts) != 3:
                    raise ValueError
                credit_amount = float(parts[0])
                description = parts[1]
                term_months = int(parts[2])
                due_date = datetime.now() + timedelta(days=30 * term_months)
                credit_record = {
                    "id": int(datetime.now().timestamp() * 1000),
                    "amount": credit_amount,
                    "description": description,
                    "term": term_months,
                    "due_date": due_date,
                    "timestamp": datetime.now(),
                    "notified": False
                }
                user_data[user_id]["credits"].append(credit_record)
                await update.message.reply_text(f"✅ Кредит на {credit_amount} {user_data[user_id]['currency']} додано. Термін погашення через {term_months} місяців.")
            elif action == 'reminder':
                # Формат: текст, YYYY-MM-DD HH:MM
                parts = [p.strip() for p in text.split(",", 1)]
                if len(parts) != 2:
                    raise ValueError
                reminder_text = parts[0]
                due_dt = datetime.strptime(parts[1], "%Y-%m-%d %H:%M")
                reminder_record = {
                    "id": int(datetime.now().timestamp() * 1000),
                    "text": reminder_text,
                    "due_date": due_dt,
                    "timestamp": datetime.now(),
                    "notified": False
                }
                user_data[user_id]["reminders"].append(reminder_record)
                await update.message.reply_text(f"✅ Напоминання додано: '{reminder_text}' на {due_dt.strftime('%Y-%m-%d %H:%M')}")
            user_data[user_id]["awaiting_input"] = None
        except ValueError:
            await update.message.reply_text("⚠️ Невірний формат введення.\nДля транзакцій введіть число.\nДля боргових записів – дані у форматі:\nсума, опис, дата (YYYY-MM-DD)\nДля кредитів – дані у форматі:\nсума, опис, термін (місяців)\nДля напоминань – дані у форматі:\nтекст, YYYY-MM-DD HH:MM")
        return

    # Головне меню
    if text == main_buttons[0]:
        # "Додати дохід"
        income_cats = categories[default_language]['income']
        keyboard = []
        for i in range(0, len(income_cats), 2):
            row = [InlineKeyboardButton(income_cats[i], callback_data=f'income_{income_cats[i]}')]
            if i + 1 < len(income_cats):
                row.append(InlineKeyboardButton(income_cats[i+1], callback_data=f'income_{income_cats[i+1]}'))
            keyboard.append(row)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("💵 Виберіть категорію доходу:\n(Натисніть на кнопку)", reply_markup=reply_markup)
    elif text == main_buttons[1]:
        # "Додати витрати"
        expense_cats = categories[default_language]['expense']
        keyboard = []
        for i in range(0, len(expense_cats), 2):
            row = [InlineKeyboardButton(expense_cats[i], callback_data=f'expense_{expense_cats[i]}')]
            if i + 1 < len(expense_cats):
                row.append(InlineKeyboardButton(expense_cats[i+1], callback_data=f'expense_{expense_cats[i+1]}'))
            keyboard.append(row)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("💸 Виберіть категорію витрат:", reply_markup=reply_markup)
    elif text == main_buttons[2]:
        # "Баланс"
        report = generate_financial_report(user_id)
        await update.message.reply_text(report, parse_mode="Markdown")
    elif text == main_buttons[3]:
        # "Історія"
        if not user_data[user_id]["income"] and not user_data[user_id]["expense"]:
            await update.message.reply_text("Немає транзакцій.")
        else:
            if user_data[user_id]["income"]:
                await update.message.reply_text("💰 Доходи:")
                for trans in user_data[user_id]["income"]:
                    trans_msg = (f"ID: {trans['id']}\nКатегорія: {trans['category']}\n"
                                 f"Сума: {trans['amount']} {user_data[user_id]['currency']}\n"
                                 f"Час: {trans['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                    keyboard = [[
                        InlineKeyboardButton("Редагувати", callback_data=f'edit_income_{trans["id"]}'),
                        InlineKeyboardButton("Видалити", callback_data=f'delete_income_{trans["id"]}')
                    ]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(trans_msg, reply_markup=reply_markup)
            if user_data[user_id]["expense"]:
                await update.message.reply_text("💸 Витрати:")
                for trans in user_data[user_id]["expense"]:
                    trans_msg = (f"ID: {trans['id']}\nКатегорія: {trans['category']}\n"
                                 f"Сума: {trans['amount']} {user_data[user_id]['currency']}\n"
                                 f"Час: {trans['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                    keyboard = [[
                        InlineKeyboardButton("Редагувати", callback_data=f'edit_expense_{trans["id"]}'),
                        InlineKeyboardButton("Видалити", callback_data=f'delete_expense_{trans["id"]}')
                    ]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(trans_msg, reply_markup=reply_markup)
    elif text == main_buttons[4]:
        # "Конвертер валют"
        user_data[user_id]["awaiting_input"] = ("convert", "")
        await update.message.reply_text("💱 Введіть суму для конвертації:")
    elif text == main_buttons[5]:
        # "Борги" – меню для боргових записів (віддав / брав)
        keyboard = [
            [InlineKeyboardButton("➕ Віддав", callback_data="debt_add")],
            [InlineKeyboardButton("➕ Брав", callback_data="borrow_add")],
            [InlineKeyboardButton("📋 Переглянути борги", callback_data="debt_view")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("💳 Оберіть дію для боргів:\n(Для додавання введіть дані у форматі: сума, опис, дата (YYYY-MM-DD))", reply_markup=reply_markup)
    elif text == main_buttons[6]:
        # "Кредити" – меню для кредитів (введення у форматі: сума, опис, термін (місяців))
        keyboard = [
            [InlineKeyboardButton("➕ Додати кредит", callback_data="credit_add")],
            [InlineKeyboardButton("📋 Переглянути кредити", callback_data="credit_view")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🏦 Оберіть дію для кредитів:\n(Для додавання введіть дані у форматі: сума, опис, термін (місяців))", reply_markup=reply_markup)
    elif text == main_buttons[7]:
        # "Вибір валюти"
        keyboard = [[InlineKeyboardButton(cur, callback_data=f'currency_{cur}')] for cur in currencies]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("💲 Оберіть валюту для обліку:", reply_markup=reply_markup)
    elif text == main_buttons[8]:
        # "Фінансові поради"
        tip_category = random.choice(list(financial_tips[default_language].keys()))
        tip = random.choice(financial_tips[default_language][tip_category])
        await update.message.reply_text(f"💡 Порада: {tip}")
    elif text == main_buttons[9]:
        # "Напоминання" – меню для напоминань
        keyboard = [
            [InlineKeyboardButton("➕ Додати напоминання", callback_data="reminder_add")],
            [InlineKeyboardButton("📋 Переглянути напоминання", callback_data="reminder_view")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("⏰ Оберіть дію для напоминань:\n(Введіть дані у форматі: текст, YYYY-MM-DD HH:MM)", reply_markup=reply_markup)
    elif text == main_buttons[10]:
        # "Help"
        await help_command(update, context)

# Обработчик inline-кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    data = query.data.split("_")
    action = data[0]
    
    if action in ['income', 'expense']:
        category = "_".join(data[1:])
        user_data[user_id]["awaiting_input"] = (action, category)
        await query.edit_message_text(f"Введіть суму для '{category}':")
    elif action == 'currency':
        selected_currency = data[1]
        user_data[user_id]['currency'] = selected_currency
        await query.edit_message_text(f"Ваша валюта змінена на {selected_currency}.")
    elif action == 'debt':
        # Дії для боргів: "debt_add" або "debt_view"
        subaction = data[1]
        if subaction == "add":
            user_data[user_id]["awaiting_input"] = ("debt", "")
            await query.edit_message_text("Введіть дані боргу (віддав) у форматі:\nсума, опис, дата (YYYY-MM-DD)")
        elif subaction == "view":
            debts = user_data[user_id].get("debts", {"loans": []})
            if not debts["loans"]:
                await query.edit_message_text("Немає записів боргів.")
            else:
                messages = []
                for d in debts["loans"]:
                    msg = (f"ID: {d['id']}\nСума: {d['amount']} {user_data[user_id]['currency']}\n"
                           f"Опис: {d['description']}\nТермін: {d['due_date'].strftime('%Y-%m-%d')}")
                    messages.append(msg)
                await query.edit_message_text("\n\n".join(messages))
    elif action == 'borrow':
        # Дії для "Брав" (взяти в борг)
        subaction = data[1]  # тут, якщо callback = "borrow_add"
        if subaction == "add":
            user_data[user_id]["awaiting_input"] = ("borrow", "")
            await query.edit_message_text("Введіть дані боргу (брав) у форматі:\nсума, опис, дата (YYYY-MM-DD)")
    elif action == 'credit':
        subaction = data[1]
        if subaction == "add":
            user_data[user_id]["awaiting_input"] = ("credit", "")
            await query.edit_message_text("Введіть дані кредиту у форматі:\nсума, опис, термін (місяців)")
        elif subaction == "view":
            credits = user_data[user_id].get("credits", [])
            if not credits:
                await query.edit_message_text("Немає записів кредитів.")
            else:
                messages = []
                for d in credits:
                    msg = (f"ID: {d['id']}\nСума: {d['amount']} {user_data[user_id]['currency']}\n"
                           f"Опис: {d['description']}\nТермін: {d['term']} місяців\n"
                           f"Погашення: {d['due_date'].strftime('%Y-%m-%d')}")
                    messages.append(msg)
                await query.edit_message_text("\n\n".join(messages))
    elif action == 'reminder':
        subaction = data[1]
        if subaction == "add":
            user_data[user_id]["awaiting_input"] = ("reminder", "")
            await query.edit_message_text("Введіть дані напоминання у форматі:\nтекст, YYYY-MM-DD HH:MM")
        elif subaction == "view":
            reminders = user_data[user_id].get("reminders", [])
            if not reminders:
                await query.edit_message_text("Немає напоминань.")
            else:
                messages = []
                for r in reminders:
                    msg = (f"ID: {r['id']}\nТекст: {r['text']}\nЧас: {r['due_date'].strftime('%Y-%m-%d %H:%M')}")
                    messages.append(msg)
                await query.edit_message_text("\n\n".join(messages))
    elif action.startswith('delete'):
        trans_type = data[1]  # може бути income, expense, debt, credit або reminder
        trans_id = int(data[2])
        if trans_type in ['income', 'expense']:
            original_count = len(user_data[user_id][trans_type])
            user_data[user_id][trans_type] = [t for t in user_data[user_id][trans_type] if t["id"] != trans_id]
            if len(user_data[user_id][trans_type]) < original_count:
                await query.edit_message_text("✅ Запис видалено.")
            else:
                await query.edit_message_text("⚠️ Запис не знайдено.")
        elif trans_type in ['debt', 'credit']:
            if trans_type == "debt":
                key = "loans"
                original = len(user_data[user_id]["debts"][key])
                user_data[user_id]["debts"][key] = [d for d in user_data[user_id]["debts"][key] if d["id"] != trans_id]
            else:
                key = "credits"
                original = len(user_data[user_id]["credits"])
                user_data[user_id]["credits"] = [d for d in user_data[user_id]["credits"] if d["id"] != trans_id]
            if (trans_type == "debt" and len(user_data[user_id]["debts"][key]) < original) or \
               (trans_type == "credit" and len(user_data[user_id]["credits"]) < original):
                await query.edit_message_text("✅ Запис видалено.")
            else:
                await query.edit_message_text("⚠️ Запис не знайдено.")
        elif trans_type == "reminder":
            original = len(user_data[user_id]["reminders"])
            user_data[user_id]["reminders"] = [r for r in user_data[user_id]["reminders"] if r["id"] != trans_id]
            if len(user_data[user_id]["reminders"]) < original:
                await query.edit_message_text("✅ Напоминання видалено.")
            else:
                await query.edit_message_text("⚠️ Напоминання не знайдено.")
    elif action.startswith('edit'):
        trans_type = data[1]
        trans_id = int(data[2])
        category = None
        if trans_type in ['income', 'expense']:
            for t in user_data[user_id][trans_type]:
                if t["id"] == trans_id:
                    category = t["category"]
                    break
        elif trans_type in ['debt', 'credit']:
            if trans_type == "debt":
                key = "loans"
                for d in user_data[user_id]["debts"][key]:
                    if d["id"] == trans_id:
                        category = d["description"]
                        break
            else:
                for d in user_data[user_id]["credits"]:
                    if d["id"] == trans_id:
                        category = d["description"]
                        break
        elif trans_type == "reminder":
            for r in user_data[user_id]["reminders"]:
                if r["id"] == trans_id:
                    category = r["text"]
                    break
        if category:
            user_data[user_id]["awaiting_edit"] = {"type": trans_type, "id": trans_id}
            await query.edit_message_text(f"Введіть нове значення для '{category}':")
        else:
            await query.edit_message_text("⚠️ Запис не знайдено.")

# Запуск бота
async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    asyncio.create_task(check_debts(app))
    asyncio.create_task(check_reminders(app))
    print("🚀 Bot is running. Type /start or /help to begin.")
    await app.run_polling()

if __name__ == '__main__':
    nest_asyncio.apply()
    asyncio.run(main())
