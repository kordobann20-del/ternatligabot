import telebot
from telebot import types
import random
import time
import json
import os
import sys
import logging

# ==============================================================================
# [1] НАСТРОЙКА СИСТЕМНОГО ЛОГИРОВАНИЯ
# ==============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("FootballBotCore")

# ==============================================================================
# [2] ГЛОБАЛЬНЫЕ НАСТРОЙКИ И ИНИЦИАЛИЗАЦИЯ БОТА
# ==============================================================================

# Уникальный токен вашего Telegram бота
TOKEN = "8886116833:AAEDyyrYKXH3WtY2BBFCOe4lZcaqlYBEaXY"

# Список администраторов (цифровые Telegram ID)
ADMINS = [7908057052, 1674945230]

bot = telebot.TeleBot(TOKEN)

# Конфигурация путей к файлам базы данных JSON
DB_FILES = {
    'cards': 'cards.json',         # База данных всех существующих карточек
    'colls': 'collections.json',   # Коллекции карточек игроков
    'squads': 'squads.json',       # Текущие футбольные составы пользователей
    'users': 'users_data.json',     # Профили пользователей, балансы, статистика
    'bans': 'bans.json',           # Черный список (заблокированные ID и юзернеймы)
    'promos': 'promos.json'        # Доступные промокоды и их параметры
}

# ==============================================================================
# [3] ИГРОВЫЕ ПАРАМЕТРЫ И КОНФИГУРАЦИЯ БАЛАНСА
# ==============================================================================

# Характеристики редкостей карт, шансы выпадения и сила атаки
RARITY_STATS = {
    1: {"chance": 35, "score": 1000, "atk": 100, "label": "Обычная"},
    2: {"chance": 30, "score": 3000, "atk": 450, "label": "Необычная"},
    3: {"chance": 20, "score": 7500, "atk": 1000, "label": "Редкая"},
    4: {"chance": 10, "score": 15000, "atk": 2500, "label": "Эпическая"},
    5: {"chance": 5, "score": 30000, "atk": 5000, "label": "Легендарная"}
}

# Декодирование футбольных позиций на русский язык
POSITIONS_RU = {
    "ГК": "Вратарь", 
    "ЛЗ": "Левый Защитник", 
    "ПЗ": "Правый Защитник",
    "ЦП": "Центральный Полузащитник", 
    "ЛВ": "Левый Вингер", 
    "ПВ": "Правый Вингер", 
    "КФ": "Нападающий"
}

# Конфигурация слотов игрового состава (7 позиций)
SQUAD_SLOTS = {
    0: {"label": "🧤 ГК (Вратарь)", "code": "ГК"},
    1: {"label": "🛡 ЛЗ (Защитник)", "code": "ЛЗ"},
    2: {"label": "🛡 ПЗ (Защитник)", "code": "ПЗ"},
    3: {"label": "👟 ЦП (Полузащитник)", "code": "ЦП"},
    4: {"label": "⚡️ ЛВ (Вингер)", "code": "ЛВ"},
    5: {"label": "⚡️ ПВ (Вингер)", "code": "ПВ"},
    6: {"label": "🎯 КФ (Нападающий)", "code": "КФ"}
}

# Предустановленный список футбольных клубов для лора или кастомизации карт
FOOTBALL_CLUBS_POOL = [
    "Интер Милан",
    "Арсенал Лондон",
    "Барселона",
    "Наполи",
    "Реал Мадрид",
    "Манчестер Сити",
    "Бавария Мюнхен"
]

# Глобальные словари для отслеживания времени перезарядки действий (Cooldowns)
roll_cooldowns = {}
pvp_cooldowns = {}

# Глобальные списки и словари для системы онлайн ПВП матчей
pvp_search_queue = [] # Игроки, которые ищут случайный онлайн матч
pvp_challenges = {}   # Активные прямые вызовы {target_username: challenger_id}

# ==============================================================================
# [4] УПРАВЛЕНИЕ ДАННЫМИ (JSON STORAGE ENGINE С АВТО-БЭКАПОМ)
# ==============================================================================

def initialize_database_files():
    """Проверяет наличие всех файлов БД и создает пустые структуры, если файлы отсутствуют."""
    logger.info("Проверка целостности файлов базы данных...")
    for key, file_name in DB_FILES.items():
        if not os.path.exists(file_name):
            default_structure = [] if key in ['cards', 'bans'] else {}
            try:
                with open(file_name, 'w', encoding='utf-8') as f:
                    json.dump(default_structure, f, ensure_ascii=False, indent=4)
                logger.info(f"Создан новый пустой файл базы данных: {file_name}")
            except IOError as e:
                logger.critical(f"Не удалось инициализировать файл {file_name}: {e}")

# Запуск первичной инициализации при импорте модуля
initialize_database_files()


def load_data(key):
    """
    Безопасно загружает данные из JSON файла по ключу таблицы.
    В случае повреждения файла пытается восстановить данные из резервной копии .bak.
    """
    file_path = DB_FILES.get(key)
    if not file_path:
        logger.error(f"Попытка доступа к несуществующему ключу базы данных: {key}")
        return [] if key in ['cards', 'bans'] else {}

    # Если основного файла нет, пробуем восстановить из бэкапа
    if not os.path.exists(file_path):
        backup_path = file_path + ".bak"
        if os.path.exists(backup_path):
            logger.warning(f"Основной файл {file_path} отсутствует! Восстановление из {backup_path}")
            try:
                with open(backup_path, 'r', encoding='utf-8') as b_file:
                    backup_content = b_file.read()
                with open(file_path, 'w', encoding='utf-8') as f_file:
                    f_file.write(backup_content)
            except IOError as e:
                logger.error(f"Не удалось восстановить файл из бэкапа: {e}")
        else:
            default_structure = [] if key in ['cards', 'bans'] else {}
            return default_structure

    # Чтение данных из основного файла
    with open(file_path, 'r', encoding='utf-8') as file_in:
        try:
            content = file_in.read()
            if not content.strip():
                return [] if key in ['cards', 'bans'] else {}
            return json.loads(content)
        except json.JSONDecodeError as json_error:
            logger.error(f"Файл {file_path} поврежден или имеет неверный формат JSON: {json_error}")
            
            # Попытка аварийного чтения из .bak файла
            backup_path = file_path + ".bak"
            if os.path.exists(backup_path):
                logger.info(f"Попытка аварийного чтения резервной копии для {key}...")
                try:
                    with open(backup_path, 'r', encoding='utf-8') as backup_in:
                        return json.loads(backup_in.read())
                except Exception as backup_error:
                    logger.critical(f"Резервная копия {backup_path} также повреждена: {backup_error}")
            
            return [] if key in ['cards', 'bans'] else {}
        except Exception as general_error:
            logger.error(f"Непредвиденная ошибка при чтении базы {key}: {general_error}")
            return [] if key in ['cards', 'bans'] else {}


def save_data(data_object, key):
    """
    Сохраняет переданный объект данных в JSON файл.
    Перед записью создает резервную копию предыдущего стабильного состояния (.bak).
    """
    file_path = DB_FILES.get(key)
    if not file_path:
        logger.error(f"Попытка сохранения в несуществующую таблицу: {key}")
        return False

    # Создание резервной копии перед перезаписью
    if os.path.exists(file_path):
        try:
            backup_path = file_path + ".bak"
            if os.path.exists(backup_path):
                os.remove(backup_path)
            os.rename(file_path, backup_path)
        except Exception as backup_exception:
            logger.warning(f"Не удалось создать резервную копию для {file_path}: {backup_exception}")

    # Запись новых данных в файл
    try:
        with open(file_path, 'w', encoding='utf-8') as file_out:
            json.dump(data_object, file_out, ensure_ascii=False, indent=4)
        return True
    except IOError as io_error:
        logger.critical(f"Ошибка ввода-вывода при сохранении таблицы {key} в файл {file_path}: {io_error}")
        # Попытка откатить файл из бэкапа в случае критического сбоя записи
        backup_path = file_path + ".bak"
        if os.path.exists(backup_path):
            try:
                os.rename(backup_path, file_path)
                logger.info(f"Файл {file_path} успешно восстановлен из резервной копии после ошибки записи.")
            except Exception as rollback_err:
                logger.critical(f"Не удалось откатить изменения после сбоя записи: {rollback_err}")
        return False
    except Exception as general_error:
        logger.critical(f"Критическая ошибка сохранения данных {key}: {general_error}")
        return False

# ==============================================================================
# [5] СИСТЕМНЫЕ ПРОВЕРКИ, БЕЗОПАСНОСТЬ И ВЫЧИСЛЕНИЯ
# ==============================================================================

def check_admin_permission(user_obj):
    """
    Проверяет, имеет ли пользователь административные права.
    Сравнивает Telegram ID пользователя со списком ADMINS.
    """
    if user_obj is None:
        return False
    return user_obj.id in ADMINS


def check_ban_status(user_obj):
    """
    Проверяет, заблокирован ли пользователь в боте.
    Поиск идет как по цифровому Telegram ID, так и по текстовому Username.
    """
    if user_obj is None:
        return False
        
    ban_list = load_data('bans')
    user_id_string = str(user_obj.id)
    user_name_string = user_obj.username.lower() if user_obj.username else "no_username_set"
    
    if user_id_string in ban_list:
        return True
    if user_name_string in ban_list:
        return True
        
    return False


def calculate_total_power(user_id):
    """
    Рассчитывает суммарную силу атаки (мощность) текущего футбольного состава игрока.
    Суммирует параметры атаки из RARITY_STATS на основе звездности карт в слотах.
    """
    squad_data = load_data('squads')
    my_squad = squad_data.get(str(user_id), [None] * 7)
    
    power_sum = 0
    for card_item in my_squad:
        if card_item is not None and isinstance(card_item, dict):
            stars = card_item.get('stars', 1)
            # Защита от выхода за границы конфигурации звездности
            if stars not in RARITY_STATS:
                stars = 1
            power_sum += RARITY_STATS[stars]['atk']
            
    return power_sum


def log_action(user_id, action_name):
    """Фиксирует действия пользователей в консоли для мониторинга активности."""
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"ИГРОК: {user_id} | ДЕЙСТВИЕ: {action_name} | ВРЕМЯ: {current_time}")

# ==============================================================================
# [6] ИНТЕРФЕЙСНЫЙ ДВИЖОК (ГЕНЕРАЦИЯ КЛАВИАТУР СИСТЕМЫ)
# ==============================================================================

def create_main_menu(user_id):
    """
    Формирует главное меню управления для обычных пользователей.
    Если пользователь является администратором, в меню автоматически добавляется кнопка Админ-панели.
    """
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    btn_roll = types.KeyboardButton("🎰 Крутить карту")
    btn_collection = types.KeyboardButton("🗂 Коллекция")
    btn_squad = types.KeyboardButton("📋 Состав")
    btn_profile = types.KeyboardButton("👤 Профиль")
    btn_top = types.KeyboardButton("🏆 Топ очков")
    btn_pvp = types.KeyboardButton("🏟 ПВП Арена")
    btn_promo = types.KeyboardButton("🎟 Промокод")
    btn_referrals = types.KeyboardButton("👥 Рефералы")
    
    # Добавление кнопок рядами для красивого визуального отображения
    markup.add(btn_roll, btn_collection)
    markup.add(btn_squad, btn_profile)
    markup.add(btn_top, btn_pvp)
    markup.add(btn_promo, btn_referrals)
    
    # Внутренний контейнер для быстрой проверки прав администратора без обращения к API
    class LocalUserObject:
        def __init__(self, uid):
            self.id = uid

    if check_admin_permission(LocalUserObject(user_id)):
        btn_admin = types.KeyboardButton("🛠 Админ-панель")
        markup.add(btn_admin)
        
    return markup


def create_admin_menu():
    """Создает специализированное меню управления для администраторов бота."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    btn_add_card = types.KeyboardButton("➕ Добавить карту")
    btn_edit_card = types.KeyboardButton("📝 Изменить карту")
    btn_del_card = types.KeyboardButton("🗑 Удалить карту")
    
    btn_add_promo = types.KeyboardButton("🎟 +Промокод")
    btn_del_promo = types.KeyboardButton("🗑 Удалить промокод")
    
    btn_ban = types.KeyboardButton("🚫 Забанить")
    btn_unban = types.KeyboardButton("✅ Разбанить")
    
    btn_reset = types.KeyboardButton("🧨 Обнулить бота")
    btn_back = types.KeyboardButton("🏠 Назад в меню")
    
    markup.add(btn_add_card, btn_edit_card, btn_del_card)
    markup.add(btn_add_promo, btn_del_promo)
    markup.add(btn_ban, btn_unban)
    markup.add(btn_reset, btn_back)
    
    return markup


def create_cancel_menu():
    """Создает универсальную кнопку отмены для выхода из интерактивных диалогов ввода."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("❌ Отмена"))
    return markup

# ==============================================================================
# [7] ОБРАБОТЧИКИ СИСТЕМНЫХ КОМАНД И РЕФЕРАЛЬНОЙ СИСТЕМЫ
# ==============================================================================

@bot.message_handler(commands=['start'])
def start_message_handler(message):
    """
    Обработчик команды /start. Реализует регистрацию пользователей в JSON базе данных,
    проверку банов и полноценную глубокую реферальную систему с начислением бонусов пригласителю.
    """
    if check_ban_status(message.from_user):
        bot.send_message(message.chat.id, "🚫 Вы заблокированы. Доступ к функциям симулятора закрыт.")
        return

    users_database = load_data('users')
    user_id_key = str(message.from_user.id)
    log_action(user_id_key, f"START_COMMAND_TRIGGERED (Text: {message.text})")

    # Выделение реферального токена (ID пригласителя) из текста команды /start
    inviter_id = None
    command_parts = message.text.split()
    if len(command_parts) > 1:
        inviter_id = command_parts[1].strip()

    # Если пользователь новый и его нет в базе данных - регистрируем его profile
    if user_id_key not in users_database:
        user_display_name = f"@{message.from_user.username}" if message.from_user.username else f"id_{user_id_key}"
        
        users_database[user_id_key] = {
            "nick": message.from_user.first_name if message.from_user.first_name else "Футболист",
            "username": user_display_name,
            "score": 0,
            "free_rolls": 0,
            "bonus_luck": 1.0,
            "refs": 0,
            "used_promos": []
        }
        logger.info(f"Зарегистрирован новый пользователь: ID {user_id_key}, Имя: {message.from_user.first_name}")
        
        # Начисление наград пригласителю (рефереру), если условия соблюдены
        if inviter_id and inviter_id in users_database and inviter_id != user_id_key:
            users_database[inviter_id]["score"] += 5000
            users_database[inviter_id]["free_rolls"] = users_database[inviter_id].get("free_rolls", 0) + 3
            users_database[inviter_id]["refs"] = users_database[inviter_id].get("refs", 0) + 1
            
            try:
                msg_to_inviter = (
                    "👥 **НОВЫЙ ИГРОК ПОДДКЛЮЧЕН!**\n\n"
                    "По вашей реферальной ссылке зарегистрировался новый менеджер.\n"
                    "🎁 **Вам начислено вознаграждение:**\n"
                    "— 💰 **+5,000 очков на баланс**\n"
                    "— 🎫 **+3 бесплатных прокрута карточек**"
                )
                bot.send_message(int(inviter_id), msg_to_inviter, parse_mode="Markdown")
                logger.info(f"Реферальный бонус успешно выдан пользователю {inviter_id}")
            except Exception as referral_error:
                logger.error(f"Не удалось отправить пуш-уведомление рефереру {inviter_id}: {referral_error}")

        # Сохраняем обновленную базу данных пользователей
        save_data(users_database, 'users')
    else:
        # Если пользователь уже зарегистрирован, но перешел по реферальной ссылке, игнорируем начисление
        if inviter_id:
            logger.info(f"Игрок {user_id_key} уже зарегистрирован, реферальная ссылка проигнорирована.")

    # Приветственное сообщение
    welcome_text = (
        "⚽️ **Приветствую, {}!**\n\n"
        "Вы попали в продвинутый симулятор футбольных карточек.\n"
        "Собирайте уникальные составы, прокачивайте команду, активируйте секретные промокоды "
        "и побеждайте других менеджеров на ПВП Арене!\n\n"
        "Используйте встроенное графическое меню для управления своей футбольной империей."
    ).format(message.from_user.first_name)
    
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        reply_markup=create_main_menu(message.from_user.id), 
        parse_mode="Markdown"
    )


@bot.message_handler(func=lambda m: m.text == "👥 Рефералы")
def referral_stats_handler(message):
    """Генерирует индивидуальную реферальную ссылку и выводит статистику приглашенных друзей."""
    if check_ban_status(message.from_user):
        return
        
    user_id = message.from_user.id
    users_db = load_data('users')
    
    try:
        bot_info = bot.get_me()
        bot_username = bot_info.username
    except Exception as api_err:
        logger.error(f"Ошибка при запросе информации о боте через get_me: {api_err}")
        bot_username = "FootballCardSimulatorBot"  # Дефолтный фоллбэк резервного имени
    
    invite_link = f"https://t.me/{bot_username}?start={user_id}"
    user_profile_data = users_db.get(str(user_id), {})
    ref_count = user_profile_data.get("refs", 0)
    
    referral_text = (
        "👥 **РЕФЕРАЛЬНАЯ ПРОГРАММА**\n\n"
        "Развивайте футбольное сообщество бота и получайте ценные призы!\n\n"
        "🎁 **Награда за каждого приглашенного друга:**\n"
        "— 💰 **5,000 очков на счет**\n"
        "— 🎫 **3 бонусных прокрута карт**\n\n"
        "📊 Ваша личная статистика:\n"
        "— Всего приглашено игроков: **{}**\n\n"
        "🔗 Ваша уникальная ссылка для приглашений (нажмите для копирования):\n"
        "`{}`"
    ).format(ref_count, invite_link)
    
    bot.send_message(message.chat.id, referral_text, parse_mode="Markdown")

# ==============================================================================
# КОНЕЦ ПЕРВОЙ ЧАСТИ. ОЖИДАЙТЕ ВТОРОЙ И ТРЕТЬЕЙ ЧАСТИ ДЛЯ ПОЛНОЙ СБОРКИ БОТА.
# ==============================================================================

# ==============================================================================
# [8] ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ И ИНФОРМАЦИЯ О БАЛАНСЕ
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile_handler(message):
    """Выводит подробную статистику пользователя: баланс, сила состава, кулдауны."""
    if check_ban_status(message.from_user):
        return

    user_id = str(message.from_user.id)
    users_db = load_data('users')
    colls_db = load_data('colls')
    
    # Если пользователя нет в базе (не нажимал /start)
    if user_id not in users_db:
        bot.send_message(message.chat.id, "⚠️ Вы не зарегистрированы. Нажмите /start")
        return

    profile_data = users_db[user_id]
    user_score = profile_data.get('score', 0)
    free_rolls = profile_data.get('free_rolls', 0)
    user_refs = profile_data.get('refs', 0)
    
    # Подсчет статистики коллекции
    user_collection = colls_db.get(user_id, [])
    collection_count = len(user_collection)
    
    # Подсчет силы боевого состава
    total_power = calculate_total_power(user_id)
    
    # Расчет времени до следующего бесплатного прокрута (кулдаун 1 час)
    cooldown_text = "Готов прямо сейчас! ✅"
    last_roll_time = roll_cooldowns.get(user_id, 0)
    current_time = time.time()
    time_passed = current_time - last_roll_time
    
    if time_passed < 3600 and free_rolls <= 0:
        remaining_seconds = 3600 - int(time_passed)
        minutes, seconds = divmod(remaining_seconds, 60)
        cooldown_text = f"Осталось {minutes} мин. {seconds} сек. ⏳"
    elif free_rolls > 0:
        cooldown_text = "Доступны бесплатные билеты! 🎫"

    profile_text = (
        f"👤 **ПРОФИЛЬ МЕНЕДЖЕРА | {profile_data.get('nick', 'Игрок')}**\n\n"
        f"💰 **Ваш баланс очков:** {user_score:,}\n"
        f"⚡️ **Сила текущего состава:** {total_power} ATK\n"
        f"🗂 **Карт в коллекции:** {collection_count} шт.\n"
        f"🎫 **Бесплатных прокрутов:** {free_rolls}\n"
        f"👥 **Приглашенных друзей:** {user_refs}\n\n"
        f"🎰 **Статус рулетки:** {cooldown_text}"
    )

    bot.send_message(message.chat.id, profile_text, parse_mode="Markdown")

# ==============================================================================
# [9] СИСТЕМА ГАЧИ (ПРОКРУТ КАРТОЧЕК С КУЛДАУНАМИ)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🎰 Крутить карту")
def roll_card_handler(message):
    """
    Система случайного выпадения карт (Гача).
    Учитывает кулдаун в 1 час (3600 секунд) и наличие подарочных бесплатных прокрутов.
    """
    if check_ban_status(message.from_user):
        return

    user_id = str(message.from_user.id)
    users_db = load_data('users')
    
    if user_id not in users_db:
        bot.send_message(message.chat.id, "⚠️ Ошибка профиля. Нажмите /start")
        return

    profile_data = users_db[user_id]
    free_rolls = profile_data.get('free_rolls', 0)
    current_time = time.time()
    last_roll = roll_cooldowns.get(user_id, 0)

    # Проверка системы кулдауна
    if not check_admin_permission(message.from_user):
        if free_rolls <= 0 and (current_time - last_roll) < 3600:
            remaining = 3600 - int(current_time - last_roll)
            mins, secs = divmod(remaining, 60)
            bot.send_message(
                message.chat.id, 
                f"⏳ Вы слишком устали! Следующий прокрут будет доступен через **{mins} мин {secs} сек**.\n"
                f"Приглашайте друзей, чтобы получить билеты без кулдауна!", 
                parse_mode="Markdown"
            )
            return

    # Загрузка базы существующих карт сервера
    cards_db = load_data('cards')
    if not cards_db:
        bot.send_message(message.chat.id, "😔 Извините, администрация еще не добавила карты в игру.")
        return

    # Выбор случайной редкости на основе заранее заданных шансов
    random_chance = random.uniform(0, 100)
    cumulative = 0
    selected_stars = 1
    
    # Сортировка от обычных к легендарным для корректного распределения вероятностей
    for stars, data in sorted(RARITY_STATS.items()):
        cumulative += data['chance']
        if random_chance <= cumulative:
            selected_stars = stars
            break

    # Фильтрация пула карт по выпавшей редкости
    available_pool = [card for card in cards_db if card.get('stars', 1) == selected_stars]
    
    # Если в выпавшей редкости нет карт, берем случайную карту из всей базы
    if not available_pool:
        dropped_card = random.choice(cards_db)
        selected_stars = dropped_card.get('stars', 1)
    else:
        dropped_card = random.choice(available_pool)

    # Списание прокрута и обновление кулдауна
    if free_rolls > 0:
        users_db[user_id]['free_rolls'] -= 1
        save_data(users_db, 'users')
    else:
        roll_cooldowns[user_id] = current_time

    # Сохранение выпавшей карты в инвентарь пользователя (коллекцию)
    colls_db = load_data('colls')
    if user_id not in colls_db:
        colls_db[user_id] = []
    
    # Генерируем уникальный инвентарный ID для конкретной выбитой карточки
    dropped_card_copy = dropped_card.copy()
    dropped_card_copy['inv_id'] = f"{user_id}_{int(time.time()*1000)}_{random.randint(100,999)}"
    colls_db[user_id].append(dropped_card_copy)
    save_data(colls_db, 'colls')

    # Начисление бонусных очков за выбитую карточку
    earned_score = RARITY_STATS[selected_stars]['score']
    users_db[user_id]['score'] += earned_score
    save_data(users_db, 'users')

    # Формирование визуального сообщения о выпадении
    rarity_label = RARITY_STATS[selected_stars]['label']
    star_visual = "⭐" * selected_stars
    
    drop_text = (
        f"🎰 **ВЫПАДЕНИЕ ИЗ НАБОРА!**\n\n"
        f"[{rarity_label}] {dropped_card.get('name', 'Неизвестный')}\n"
        f"Рейтинг: {star_visual}\n"
        f"Позиция: {POSITIONS_RU.get(dropped_card.get('pos', 'ЦП'), dropped_card.get('pos', 'ЦП'))}\n"
        f"Клуб: {dropped_card.get('club', 'Неизвестный')}\n"
        f"Сила Атаки: {RARITY_STATS[selected_stars]['atk']} ATK\n\n"
        f"💰 Бонус очков за получение: **+{earned_score}**"
    )

    # Если к карточке прикреплено фото (file_id) — отправляем карточку с изображением
    if dropped_card.get('photo_id'):
        try:
            bot.send_photo(message.chat.id, dropped_card['photo_id'], caption=drop_text, parse_mode="Markdown")
        except Exception as photo_err:
            logger.error(f"Ошибка отправки фото карты {dropped_card.get('name')}: {photo_err}")
            bot.send_message(message.chat.id, drop_text + "\n*(Изображение карты временно недоступно)*", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, drop_text, parse_mode="Markdown")

    log_action(user_id, f"ROLLED_CARD (Card: {dropped_card.get('name')}, Rarity: {selected_stars})")

# ==============================================================================
# [10] КОЛЛЕКЦИЯ ИГРОКА И ПАГИНАЦИЯ ИНТЕРФЕЙСА
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🗂 Коллекция")
def view_collection_handler(message):
    """Отображает коллекцию карточек пользователя с постраничной навигацией."""
    if check_ban_status(message.from_user):
        return

    user_id = str(message.from_user.id)
    colls_db = load_data('colls')
    user_col = colls_db.get(user_id, [])

    if not user_col:
        bot.send_message(message.chat.id, "📭 Ваша коллекция пока пуста. Попробуйте покрутить карты!")
        return

    # Запускаем функцию рендера 0-й страницы
    send_collection_page(message.chat.id, user_col, page=0)


def send_collection_page(chat_id, collection_list, page=0, message_id=None):
    """
    Вспомогательная функция для генерации текстового списка коллекции 
    и кнопок постраничной навигации (Inline Keyboard).
    """
    items_per_page = 10
    total_pages = (len(collection_list) + items_per_page - 1) // items_per_page
    
    # Защита от выхода за границы страниц
    if page < 0: page = 0
    if page >= total_pages: page = total_pages - 1

    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    current_items = collection_list[start_idx:end_idx]

    text = f"🗂 **Ваша Коллекция (Страница {page + 1} из {total_pages})**\n\n"
    
    # Формируем список карт
    for idx, card in enumerate(current_items, start=start_idx + 1):
        stars = card.get('stars', 1)
        star_str = "⭐" * stars
        pos = card.get('pos', 'ЦП')
        name = card.get('name', 'Игрок')
        text += f"{idx}. [{pos}] {name} {star_str}\n"

    # Создаем Inline-клавиатуру для листания
    markup = types.InlineKeyboardMarkup()
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton("⬅️ Пред.", callback_data=f"col_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(types.InlineKeyboardButton("След. ➡️", callback_data=f"col_page_{page+1}"))
        
    if nav_buttons:
        markup.add(*nav_buttons)

    # Если вызвано из коллбэка — редактируем старое сообщение, иначе шлем новое
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass # Игнорируем ошибки (например, если текст не изменился)
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith('col_page_'))
def collection_pagination_callback(call):
    """Обработчик нажатий на Inline-кнопки листания коллекции."""
    user_id = str(call.from_user.id)
    colls_db = load_data('colls')
    user_col = colls_db.get(user_id, [])
    
    if not user_col:
        bot.answer_callback_query(call.id, "Ваша коллекция пуста.")
        return
        
    try:
        target_page = int(call.data.split('_')[2])
        send_collection_page(call.message.chat.id, user_col, target_page, call.message.message_id)
        bot.answer_callback_query(call.id)
    except Exception as err:
        logger.error(f"Ошибка пагинации коллекции: {err}")
        bot.answer_callback_query(call.id, "Произошла ошибка при перелистывании.")

# ==============================================================================
# [11] УПРАВЛЕНИЕ ФУТБОЛЬНЫМ СОСТАВОМ (SQUAD)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "📋 Состав")
def squad_menu_handler(message):
    """Выводит текущий футбольный состав менеджера на поле."""
    if check_ban_status(message.from_user):
        return

    user_id = str(message.from_user.id)
    squads_db = load_data('squads')
    
    # Если состава еще нет — создаем пустой из 7 слотов (индексы от 0 до 6)
    if user_id not in squads_db:
        squads_db[user_id] = [None] * 7
        save_data(squads_db, 'squads')
        
    my_squad = squads_db[user_id]
    total_atk = calculate_total_power(user_id)
    
    squad_text = f"📋 **ВАШ СТАРТОВЫЙ СОСТАВ**\n⚡️ Общая сила атаки: **{total_atk}**\n\n"
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # Формируем отображение каждого из 7 слотов (позиций)
    for slot_idx, slot_info in SQUAD_SLOTS.items():
        card_in_slot = my_squad[slot_idx]
        
        if card_in_slot is None:
            squad_text += f"{slot_info['label']}: 🈳 [Пусто]\n"
            btn_text = f"Установить {slot_info['code']}"
        else:
            stars_str = "⭐" * card_in_slot.get('stars', 1)
            name = card_in_slot.get('name', 'Неизвестный')
            squad_text += f"{slot_info['label']}: {name} {stars_str}\n"
            btn_text = f"Заменить {slot_info['code']} ({name})"
            
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"eq_slot_{slot_idx}"))
        
    squad_text += "\nВыберите позицию ниже, чтобы установить или заменить игрока."
    
    bot.send_message(message.chat.id, squad_text, reply_markup=markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith('eq_slot_'))
def select_card_for_slot_callback(call):
    """Вызывается при нажатии на слот в меню состава. Предлагает выбрать карту подходящей позиции."""
    user_id = str(call.from_user.id)
    slot_idx = int(call.data.split('_')[2])
    
    target_pos_code = SQUAD_SLOTS[slot_idx]['code']
    
    colls_db = load_data('colls')
    user_col = colls_db.get(user_id, [])
    
    # Ищем в коллекции карточки, которые подходят по позиции
    suitable_cards = [c for c in user_col if c.get('pos') == target_pos_code]
    
    if not suitable_cards:
        bot.answer_callback_query(call.id, f"У вас нет карточек на позицию {target_pos_code} в коллекции!", show_alert=True)
        return
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # Лимит показа для предотвращения переполнения Telegram API (макс. 20 подходящих карт)
    for card in suitable_cards[:20]:
        stars_str = "⭐" * card.get('stars', 1)
        btn_label = f"{card.get('name')} {stars_str}"
        # Передаем инвентарный ID карты и целевой слот в callback_data
        markup.add(types.InlineKeyboardButton(btn_label, callback_data=f"setcard_{slot_idx}_{card['inv_id']}"))
        
    bot.edit_message_text(
        f"⬇️ Выберите игрока для установки на позицию **{target_pos_code}**:", 
        call.message.chat.id, 
        call.message.message_id, 
        reply_markup=markup, 
        parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('setcard_'))
def apply_card_to_slot_callback(call):
    """Применяет выбранную карточку к конкретному слоту в составе и сохраняет в БД."""
    data_parts = call.data.split('_')
    slot_idx = int(data_parts[1])
    inv_id = data_parts[2] # Содержит user_id_timestamp_random
    user_id = str(call.from_user.id)
    
    colls_db = load_data('colls')
    user_col = colls_db.get(user_id, [])
    
    # Ищем саму карточку по уникальному инвентарному номеру
    target_card = None
    for card in user_col:
        if card.get('inv_id') == inv_id:
            target_card = card
            break
            
    if not target_card:
        bot.answer_callback_query(call.id, "Карточка не найдена в инвентаре (возможно, была удалена).", show_alert=True)
        return
        
    squads_db = load_data('squads')
    if user_id not in squads_db:
        squads_db[user_id] = [None] * 7
        
    squads_db[user_id][slot_idx] = target_card
    save_data(squads_db, 'squads')
    
    bot.answer_callback_query(call.id, f"{target_card.get('name')} успешно назначен в состав!")
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    # После установки возвращаем пользователя в меню состава для удобства
    class MockMessage:
        def __init__(self, from_user, chat):
            self.from_user = from_user
            self.chat = chat
            
    mock_msg = MockMessage(call.from_user, call.message.chat)
    squad_menu_handler(mock_msg)

# ==============================================================================
# [12] СИСТЕМА ТОПА И ПРОМОКОДОВ
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🏆 Топ очков")
def leaderboard_handler(message):
    """Генерирует и выводит таблицу лидеров на основе набранных очков (score)."""
    if check_ban_status(message.from_user):
        return

    users_db = load_data('users')
    
    if not users_db:
        bot.send_message(message.chat.id, "Рейтинг пуст.")
        return

    # Преобразуем словарь в список и сортируем по ключу 'score' в порядке убывания
    sorted_users = sorted(users_db.items(), key=lambda item: item[1].get('score', 0), reverse=True)
    
    top_text = "🏆 **РЕЙТИНГ МЕНЕДЖЕРОВ (ТОП-10)**\n\n"
    
    for idx, (uid, udata) in enumerate(sorted_users[:10], start=1):
        nick = udata.get('nick', 'Игрок')
        score = udata.get('score', 0)
        
        # Эмодзи для топ-3
        medal = "🏅"
        if idx == 1: medal = "🥇"
        elif idx == 2: medal = "🥈"
        elif idx == 3: medal = "🥉"
            
        top_text += f"{medal} **{idx}.** {nick} — {score:,} очков\n"

    bot.send_message(message.chat.id, top_text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "🎟 Промокод")
def promo_init_handler(message):
    """Активирует режим ввода промокода (ожидание следующего сообщения)."""
    if check_ban_status(message.from_user):
        return

    msg = bot.send_message(
        message.chat.id, 
        "⌨️ Введите промокод (соблюдайте регистр):", 
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, process_promo_input)


def process_promo_input(message):
    """Обрабатывает введенный пользователем текст промокода и начисляет награду."""
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "Ввод отменен.", reply_markup=create_main_menu(message.from_user.id))
        return

    user_id = str(message.from_user.id)
    promo_code = message.text.strip()
    
    promos_db = load_data('promos')
    users_db = load_data('users')
    
    if promo_code not in promos_db:
        bot.send_message(
            message.chat.id, 
            "❌ Неверный или несуществующий промокод.", 
            reply_markup=create_main_menu(message.from_user.id)
        )
        return
        
    promo_data = promos_db[promo_code]
    
    # Проверка на исчерпание лимита активаций
    if promo_data.get('activations_left', 0) <= 0:
        bot.send_message(
            message.chat.id, 
            "❌ Этот промокод больше не действителен (закончились активации).", 
            reply_markup=create_main_menu(message.from_user.id)
        )
        return
        
    # Проверка, использовал ли уже пользователь этот промокод
    user_profile = users_db.get(user_id, {})
    used_promos = user_profile.get('used_promos', [])
    
    if promo_code in used_promos:
        bot.send_message(
            message.chat.id, 
            "⚠️ Вы уже активировали этот промокод ранее.", 
            reply_markup=create_main_menu(message.from_user.id)
        )
        return
        
    # Начисление наград
    bonus_score = promo_data.get('bonus_score', 0)
    bonus_rolls = promo_data.get('bonus_rolls', 0)
    
    users_db[user_id]['score'] = user_profile.get('score', 0) + bonus_score
    users_db[user_id]['free_rolls'] = user_profile.get('free_rolls', 0) + bonus_rolls
    
    if 'used_promos' not in users_db[user_id]:
        users_db[user_id]['used_promos'] = []
    users_db[user_id]['used_promos'].append(promo_code)
    
    # Уменьшаем лимит активаций глобального промокода
    promos_db[promo_code]['activations_left'] -= 1
    
    save_data(users_db, 'users')
    save_data(promos_db, 'promos')
    
    success_text = (
        f"✅ **ПРОМОКОД АКТИВИРОВАН!**\n\n"
        f"Вы получили:\n"
        f"💰 Очков: +{bonus_score}\n"
        f"🎫 Прокрутов: +{bonus_rolls}"
    )
    
    bot.send_message(message.chat.id, success_text, parse_mode="Markdown", reply_markup=create_main_menu(message.from_user.id))
    log_action(user_id, f"ACTIVATED_PROMO (Code: {promo_code})")

# ==============================================================================
# [13] СИСТЕМА ОНЛАЙН ПВП-АРЕНЫ (МАТЧИ С РЕАЛЬНЫМИ ЛЮДЬМИ)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🏟 ПВП Арена")
def pvp_arena_handler(message):
    """Меню выбора режима PvP: поиск онлайн-соперника или вызов по юзернейму."""
    # Удаляем предыдущие сообщения арены, если они были, чтобы не засорять чат
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔍 Найти случайного игрока", callback_data="pvp_find_random"),
        types.InlineKeyboardButton("⚔️ Вызвать игрока (по @username)", callback_data="pvp_challenge_user")
    )
    bot.send_message(message.chat.id, "🏟 **ПВП АРЕНА**\nВыберите режим матча:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "pvp_find_random")
def pvp_random_search(call):
    """Логика поиска случайного игрока в очереди."""
    user_id = call.from_user.id
    if user_id in pvp_search_queue:
        bot.answer_callback_query(call.id, "Вы уже ищете соперника!")
        return
    
    pvp_search_queue.append(user_id)
    bot.answer_callback_query(call.id, "Ищу свободного менеджера...")
    
    if len(pvp_search_queue) >= 2:
        p1 = pvp_search_queue.pop(0)
        p2 = pvp_search_queue.pop(0)
        execute_match(p1, p2)

def execute_match(p1_id, p2_id):
    """Механика матча: сравнение силы атаки состава."""
    power1 = calculate_total_power(p1_id)
    power2 = calculate_total_power(p2_id)
    
    # Расчет вероятности победы
    total = power1 + power2
    chance1 = (power1 / total * 100) if total > 0 else 50
    
    winner = p1_id if random.randint(0, 100) < chance1 else p2_id
    loser = p2_id if winner == p1_id else p1_id
    
    users = load_data('users')
    users[str(winner)]['score'] += 5000
    save_data(users, 'users')
    
    msg = f"🏟 **ИТОГИ МАТЧА**\nПобедитель: {winner}\nПроигравший: {loser}\nНаграда: +5000 очков!"
    bot.send_message(winner, msg)
    bot.send_message(loser, msg)

# ==============================================================================
# [14] РАСШИРЕННАЯ АДМИН-ПАНЕЛЬ (УПРАВЛЕНИЕ БЕЗ ССЫЛОК)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🛠 Админ-панель")
def admin_panel_handler(message):
    if not check_admin_permission(message.from_user): return
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=create_admin_menu())

@bot.message_handler(func=lambda m: m.text == "➕ Добавить карту")
def admin_add_card(message):
    """Админ присылает данные и фото. Никаких URL."""
    msg = bot.send_message(message.chat.id, "Отправьте сообщение в формате:\nИмя|Редкость|Позиция|Клуб", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, lambda m: bot.register_next_step_handler(m, lambda photo: save_card_with_photo(photo, m.text)))

def save_card_with_photo(message, info):
    """Сохранение фото через File ID, которое прислал админ."""
    if not message.photo:
        bot.send_message(message.chat.id, "Нужно было прислать фото!")
        return
    
    photo_id = message.photo[-1].file_id
    parts = info.split('|')
    cards = load_data('cards')
    cards.append({"name": parts[0], "stars": int(parts[1]), "pos": parts[2], "club": parts[3], "photo_id": photo_id})
    save_data(cards, 'cards')
    bot.send_message(message.chat.id, "✅ Карточка успешно создана в базе!")

# ==============================================================================
# [15] СИСТЕМА УДАЛЕНИЯ СООБЩЕНИЙ (ДЛЯ ЧИСТОТЫ)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🏠 Назад в меню")
def back_to_menu(message):
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=create_main_menu(message.from_user.id))

# Запуск
if __name__ == "__main__":
    bot.infinity_polling()
