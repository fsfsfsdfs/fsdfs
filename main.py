from msilib import add_data
import telebot
from telebot import types
import sqlite3
import time
import threading
import re

bot_token = '5315502911:AAHFhNiFHW6omGgMoZkDj_NtfHhRq-Uzgjg'
bot = telebot.TeleBot(bot_token)

conn = sqlite3.connect('school.db', check_same_thread=False)
c = conn.cursor()

# Создать таблицы если они не существуют
c.execute('''CREATE TABLE IF NOT EXISTS users
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, first_name TEXT, last_name TEXT, username TEXT, nickname TEXT, age INTEGER, gender TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS schedule
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, group_name TEXT, subject TEXT, start_time TEXT, FOREIGN KEY(user_id) REFERENCES users(user_id))''')

c.execute('''CREATE TABLE IF NOT EXISTS homework
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, description TEXT, due_time TEXT, FOREIGN KEY(user_id) REFERENCES users(user_id))''')

c.execute('''CREATE TABLE IF NOT EXISTS survey
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, question TEXT, options TEXT, due_time TEXT, FOREIGN KEY(user_id) REFERENCES users(user_id))''')

c.execute('''CREATE TABLE IF NOT EXISTS faq
             (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, answer TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS admins
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE)''')

conn.commit()

def add_admin(user_id):
    try:
        c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def insert_data(table, **kwargs):
    try:
        columns = ', '.join(kwargs.keys())
        placeholders = ', '.join('?' * len(kwargs))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        c.execute(query, tuple(kwargs.values()))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Ошибка при добавлении данных: {e}")
        return False

def get_data(table, where_clause=None, **kwargs):
    try:
        if where_clause:
            query = f"SELECT * FROM {table} WHERE {where_clause}"
            c.execute(query, tuple(kwargs.values()))
        else:
            c.execute(f"SELECT * FROM {table}")
        return c.fetchall()
    except sqlite3.Error as e:
        print(f"Ошибка при получении данных: {e}")
        return None

def send_reminder():
    current_time = time.strftime('%H:%M')
    schedule = get_data('schedule', start_time=current_time)
    if schedule:
        for row in schedule:
            user_id = row[1]
            if row[4] > current_time:
                bot.send_message(user_id, "Напоминание: скоро у вас начнется урок!")

def create_inline_keyboard(buttons):
    keyboard = types.InlineKeyboardMarkup()
    for button_text, callback_data in buttons.items():
        button = types.InlineKeyboardButton(text=button_text, callback_data=callback_data)
        keyboard.add(button)
    return keyboard

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    user = get_data('users', user_id=user_id)
    admin = get_data('admins', user_id=user_id)

    if not user:
        bot.send_message(message.chat.id, "Привет, меня зовут SchoolBot! Я помогу тебе узнать расписание уроков, получить домашние задания и многое другое. Чтобы начать, пожалуйста, зарегистрируйся.")
        bot.send_message(message.chat.id, "Напиши /register, чтобы зарегистрироваться.")
    else:
        buttons = {
            "Расписание уроков": "schedule",
            "Домашние задания": "homework",
            "FAQ": "faq",
            "Опрос": "survey"
        }

        if admin:
            buttons.update({
                "Добавить домашнее задание": "add_homework",
                "Добавить расписание": "add_schedule",
                "Техподдержка": "support",
                "Управление администраторами": "manage_admins"
            })

        bot.send_message(message.chat.id, "Привет, SchoolBot! Вот что я могу сделать:", reply_markup=create_inline_keyboard(buttons))

@bot.message_handler(commands=['ids'])
def id(message):
    user_id = message.from_user.id
    bot.send_message('Ваш айди: ', user_id)

@bot.message_handler(commands=['register'])
def register(message):
    user_id = message.from_user.id
    if get_data('users', user_id=user_id):
        bot.send_message(message.chat.id, "Вы уже зарегистрированы.")
    else:
        bot.send_message(message.chat.id, "Пожалуйста, введите ваше имя.")

@bot.message_handler(func=lambda message: message.text and message.text.startswith("/add_"))
def add_data_for_admin(message):
    user_id = message.from_user.id
    admin = get_data('admins', user_id=user_id)

    if not admin:
        bot.send_message(message.chat.id, "У вас нет административных прав.")
        return

    text_parts = message.text.split()
    if len(text_parts) < 2:
        bot.send_message(message.chat.id, "Неверный формат команды. Используйте /add_homework или /add_schedule.")
        return

    command = text_parts[1]
    if command == "add_homework":
        if not re.match(r'^/add_homework\s*$', message.text):
            bot.send_message(message.chat.id, "Неверный формат команды. Используйте /add_homework.")
            return
        add_homework(message, user_id)
    elif command == "add_schedule":
        if not re.match(r'^/add_schedule\s*$', message.text):
            bot.send_message(message.chat.id, "Неверный формат команды. Используйте /add_schedule.")
            return
        add_schedule(message, user_id)
    elif command == "manage_admins":
        manage_admins(message, user_id)

def add_homework(message, user_id):
    bot.send_message(message.chat.id, "Пожалуйста, введите описание домашнего задания.")
    bot.register_next_step_handler(message, lambda msg: get_next_add_step_for_admin(msg, user_id, "description", "homework"))

def add_schedule(message, user_id):
    bot.send_message(message.chat.id, "Пожалуйста, введите название группы.")
    bot.register_next_step_handler(message, lambda msg: get_next_add_step_for_admin(msg, user_id, "group_name", "schedule"))

def manage_admins(message, user_id):
    admins = get_data('admins')
    if not admins:
        bot.send_message(message.chat.id, "Нет зарегистрированных администраторов.")
        return
    try:
        admin_list = '\n'.join([f"{admin[1]} - {admin[2]}" for admin in admins])
    except IndexError:
        bot.send_message(message.chat.id, "Ошибка: неверный формат данных в tuple admins.")
        return
    bot.send_message(message.chat.id, f"Список администраторов:\n{admin_list}")

def get_next_add_step_for_admin(message, user_id, current_step, table, *args):
    if current_step == "group_name":
        group_name = message.text
        if not group_name.isalpha():
            bot.send_message(message.chat.id, "Неверный формат группы. Используйте только буквы.")
            return
        bot.send_message(message.chat.id, "Пожалуйста, введите название предмета.")
        bot.register_next_step_handler(message, lambda msg: get_next_add_step_for_admin(msg, user_id, "subject", table, group_name))
    elif current_step == "subject":
        subject = message.text
        if not subject.isalpha():
            bot.send_message(message.chat.id, "Неверный формат предмета. Используйте только буквы.")
            return
        bot.send_message(message.chat.id, "Пожалуйста, введите время начала урока в формате HH:MM.")
        bot.register_next_step_handler(message, lambda msg: get_next_add_step_for_admin(msg, user_id, "start_time", table, subject=subject))
    elif current_step == "start_time" or current_step == "description":
        value = message.text
        if not re.match(r'^\d{2}:\d{2}$', value) or current_step == "description":
            bot.send_message(message.chat.id, "Неверный формат времени. Используйте формат HH:MM.")
            return
        insert_data(table, user_id=user_id, *args, **{current_step: value})
        bot.send_message(message.chat.id, f"Данные успешно добавлены в {table.replace('_', ' ')}!")

def handle_support_message(message, user_id):
    support_message = message.text
    if not support_message.isprintable():
        bot.send_message(user_id, "Неверный формат сообщения. Используйте только печатные символы.")
        return
    admins = get_data('admins')

    if admins:
        for admin_row in admins:
            admin_user_id = admin_row[1]
            bot.send_message(admin_user_id, f"Новое сообщение от пользователя {user_id}: {support_message}")
            bot.send_message(user_id, "Ваше сообщение отправлено. Мы скоро свяжемся с вами.")
    else:
        bot.send_message(user_id, "Извините, в настоящее время нет доступных администраторов.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query_handler(call):
    if call.data in ["schedule", "homework", "faq", "survey"]:
        data = get_data(call.data, user_id=call.from_user.id)
        if data is None:
            message = "Нет доступных данных."
        else:
            message = '\n'.join([f"{row[2]}" for row in data])
        bot.send_message(call.message.chat.id, message)
    elif call.data == "support":
        bot.send_message(call.message.chat.id, "Пожалуйста, введите сообщение для техподдержки.")
        bot.register_next_step_handler(call.from_user, lambda msg: handle_support_message(msg, call.from_user.id))
    elif call.data == "faq":
        bot.send_message(call.message.chat.id, "Пожалуйста, введите вопрос, который вы хотите добавить в FAQ.")
        bot.register_next_step_handler(call.from_user, lambda msg: handle_faq_question(msg, call.from_user.id))
    elif call.data == "manage_admins":
        bot.send_message(call.message.chat.id, "Управление администраторами.")
        manage_admins(call.message, call.from_user.id)

def handle_faq_question(message, user_id):
    question = message.text
    if not question.isprintable():
        bot.send_message(user_id, "Неверный формат вопроса. Используйте только печатные символы.")
        return
    bot.send_message(user_id, "Пожалуйста, введите ответ на вопрос.")
    bot.register_next_step_handler(message, lambda msg: add_faq_answer(msg, user_id, question))

def add_faq_answer(message, user_id, question):
    answer = message.text
    if not answer.isprintable():
        bot.send_message(user_id, "Неверный формат ответа. Используйте только печатные символы.")
        return
    insert_data('faq', question=question, answer=answer)
    bot.send_message(user_id, "Вопрос успешно добавлен в FAQ!")

# Добавляет администратора с указанным идентификатором пользователя при старте бота
add_admin('JosephAldridge')

# Планирование функции send_reminder для запроса каждые 5 минут
reminder_thread = threading.Thread(target=send_reminder)
reminder_thread.start()

bot.polling(none_stop=True)