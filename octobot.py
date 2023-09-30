import json
import re
from collections import defaultdict
from datetime import datetime, timedelta

import gspread
import pandas as pd
import telebot

bot = telebot.TeleBot("6274676996:AAGDpTutNUAyvkWeRNx4ampqAyx8CJnvte8")


def is_valid_date(date: str = "01/01/00", divider: str = "/") -> bool:
    """Проверяем, что дата дедлайна валидна:
    - дата не может быть до текущей
    - не может быть позже, чем через год
    - не может быть такой, которой нет в календаре
    - может быть сегодняшним числом
    - пользователь не должен быть обязан вводить конкретный формат даты
    (например, только через точку или только через слеш)"""

    # Получаем текущую дату и время
    now = datetime.now().date()

    # Пробуем преобразовать строку даты в объект datetime
    try:
        deadline_date = datetime.strptime(date, f"%d{divider}%m{divider}%y").date()
    except ValueError:
        return False

    # Проверяем, что дата не может быть до текущей
    if deadline_date < now:
        return False

    # Проверяем, что дата не может быть позже, чем через год
    if deadline_date > now + timedelta(days=365):
        return False

    # Проверяем, что дата существует в календаре
    try:
        datetime(deadline_date.year, deadline_date.month, deadline_date.day)
    except ValueError:
        return False

    return True


def is_valid_url(url: str = "") -> bool:
    """Проверяем, что ссылка рабочая"""
    pattern = re.compile(
        r"^(?:(?:http)s?://)?"  # опциональная схема http:// или https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # домен
        r"localhost|"  # localhost
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...или IP
        r"(?::\d+)?"  # необязательный порт
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    if not pattern.match(url):
        return False

    # Проверка на поддомены без основного домена
    domain_parts = url.split(".")
    if len(domain_parts) == 2 and domain_parts[0].isalpha() and len(domain_parts[0]) == 2:
        return False

    return True


def convert_date(date: str = "01/01/00"):
    """Конвертируем дату из строки в datetime"""
    if date:
        return datetime.strptime(date, "%d/%m/%y")
    else:
        return None


def connect_table(message):
    """Подключаемся к Google-таблице"""
    url = message.text
    sheet_id = "1IMWvdaymgatzkGB2UnSSArA07chGsYfg6c7M7TDCJcI"
    gc = gspread.service_account(filename="credentials.json")
    sheet_data = gc.open("homework05").sheet1
    try:
        with open("tables.json") as json_file:
            tables = json.load(json_file)
        title = len(tables) + 1
        tables[title] = {"url": url, "id": sheet_id}
    except FileNotFoundError:
        tables = {0: {"url": url, "id": sheet_id}}
    with open("tables.json", "w") as json_file:
        json.dump(tables, json_file)
    bot.send_message(message.chat.id, "Таблица подключена!")
    return bool


def access_current_sheet(message):
    """Обращаемся к Google-таблице"""
    with open("tables.json") as json_file:
        tables = json.load(json_file)

    sheet_id = tables[max(tables)]["id"]
    gc = gspread.service_account(filename="credentials.json")
    sh = gc.open_by_key(sheet_id)
    worksheet = sh.sheet1
    return worksheet, tables[max(tables)]["url"]


def check_deadlines(message):
    gc = gspread.service_account(filename="credentials.json")
    sheet_data = gc.open("homework05").sheet1
    df = pd.DataFrame(sheet_data.get_all_values()[1:])
    df.iloc[:, 2:] = df.iloc[:, 2:].applymap(convert_date)  # конвертирует строки из подтаблицы дедлайнов в даты
    result = defaultdict(list)
    for col in df.columns[2:]:
        current_date = datetime.now()
        next_week = current_date + timedelta(days=7)
        deadlines = df.loc[(current_date < df[col]) & (df[col] < next_week)]
        if not deadlines.empty:
            for i in range(len(deadlines)):
                subj = deadlines.iloc[i, 0]
                deadline = deadlines.iloc[i, col]
                result[subj].append(deadline)

    msg = make_deadlines_message(result)
    bot.send_message(message.chat.id, msg)


def make_deadlines_message(deadlines_data):
    result = ""
    for subj, deadlines in deadlines_data.items():
        result += f"Предмет: {subj}, ближайшие дедлайны: {deadlines}\n"
    return result


def choose_action(message):
    """Обрабатываем действия верхнего уровня"""
    if message.text == "Подключить Google-таблицу":
        connect_table(message)
    elif message.text == "Редактировать предметы":
        choose_subject_action(message)
    elif message.text == "Редактировать дедлайн":
        choose_deadline_action(message)
    elif message.text == "Посмотреть дедлайны на этой неделе":
        check_deadlines(message)
    elif message.text == "Назад":
        start(message)
    else:
        bot.send_message(message.chat.id, "Неизвестное действие. Пожалуйста, попробуйте еще раз.")
        choose_action(message)


def choose_subject_action(message):
    """Выбираем действие в разделе Редактировать предметы"""
    start_markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    start_markup.row("Добавить новый предмет")
    start_markup.row("Редактировать предмет")
    start_markup.row("Удалить предмет")
    start_markup.row("Назад")
    info = bot.send_message(message.chat.id, "Выберите действие:", reply_markup=start_markup)

    def handle_next_step(message):
        gc = gspread.service_account(filename="credentials.json")
        sheet_data = gc.open("homework05").sheet1
        if message.text == "Добавить новый предмет":
            info = bot.send_message(message.chat.id, "Введите название нового предмета:")
            bot.register_next_step_handler(info, add_new_subject)
        elif message.text == "Редактировать предмет":
            # Получаем список предметов
            subjects = sheet_data.col_values(1)[1:]

            # Формируем клавиатуру с предметами
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            for subj in subjects:
                markup.add(subj)

            # Отправляем сообщение с запросом на выбор предмета
            msg = bot.send_message(
                message.chat.id, "Выберите предмет, у которого нужно изменить имя:", reply_markup=markup
            )
            bot.register_next_step_handler(msg, update_subject_name)
        elif message.text == "Удалить предмет":
            start_markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            start_markup.row("Удалить предмет")
            start_markup.row("Удалить все")
            start_markup.row("Назад")
            msg = bot.send_message(message.chat.id, "Выберите действие:", reply_markup=start_markup)
            bot.register_next_step_handler(msg, choose_removal_option)
        elif message.text == "Назад":
            start(message)
        else:
            bot.send_message(message.chat.id, "Неизвестное действие. Пожалуйста, попробуйте еще раз.")
            choose_subject_action(message)

    bot.register_next_step_handler(info, handle_next_step)


def choose_deadline_action(message):
    """Выбираем действие в разделе Редактировать дедлайн"""
    start_markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    start_markup.row("Добавить дату дедлайна")
    start_markup.row("Изменить дату дедлайна")
    start_markup.row("Назад")
    action = bot.send_message(message.chat.id, "Выберите действие:", reply_markup=start_markup)
    bot.register_next_step_handler(action, choose_subject)


def choose_subject(message):
    """Выбираем предмет, у которого надо отредактировать дедлайн"""
    gc = gspread.service_account(filename="credentials.json")
    sheet_data = gc.open("homework05").sheet1
    subjects = sheet_data.col_values(1)[1:]
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for subj in subjects:
        markup.add(subj)
    if message.text == "Назад":
        start(message)
    else:
        # Отправляем сообщение с запросом на выбор предмета
        description = "Выберите предмет, у которого надо отредактировать дедлайн:"
        msg = bot.send_message(message.chat.id, description, reply_markup=markup)
        bot.register_next_step_handler(msg, update_subject_deadline)


def update_subject_deadline(message):
    """Обновляем дедлайн"""
    gc = gspread.service_account(filename="credentials.json")
    sheet_data = gc.open("homework05").sheet1
    subject = message.text
    cell = sheet_data.find(subject)
    number = bot.send_message(message.chat.id, "Введите номер работы:")

    def handle_deadline_date(message):
        number = int(message.text)
        col_num = str(number + 2)
        if number not in sheet_data.row_values(1)[3:]:
            sheet_data.update_cell(1, col_num, number)

        row_num = cell.row
        deadline_date_str = bot.send_message(message.chat.id, "Введите дату дедлайна в формате dd/mm/yy:")

        def make_update(deadline_date):
            if not is_valid_date(deadline_date.text):
                bot.send_message(message.chat.id, "Неверный формат даты")
                return
            sheet_data.update_cell(row_num, col_num, deadline_date.text)
            bot.send_message(
                message.chat.id,
                f"Обновлен дедлайн у предмета {subject}. Для работы {number} выставлен дедлайн {deadline_date.text}",
            )

        bot.register_next_step_handler(deadline_date_str, make_update)

    bot.register_next_step_handler(number, handle_deadline_date)


def choose_removal_option(message):
    """Уточняем, точно ли надо удалить все"""
    gc = gspread.service_account(filename="credentials.json")
    sheet_data = gc.open("homework05").sheet1
    if message.text == "Удалить предмет":
        # Получаем список предметов
        subjects = sheet_data.col_values(1)[1:]
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for subj in subjects:
            markup.add(subj)

        # Отправляем сообщение с запросом на выбор предмета
        msg = bot.send_message(message.chat.id, "Выберите предмет, который нужно удалить:", reply_markup=markup)
        bot.register_next_step_handler(msg, delete_subject)
    elif message.text == "Удалить все":
        clear_subject_list(message)
    elif message.text == "Назад":
        start(message)


def check_subject(message):
    gc = gspread.service_account(filename="credentials.json")
    sheet_data = gc.open("homework05").sheet1
    subjects = sheet_data.col_values(1)[1:]
    if message.text in subjects:
        return 1
    else:
        return 0


def add_new_subject(message):
    """Вносим новое название предмета в Google-таблицу"""

    if check_subject(message) == 0:
        gc = gspread.service_account(filename="credentials.json")
        sheet_data = gc.open("homework05").sheet1
        subject = message.text
        sheet_data.append_row([subject])
        info = bot.send_message(message.chat.id, "Введите ссылку на таблицу предмета:")
        bot.register_next_step_handler(info, add_new_subject_url)
    else:
        bot.send_message(message.chat.id, "Данный предмет уже есть в таблице")
        start(message)


def add_new_subject_url(message):
    """Вносим новую ссылку на таблицу предмета в Google-таблицу"""
    gc = gspread.service_account(filename="credentials.json")
    sheet_data = gc.open("homework05").sheet1
    next_row = len(sheet_data.get_all_values())
    url = message.text
    sheet_data.update_cell(next_row, 2, url)  # Обновить ячейку B (столбец 2) новой строки
    bot.send_message(message.chat.id, "Ссылка на таблицу предмета успешно добавлена.")
    start(message)


def update_subject_name(message):
    """Запросить новое имя предмета и обновить его в таблице"""
    gc = gspread.service_account(filename="credentials.json")
    sheet_data = gc.open("homework05").sheet1

    subject = message.text
    cell = sheet_data.find(subject)

    if cell is not None:
        row = cell.row
        msg = bot.send_message(message.chat.id, "Введите новое имя для предмета:")
        bot.register_next_step_handler(msg, update_subject_url, row)
    else:
        bot.send_message(message.chat.id, "Предмет не найден.")


def update_subject_url(message, row):
    gc = gspread.service_account(filename="credentials.json")
    sheet_data = gc.open("homework05").sheet1
    new_subject = message.text
    sheet_data.update_cell(row, 1, new_subject)  # Обновить ячейку A (столбец 1) строки
    msg = bot.send_message(message.chat.id, "Введите ссылку на таблицу для предмета {}: ".format(new_subject))
    bot.register_next_step_handler(msg, add_updated_subject_url, row)


def add_updated_subject_url(message, row):
    gc = gspread.service_account(filename="credentials.json")
    sheet_data = gc.open("homework05").sheet1
    url = message.text
    sheet_data.update_cell(row, 2, url)  # Обновить ячейку B (столбец 2) строки
    bot.send_message(message.chat.id, "Ссылка на таблицу для предмета успешно добавлена.")


def delete_subject(message):
    """Удаляем предмет в Google-таблице"""
    gc = gspread.service_account(filename="credentials.json")
    sheet_data = gc.open("homework05").sheet1
    # Получаем список предметов
    subjects = sheet_data.col_values(1)[1:]

    # Формируем клавиатуру с предметами
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for subj in subjects:
        markup.add(subj)

    subject = message.text
    cell = sheet_data.find(subject)

    if cell is not None:
        row = cell.row
        sheet_data.delete_rows(row)
        bot.send_message(message.chat.id, "Предмет {} успешно удален.".format(subject))
    else:
        bot.send_message(message.chat.id, "Предмет не найден.")


def clear_subject_list(message):
    """Удаляем все из Google-таблицы"""
    delete_all = bot.send_message(
        message.chat.id, "[Вы уверены, что хотите удалить содержимое всей таблицы? Напишите Да/Нет"
    )
    start_markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    start_markup.row("Да")
    start_markup.row("Нет")
    bot.register_next_step_handler(delete_all, del_all)  # Изменено: без вызова функции del_all


def del_all(message):
    start_markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    start_markup.row("Да")
    start_markup.row("Нет")
    if message.text == "Да" or message.text == "да":
        gc = gspread.service_account(filename="credentials.json")
        sheet1 = gc.open("homework05").sheet1
        # Получить список заголовков
        header = sheet1.row_values(1)

        # Удалить все строки, кроме заголовков
        if len(header) > 0:
            sheet1.delete_rows(2, sheet1.row_count)
        bot.send_message(message.chat.id, "Таблица успешно очищена!")
        start(message)

    elif message.text == "Нет" or message.text == "нет":
        bot.send_message(message.chat.id, "Действие отменено")
        start(message)

    else:
        bot.send_message(message.chat.id, "Введена некорректная опция")
        start(message)


@bot.message_handler(commands=["start"])
def start(message):
    gc = gspread.service_account(filename="credentials.json")
    sheet_data = gc.open("homework05").sheet1
    rows = sheet_data.get_all_values()[0]
    content = sheet_data.get_all_values()[1:]
    data_frame = pd.DataFrame(content, columns=rows)
    disciplines = data_frame[["Предмет", "Ссылка"]].values.tolist()
    msg = ""
    for s, l in disciplines:
        msg += f"[{s}]({l})\n"
    bot.send_message(message.chat.id, msg, parse_mode="MarkdownV2", disable_web_page_preview=True)
    start_markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    if not bool(connect_table):
        start_markup.row("Подключить Google-таблицу")
    start_markup.row("Посмотреть дедлайны на этой неделе")
    start_markup.row("Редактировать дедлайн")
    start_markup.row("Редактировать предметы")
    info = bot.send_message(message.chat.id, "Что хотите сделать?", reply_markup=start_markup)
    bot.register_next_step_handler(info, choose_action)


if __name__ == "__main__":
    bot.infinity_polling()
