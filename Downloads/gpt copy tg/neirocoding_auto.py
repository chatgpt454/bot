import asyncio
import re
import os
import random
import openai
import time
from telethon import TelegramClient
from telethon.errors import RPCError, SessionPasswordNeededError
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

# 🔑 Данные для подключения (через переменные окружения для Railway)
api_id = 21919270
api_hash = 'a25517a604bf99d413bbf3140d3b5962'
phone = '+380990042029'
openai.api_key = os.getenv('OPENAI_API_KEY')

# Создаём клиент OpenAI
client_openai = openai.OpenAI(api_key=openai.api_key)

# 📢 Каналы
source_channels = ['@Proglib', '@tproger']
destination_channel = '@neirocoding'

# 🧠 Клиент Telegram
client = TelegramClient('telegram_session', api_id, api_hash)

# 📂 Файл для последнего ID
last_id_file = "last_message_id.txt"

# 🚫 Регулярки
phone_pattern = r'\+?\d[\d\s\-\(\)]{7,}\d'
username_pattern = r'@\w+'
url_pattern = r'https?://\S+'

# 🔍 Ключевые слова
keywords = [
    'code', 'coding', 'программирование', 'разработка', 'development',
    'бот', 'bot', 'автоматизация', 'automation', 'AI', 'ИИ',
    'фриланс', 'freelance', 'заработок', 'money', 'работа', 'job',
    'контент', 'content', 'маркетинг', 'marketing', 'лендинг', 'landing',
    'дизайн', 'design', 'UI', 'UX', 'интерфейс',
    'tech', 'IT', 'технологии', 'software', 'программа', 'tools', 'инструменты',
    'стартап', 'startup', 'продукт', 'product', 'продажи', 'sales',
    'тренды', 'trends', 'новости', 'news', 'гаджеты', 'gadgets'
]

# Максимум постов в день
MAX_POSTS_PER_DAY = 10

def clean_text(text):
    text = re.sub(phone_pattern, '[номер скрыт]', text)
    text = re.sub(username_pattern, '', text)
    text = re.sub(url_pattern, '[ссылка удалена]', text)
    return text.strip()

def generate_hook(text):
    prompt = f"Придумай короткий (1-5 слов), лёгкий и завлекающий заголовок для IT-поста с смайликами:\n{text}"
    response = client_openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=20
    )
    return response.choices[0].message.content.strip()

def unique_text(text):
    prompt = f"Перепиши текст в лёгком, простом и завлекающем стиле для IT-шников и фрилансеров, добавь смайлики и используй **жирный** или *курсив* для выделения:\n{text}"
    response = client_openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200
    )
    return response.choices[0].message.content

def add_it_hashtags(text):
    hashtags = []
    if re.search(r'code|coding|программирование|разработка|development', text, re.IGNORECASE):
        hashtags.append('#кодинг 💻')
    if re.search(r'бот|bot|автоматизация|automation|AI|ИИ', text, re.IGNORECASE):
        hashtags.append('#автоматизация 🤖')
    if re.search(r'фриланс|freelance|заработок|money|работа|job', text, re.IGNORECASE):
        hashtags.append('#фриланс 💸')
    if re.search(r'контент|content|маркетинг|marketing|лендинг|landing', text, re.IGNORECASE):
        hashtags.append('#контент 📝')
    if re.search(r'дизайн|design|UI|UX|интерфейс', text, re.IGNORECASE):
        hashtags.append('#дизайн 🎨')
    if re.search(r'tech|IT|технологии|software|программа|tools|инструменты', text, re.IGNORECASE):
        hashtags.append('#техно ⚙️')
    if re.search(r'стартап|startup|продукт|product|продажи|sales', text, re.IGNORECASE):
        hashtags.append('#стартапы 🚀')
    if re.search(r'тренды|trends|новости|news|гаджеты|gadgets', text, re.IGNORECASE):
        hashtags.append('#тренды 🔥')
    return text + "\n\n" + ' '.join(sorted(set(hashtags)))

def get_last_message_id():
    if os.path.exists(last_id_file):
        with open(last_id_file, 'r') as file:
            return int(file.read())
    return 0

def save_last_message_id(message_id):
    with open(last_id_file, 'w') as file:
        file.write(str(message_id))

async def copy_filtered_messages():
    print("🚀 Запуск: 10 постов в день...")
    await client.connect()

    if not await client.is_user_authorized():
        print("❗ Авторизация...")
        try:
            await client.send_code_request(phone)
            code = input("Введите код из Telegram: ")
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = input("Введите пароль 2FA: ")
            await client.sign_in(password=password)

    destination = await client.get_input_entity(destination_channel)
    last_message_id = get_last_message_id()
    all_messages = []

    for source_channel in source_channels:
        try:
            source = await client.get_input_entity(source_channel)
            print(f"🔗 Парсинг {source_channel}...")
            async for message in client.iter_messages(source):
                if message.id > last_message_id and message.text and any(keyword.lower() in message.text.lower() for keyword in keywords):
                    all_messages.append((source_channel, message))
        except Exception as e:
            print(f"❌ Ошибка доступа к {source_channel}: {e}")

    all_messages.sort(key=lambda x: x[1].id, reverse=True)
    posts_to_send = all_messages[:MAX_POSTS_PER_DAY]
    message_count = 0

    for i, (source_channel, message) in enumerate(posts_to_send):
        media_files = []
        cleaned_text = clean_text(message.text or '')
        
        hook = generate_hook(cleaned_text)
        unique_caption = unique_text(cleaned_text)
        final_text = f"{hook}\n\n{unique_caption}"
        final_text = add_it_hashtags(final_text[:500])
        final_caption = final_text[:1024]

        if isinstance(message.media, MessageMediaPhoto):
            media_files.append(message.media.photo)
        elif isinstance(message.media, MessageMediaDocument):
            media_files.append(message.media.document)

        try:
            if media_files:
                await client.send_file(destination, media_files, caption=final_caption)
                print(f"📸 Отправлен альбом из {source_channel} (ID={message.id})")
            else:
                await client.send_message(destination, final_caption)
                print(f"💬 Отправлен текст из {source_channel} (ID={message.id})")

            message_count += 1
            save_last_message_id(message.id)
            if i < len(posts_to_send) - 1:
                await asyncio.sleep(3600)  # 1 час = 3600 секунд

        except RPCError as e:
            print(f"❌ Ошибка: {e}")
            if "FloodWait" in str(e):
                wait_time = int(re.search(r'(\d+)', str(e)).group(1))
                await asyncio.sleep(wait_time)

    print(f"\n🎉 День завершён! Скопировано {message_count} сообщений.")
    await client.disconnect()

def job():
    asyncio.run(copy_filtered_messages())

def run_forever():
    while True:
        job()
        print("⏳ Ожидаем следующий день для запуска...")
        time.sleep(86400)  # 24 часа = 86400 секунд

if __name__ == "__main__":
    run_forever()