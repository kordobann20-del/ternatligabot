import telebot
from telebot import types
import random
import time
import json
import os
import sys
import logging

# ==============================================================================
# [1] НАСТРОЙКА СИСТЕМНОГО ЛОГИРОВАНИЯ И ОТЛАДКИ
# ==============================================================================
# Используется расширенное логирование для отслеживания всех действий игроков,
# матчмейкинга и системных ошибок базы данных.

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

# Уникальный токен вашего Telegram бота (замените на свой при необходимости)
TOKEN = "8886116833:AAEDyyrYKXH3WtY2BBFCOe4lZcaqlYBEaXY"

# Список администраторов (цифровые Telegram ID)
ADMINS = [7908057052, 1674945230]

bot = telebot.TeleBot(TOKEN)

# Конфигурация путей к файлам базы данных JSON
# Добавлены новые структуры для хранения отложенных матчей (если потребуется)
DB_FILES = {
    'cards': 'cards.json',         # База данных всех существующих карточек
    'colls': 'collections.json',   # Коллекции карточек игроков
    'squads': 'squads.json',       # Текущие футбольные составы пользователей
    'users': 'users_data.json',    # Профили пользователей, балансы (монеты), статистика
    'bans': 'bans.json',           # Черный список (заблокированные ID и юзернеймы)
    'promos': 'promos.json'        # Доступные промокоды и их параметры
}

# ==============================================================================
# [3] ИГРОВЫЕ ПАРАМЕТРЫ И КОНФИГУРАЦИЯ БАЛАНСА
# ==============================================================================

# Характеристики редкостей карт, шансы выпадения, стоимость в монетах и сила атаки
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

# Глобальные словари для отслеживания времени перезарядки действий (Cooldowns)
roll_cooldowns = {}
pvp_cooldowns = {}  # Здесь теперь 1 час (3600 секунд)

# Глобальные очереди для нового ПВП с реальными людьми
# pvp_queue хранит ID пользователя, который ищет игру
global_pvp_queue = []
# pvp_challenges хранит вызовы по юзернейму: {target_id: challenger_id}
pvp_challenges = {}

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

    with open(file_path, 'r', encoding='utf-8') as file_in:
        try:
            content = file_in.read()
            if not content.strip():
                return [] if key in ['cards', 'bans'] else {}
            return json.loads(content)
        except json.JSONDecodeError as json_error:
            logger.error(f"Файл {file_path} поврежден или имеет неверный формат JSON: {json_error}")
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

    if os.path.exists(file_path):
        try:
            backup_path = file_path + ".bak"
            if os.path.exists(backup_path):
                os.remove(backup_path)
            os.rename(file_path, backup_path)
        except Exception as backup_exception:
            logger.warning(f"Не удалось создать резервную копию для {file_path}: {backup_exception}")

    try:
        with open(file_path, 'w', encoding='utf-8') as file_out:
            json.dump(data_object, file_out, ensure_ascii=False, indent=4)
        return True
    except IOError as io_error:
        logger.critical(f"Ошибка ввода-вывода при сохранении таблицы {key} в файл {file_path}: {io_error}")
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
    """Проверяет, имеет ли пользователь административные права."""
    if user_obj is None:
        return False
    return user_obj.id in ADMINS

def check_ban_status(user_obj):
    """Проверяет, заблокирован ли пользователь в боте."""
    if user_obj is None:
        return False
        
    ban_list = load_data('bans')
    user_id_string = str(user_obj.id)
    user_name_string = user_obj.username.lower() if user_obj.username else "no_username_set"
    
    if user_id_string in ban_list or user_name_string in ban_list:
        return True
    return False

def calculate_total_power(user_id):
    """Рассчитывает суммарную силу атаки (мощность) состава игрока."""
    squad_data = load_data('squads')
    my_squad = squad_data.get(str(user_id), [None] * 7)
    
    power_sum = 0
    for card_item in my_squad:
        if card_item is not None and isinstance(card_item, dict):
            stars = card_item.get('stars', 1)
            if stars not in RARITY_STATS:
                stars = 1
            power_sum += RARITY_STATS[stars]['atk']
            
    return power_sum

def get_user_id_by_username(username):
    """Ищет Telegram ID пользователя в нашей базе по его @username."""
    username = username.replace("@", "").lower()
    users_db = load_data('users')
    for uid, udata in users_db.items():
        db_uname = udata.get('username', '').replace("@", "").lower()
        if db_uname == username:
            return uid
    return None

def log_action(user_id, action_name):
    """Фиксирует действия пользователей в консоли для мониторинга активности."""
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"ИГРОК: {user_id} | ДЕЙСТВИЕ: {action_name} | ВРЕМЯ: {current_time}")

# ==============================================================================
# [6] ИНТЕРФЕЙСНЫЙ ДВИЖОК (ГЕНЕРАЦИЯ КЛАВИАТУР СИСТЕМЫ)
# ==============================================================================

def create_main_menu(user_id):
    """Формирует главное меню управления для обычных пользователей."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    btn_roll = types.KeyboardButton("🎰 Крутить карту")
    btn_collection = types.KeyboardButton("🗂 Коллекция")
    btn_squad = types.KeyboardButton("📋 Состав")
    btn_profile = types.KeyboardButton("👤 Профиль")
    btn_top = types.KeyboardButton("🏆 Топ монет")
    btn_pvp = types.KeyboardButton("🏟 ПВП Арена")
    btn_promo = types.KeyboardButton("🎟 Промокод")
    btn_referrals = types.KeyboardButton("👥 Рефералы")
    
    markup.add(btn_roll, btn_collection)
    markup.add(btn_squad, btn_profile)
    markup.add(btn_top, btn_pvp)
    markup.add(btn_promo, btn_referrals)
    
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
    """Обработчик команды /start с реферальной системой."""
    if check_ban_status(message.from_user):
        bot.send_message(message.chat.id, "🚫 Вы заблокированы. Доступ к функциям симулятора закрыт.")
        return

    users_database = load_data('users')
    user_id_key = str(message.from_user.id)
    log_action(user_id_key, f"START_COMMAND_TRIGGERED (Text: {message.text})")

    inviter_id = None
    command_parts = message.text.split()
    if len(command_parts) > 1:
        inviter_id = command_parts[1].strip()

    if user_id_key not in users_database:
        user_display_name = f"@{message.from_user.username}" if message.from_user.username else f"id_{user_id_key}"
        
        users_database[user_id_key] = {
            "nick": message.from_user.first_name if message.from_user.first_name else "Футболист",
            "username": user_display_name,
            "score": 0, # В интерфейсе теперь это "монеты"
            "free_rolls": 0,
            "bonus_luck": 1.0,
            "refs": 0,
            "used_promos": []
        }
        logger.info(f"Зарегистрирован новый пользователь: ID {user_id_key}")
        
        if inviter_id and inviter_id in users_database and inviter_id != user_id_key:
            users_database[inviter_id]["score"] += 5000
            users_database[inviter_id]["free_rolls"] = users_database[inviter_id].get("free_rolls", 0) + 3
            users_database[inviter_id]["refs"] = users_database[inviter_id].get("refs", 0) + 1
            
            try:
                msg_to_inviter = (
                    "👥 **НОВЫЙ ИГРОК ПОДДКЛЮЧЕН!**\n\n"
                    "По вашей реферальной ссылке зарегистрировался новый менеджер.\n"
                    "🎁 **Вам начислено вознаграждение:**\n"
                    "— 💰 **+5,000 монет на баланс**\n"
                    "— 🎫 **+3 бесплатных прокрута карточек**"
                )
                bot.send_message(int(inviter_id), msg_to_inviter, parse_mode="Markdown")
            except Exception as referral_error:
                logger.error(f"Не удалось отправить пуш-уведомление рефереру {inviter_id}: {referral_error}")

        save_data(users_database, 'users')

    welcome_text = (
        "⚽️ **Приветствую, {}!**\n\n"
        "Вы попали в продвинутый симулятор футбольных карточек.\n"
        "Собирайте уникальные составы, прокачивайте команду, активируйте секретные промокоды "
        "и побеждайте других менеджеров в реальных ПВП битвах!\n\n"
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
    """Реферальная система для приглашения друзей."""
    if check_ban_status(message.from_user): return
        
    user_id = message.from_user.id
    users_db = load_data('users')
    
    try:
        bot_info = bot.get_me()
        bot_username = bot_info.username
    except Exception:
        bot_username = "FootballCardSimulatorBot"
    
    invite_link = f"https://t.me/{bot_username}?start={user_id}"
    user_profile_data = users_db.get(str(user_id), {})
    ref_count = user_profile_data.get("refs", 0)
    
    referral_text = (
        "👥 **РЕФЕРАЛЬНАЯ ПРОГРАММА**\n\n"
        "Развивайте футбольное сообщество бота и получайте ценные призы!\n\n"
        "🎁 **Награда за каждого приглашенного друга:**\n"
        "— 💰 **5,000 монет на счет**\n"
        "— 🎫 **3 бонусных прокрута карт**\n\n"
        "📊 Ваша личная статистика:\n"
        "— Всего приглашено игроков: **{}**\n\n"
        "🔗 Ваша уникальная ссылка для приглашений (нажмите для копирования):\n"
        "`{}`"
    ).format(ref_count, invite_link)
    
    bot.send_message(message.chat.id, referral_text, parse_mode="Markdown")

# ==============================================================================
# [8] АДМІНІСТРАТИВНА ПАНЕЛЬ ТА КЕРУВАННЯ КОНТЕНТОМ (РОЗШИРЕНА ВЕРСІЯ)
# ==============================================================================
# У цьому блоці реалізовано повний цикл управління базою даних (CRUD) для карток,
# промокодів, користувачів та глобальних налаштувань.

@bot.message_handler(func=lambda m: m.text == "🏠 Назад в меню")
def back_to_main_menu(message):
    """
    Універсальна функція повернення до головного меню.
    Скидає всі поточні стани та очищає контекст діалогу.
    """
    if check_ban_status(message.from_user): 
        return
        
    bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
    bot.send_message(
        message.chat.id, 
        "Ви повернулися до головного меню.", 
        reply_markup=create_main_menu(message.from_user.id)
    )

@bot.message_handler(func=lambda m: m.text == "🛠 Админ-панель")
def admin_panel_open(message):
    """
    Відкриває панель адміністратора та генерує швидке зведення по серверу (статистику).
    """
    if check_ban_status(message.from_user): 
        return
        
    if not check_admin_permission(message.from_user):
        bot.send_message(
            message.chat.id, 
            "⛔️ Помилка доступу: Ваш ідентифікатор не знайдено у списку адміністраторів."
        )
        return

    # Генерація статистики серверу для адміна
    users_db = load_data('users')
    cards_db = load_data('cards')
    promos_db = load_data('promos')
    bans_db = load_data('bans')
    
    total_users = len(users_db)
    total_cards = len(cards_db)
    total_promos = len(promos_db)
    total_bans = len(bans_db)
    
    total_coins_in_economy = sum(u.get('score', 0) for u in users_db.values())
    
    admin_welcome_text = (
        "🔐 **ПАНЕЛЬ КЕРУВАННЯ СЕРВЕРОМ**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 **Глобальна статистика:**\n"
        f"👥 Зареєстровано гравців: `{total_users}`\n"
        f"🗂 Карток у базі: `{total_cards}`\n"
        f"🎟 Активних промокодів: `{total_promos}`\n"
        f"🚫 Користувачів у бані: `{total_bans}`\n"
        f"💰 Всього монет в економіці: `{total_coins_in_economy}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Виберіть дію на клавіатурі нижче:"
    )
    
    bot.send_message(
        message.chat.id, 
        admin_welcome_text, 
        parse_mode="Markdown",
        reply_markup=create_admin_menu()
    )

# ------------------------------------------------------------------------------
# 8.1 СИСТЕМА ДОДАВАННЯ КАРТОК
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "➕ Добавить карту")
def admin_add_card_start(message):
    if not check_admin_permission(message.from_user): 
        return
        
    msg = bot.send_message(
        message.chat.id, 
        "📝 **КРОК 1/4: Ім'я футболіста**\n\n"
        "Введіть повне ім'я гравця (наприклад, Lionel Messi або Mykhailo Mudryk):", 
        parse_mode="Markdown",
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, process_card_name_add)

def process_card_name_add(message):
    if message.text == "❌ Отмена": 
        return back_to_main_menu(message)
        
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        msg = bot.send_message(
            message.chat.id, 
            "⚠️ Помилка: Ім'я має містити від 2 до 50 символів. Спробуйте ще раз:"
        )
        bot.register_next_step_handler(msg, process_card_name_add)
        return
        
    msg = bot.send_message(
        message.chat.id, 
        f"📝 **КРОК 2/4: Рідкісність**\n\n"
        f"Вибране ім'я: {name}\n"
        "Введіть цифру від 1 до 5, де:\n"
        "1 - Обычная (найслабша)\n"
        "2 - Необычная\n"
        "3 - Редкая\n"
        "4 - Эпическая\n"
        "5 - Легендарная (найсильніша)",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_card_rarity_add, name)

def process_card_rarity_add(message, name):
    if message.text == "❌ Отмена": 
        return back_to_main_menu(message)
        
    try:
        rarity = int(message.text.strip())
        if rarity not in RARITY_STATS:
            raise ValueError("Рідкісність поза межами допустимого діапазону.")
    except ValueError as e:
        logger.warning(f"Адмін помилився при введенні рідкісності: {e}")
        msg = bot.send_message(
            message.chat.id, 
            "⚠️ Помилка! Введіть тільки одну цифру від 1 до 5:"
        )
        bot.register_next_step_handler(msg, process_card_rarity_add, name)
        return

    positions_list = "\n".join([f"🔸 {k} — {v}" for k, v in POSITIONS_RU.items()])
    msg = bot.send_message(
        message.chat.id, 
        f"📝 **КРОК 3/4: Позиція на полі**\n\n"
        f"Виберіть одну з доступних позицій та введіть її код (наприклад, ГК або КФ):\n\n"
        f"{positions_list}",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_card_pos_add, name, rarity)

def process_card_pos_add(message, name, rarity):
    if message.text == "❌ Отмена": 
        return back_to_main_menu(message)
        
    pos = message.text.strip().upper()
    if pos not in POSITIONS_RU:
        msg = bot.send_message(
            message.chat.id, 
            "⚠️ Невідома позиція. Введіть точний код з наведених (наприклад, ЛЗ):"
        )
        bot.register_next_step_handler(msg, process_card_pos_add, name, rarity)
        return

    msg = bot.send_message(
        message.chat.id, 
        "📝 **КРОК 4/4: Фотографія**\n\n"
        "Тепер відправте **картинку** (фото) футболіста безпосередньо в цей чат.\n"
        "Бот автоматично завантажить її на сервери Telegram та збереже ідентифікатор.", 
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_card_photo_add, name, rarity, pos)

def process_card_photo_add(message, name, rarity, pos):
    if message.text == "❌ Отмена": 
        return back_to_main_menu(message)
    
    if not message.photo:
        msg = bot.send_message(
            message.chat.id, 
            "⚠️ Це не фотографія! Будь ласка, прикріпіть зображення через скріпку:"
        )
        bot.register_next_step_handler(msg, process_card_photo_add, name, rarity, pos)
        return

    # Беремо фотографію найкращої якості (остання в списку)
    try:
        photo_file_id = message.photo[-1].file_id
        
        cards_db = load_data('cards')
        # Генерація унікального ID для нової картки
        new_id = 1 if not cards_db else max([c.get('id', 0) for c in cards_db]) + 1
        
        new_card = {
            "id": new_id,
            "name": name,
            "stars": rarity,
            "pos": pos,
            "photo": photo_file_id
        }
        
        cards_db.append(new_card)
        if save_data(cards_db, 'cards'):
            card_info = (
                f"✅ **КАРТКА УСПІШНО ДОДАНА!**\n\n"
                f"🆔 ID картки: `{new_id}`\n"
                f"👤 Ім'я: **{name}**\n"
                f"⭐ Рідкісність: **{rarity}** ({RARITY_STATS[rarity]['label']})\n"
                f"🎯 Позиція: **{pos}** ({POSITIONS_RU[pos]})\n"
                f"⚔️ Сила атаки (ПВП): `{RARITY_STATS[rarity]['atk']}`"
            )
            bot.send_photo(
                message.chat.id, 
                photo_file_id, 
                caption=card_info,
                parse_mode="Markdown",
                reply_markup=create_admin_menu()
            )
            logger.info(f"[АДМІН] Картка '{name}' (ID {new_id}) успішно створена.")
        else:
            bot.send_message(
                message.chat.id, 
                "❌ Сталася критична помилка при збереженні бази даних. Перевірте логи.",
                reply_markup=create_admin_menu()
            )
    except Exception as e:
        logger.error(f"Помилка при обробці фотографії картки: {e}")
        bot.send_message(
            message.chat.id, 
            "❌ Сталася помилка при завантаженні фотографії. Спробуйте ще раз.",
            reply_markup=create_admin_menu()
        )

# ------------------------------------------------------------------------------
# 8.2 СИСТЕМА ВИДАЛЕННЯ КАРТОК
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "🗑 Удалить карту")
def admin_delete_card_start(message):
    if not check_admin_permission(message.from_user): return
    
    msg = bot.send_message(
        message.chat.id, 
        "🗑 **ВИДАЛЕННЯ КАРТКИ**\n\n"
        "Введіть числовий ID картки, яку ви хочете назавжди видалити з гри:", 
        parse_mode="Markdown",
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, process_card_delete)

def process_card_delete(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    
    try:
        target_id = int(message.text.strip())
    except ValueError:
        msg = bot.send_message(message.chat.id, "⚠️ ID має бути числом. Введіть ID ще раз:")
        bot.register_next_step_handler(msg, process_card_delete)
        return
        
    cards_db = load_data('cards')
    card_index = -1
    card_name = ""
    
    for i, card in enumerate(cards_db):
        if card.get('id') == target_id:
            card_index = i
            card_name = card.get('name', 'Невідомо')
            break
            
    if card_index != -1:
        # Видаляємо картку з глобальної бази
        del cards_db[card_index]
        save_data(cards_db, 'cards')
        
        bot.send_message(
            message.chat.id, 
            f"✅ Картка **{card_name}** (ID: `{target_id}`) була успішно видалена з бази.",
            parse_mode="Markdown",
            reply_markup=create_admin_menu()
        )
        logger.warning(f"[АДМІН] Видалено картку ID {target_id} ({card_name}).")
    else:
        bot.send_message(
            message.chat.id, 
            f"❌ Картку з ID `{target_id}` не знайдено.",
            parse_mode="Markdown",
            reply_markup=create_admin_menu()
        )

# ------------------------------------------------------------------------------
# 8.3 СИСТЕМА РЕДАГУВАННЯ КАРТОК
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "📝 Изменить карту")
def admin_edit_card_start(message):
    if not check_admin_permission(message.from_user): return
    
    msg = bot.send_message(
        message.chat.id, 
        "Введіть ID картки, яку потрібно відредагувати:", 
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, process_card_edit_find)

def process_card_edit_find(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    
    try:
        target_id = int(message.text.strip())
    except ValueError:
        msg = bot.send_message(message.chat.id, "⚠️ Помилка: Введіть число. Спробуйте ще раз:")
        bot.register_next_step_handler(msg, process_card_edit_find)
        return
        
    cards_db = load_data('cards')
    card_found = None
    
    for card in cards_db:
        if card.get('id') == target_id:
            card_found = card
            break
            
    if not card_found:
        bot.send_message(
            message.chat.id, 
            f"❌ Картку з ID {target_id} не знайдено.", 
            reply_markup=create_admin_menu()
        )
        return
        
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("✏️ Ім'я"), 
        types.KeyboardButton("✏️ Рідкісність"),
        types.KeyboardButton("✏️ Позицію"),
        types.KeyboardButton("🖼 Фото"),
        types.KeyboardButton("❌ Отмена")
    )
    
    msg = bot.send_message(
        message.chat.id, 
        f"Картку знайдено: **{card_found.get('name')}** (⭐ {card_found.get('stars')})\n"
        f"Що саме ви хочете змінити?",
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_card_edit_field, target_id)

def process_card_edit_field(message, target_id):
    choice = message.text
    if choice == "❌ Отмена": return back_to_main_menu(message)
    
    if choice == "✏️ Ім'я":
        msg = bot.send_message(message.chat.id, "Введіть нове ім'я:", reply_markup=create_cancel_menu())
        bot.register_next_step_handler(msg, apply_card_edit, target_id, 'name')
    elif choice == "✏️ Рідкісність":
        msg = bot.send_message(message.chat.id, "Введіть нову рідкісність (1-5):", reply_markup=create_cancel_menu())
        bot.register_next_step_handler(msg, apply_card_edit, target_id, 'stars')
    elif choice == "✏️ Позицію":
        msg = bot.send_message(message.chat.id, "Введіть нову позицію (напр., ЛВ):", reply_markup=create_cancel_menu())
        bot.register_next_step_handler(msg, apply_card_edit, target_id, 'pos')
    elif choice == "🖼 Фото":
        msg = bot.send_message(message.chat.id, "Відправте нове фото:", reply_markup=create_cancel_menu())
        bot.register_next_step_handler(msg, apply_card_edit, target_id, 'photo')
    else:
        bot.send_message(message.chat.id, "Невідома дія.", reply_markup=create_admin_menu())

def apply_card_edit(message, target_id, field):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    
    cards_db = load_data('cards')
    for card in cards_db:
        if card.get('id') == target_id:
            if field == 'name':
                card['name'] = message.text.strip()
            elif field == 'stars':
                try:
                    stars = int(message.text.strip())
                    if stars not in RARITY_STATS: raise ValueError
                    card['stars'] = stars
                except:
                    bot.send_message(message.chat.id, "⚠️ Невірна рідкісність.", reply_markup=create_admin_menu())
                    return
            elif field == 'pos':
                pos = message.text.strip().upper()
                if pos not in POSITIONS_RU:
                    bot.send_message(message.chat.id, "⚠️ Невірна позиція.", reply_markup=create_admin_menu())
                    return
                card['pos'] = pos
            elif field == 'photo':
                if not message.photo:
                    bot.send_message(message.chat.id, "⚠️ Потрібно фото.", reply_markup=create_admin_menu())
                    return
                card['photo'] = message.photo[-1].file_id
                
            save_data(cards_db, 'cards')
            bot.send_message(
                message.chat.id, 
                f"✅ Картку успішно оновлено!", 
                reply_markup=create_admin_menu()
            )
            return

# ------------------------------------------------------------------------------
# 8.4 СИСТЕМА УПРАВЛІННЯ ПРОМОКОДАМИ
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "🎟 +Промокод")
def admin_add_promo_start(message):
    if not check_admin_permission(message.from_user): return
    
    msg = bot.send_message(
        message.chat.id, 
        "Введіть текст промокоду (наприклад, FREECOINS2026):", 
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, process_promo_code_add)

def process_promo_code_add(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    code = message.text.strip().upper()
    
    msg = bot.send_message(message.chat.id, f"Скільки **монет** дасть промокод {code}?")
    bot.register_next_step_handler(msg, process_promo_coins_add, code)

def process_promo_coins_add(message, code):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    try:
        coins = int(message.text.strip())
    except:
        msg = bot.send_message(message.chat.id, "Введіть число!")
        bot.register_next_step_handler(msg, process_promo_coins_add, code)
        return
        
    msg = bot.send_message(message.chat.id, f"Скільки **безкоштовних прокрутів** дасть промокод?")
    bot.register_next_step_handler(msg, process_promo_rolls_add, code, coins)

def process_promo_rolls_add(message, code, coins):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    try:
        rolls = int(message.text.strip())
    except:
        msg = bot.send_message(message.chat.id, "Введіть число!")
        bot.register_next_step_handler(msg, process_promo_rolls_add, code, coins)
        return
        
    msg = bot.send_message(
        message.chat.id, 
        "Скільки разів його можна активувати загалом? (Введіть 0 для безліміту):"
    )
    bot.register_next_step_handler(msg, process_promo_limit_add, code, coins, rolls)

def process_promo_limit_add(message, code, coins, rolls):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    try:
        limit = int(message.text.strip())
    except:
        msg = bot.send_message(message.chat.id, "Введіть число!")
        bot.register_next_step_handler(msg, process_promo_limit_add, code, coins, rolls)
        return
        
    promos_db = load_data('promos')
    promos_db[code] = {
        "coins": coins,
        "rolls": rolls,
        "limit": limit,
        "activations": 0
    }
    save_data(promos_db, 'promos')
    
    bot.send_message(
        message.chat.id, 
        f"✅ Промокод `{code}` створено!\n"
        f"💰 Монет: {coins}\n"
        f"🎫 Спінів: {rolls}\n"
        f"🔄 Ліміт: {'Безліміт' if limit == 0 else limit}",
        parse_mode="Markdown",
        reply_markup=create_admin_menu()
    )

@bot.message_handler(func=lambda m: m.text == "🗑 Удалить промокод")
def admin_del_promo_start(message):
    if not check_admin_permission(message.from_user): return
    
    promos_db = load_data('promos')
    if not promos_db:
        bot.send_message(message.chat.id, "Активних промокодів немає.")
        return
        
    promo_list = "\n".join(list(promos_db.keys()))
    msg = bot.send_message(
        message.chat.id, 
        f"Список промокодів:\n{promo_list}\n\nВведіть код для видалення:", 
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, process_promo_del)

def process_promo_del(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    code = message.text.strip().upper()
    
    promos_db = load_data('promos')
    if code in promos_db:
        del promos_db[code]
        save_data(promos_db, 'promos')
        bot.send_message(message.chat.id, f"✅ Промокод {code} видалено.", reply_markup=create_admin_menu())
    else:
        bot.send_message(message.chat.id, "❌ Такого промокоду не існує.", reply_markup=create_admin_menu())

# ------------------------------------------------------------------------------
# 8.5 БЛОКУВАННЯ ТА РОЗБЛОКУВАННЯ КОРИСТУВАЧІВ
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "🚫 Забанить")
def admin_ban_start(message):
    if not check_admin_permission(message.from_user): return
    msg = bot.send_message(
        message.chat.id, 
        "Введіть Telegram ID або @username порушника:", 
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, process_ban_user)

def process_ban_user(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    
    target = message.text.strip().lower().replace("@", "")
    bans_db = load_data('bans')
    
    if target not in bans_db:
        bans_db.append(target)
        save_data(bans_db, 'bans')
        bot.send_message(
            message.chat.id, 
            f"✅ Гравця `{target}` заблоковано назавжди. Йому обмежено доступ до ПВП та команд.", 
            parse_mode="Markdown", 
            reply_markup=create_admin_menu()
        )
        logger.warning(f"АДМІН {message.from_user.id} заблокував {target}")
    else:
        bot.send_message(message.chat.id, "⚠️ Цей гравець вже знаходиться в бані.", reply_markup=create_admin_menu())

@bot.message_handler(func=lambda m: m.text == "✅ Разбанить")
def admin_unban_start(message):
    if not check_admin_permission(message.from_user): return
    msg = bot.send_message(message.chat.id, "Введіть ID або @username для амністії:", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, process_unban_user)

def process_unban_user(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    
    target = message.text.strip().lower().replace("@", "")
    bans_db = load_data('bans')
    
    if target in bans_db:
        bans_db.remove(target)
        save_data(bans_db, 'bans')
        bot.send_message(
            message.chat.id, 
            f"✅ Гравця `{target}` розблоковано. Доступ відновлено.", 
            parse_mode="Markdown", 
            reply_markup=create_admin_menu()
        )
    else:
        bot.send_message(message.chat.id, "⚠️ Цього гравця немає в чорному списку.", reply_markup=create_admin_menu())

@bot.message_handler(func=lambda m: m.text == "🧨 Обнулить бота")
def admin_reset_start(message):
    if not check_admin_permission(message.from_user): return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("⚠️ ПІДТВЕРДЖУЮ ВАЙП"), types.KeyboardButton("❌ Отмена"))
    msg = bot.send_message(
        message.chat.id, 
        "‼️ **УВАГА! КРИТИЧНА ДІЯ!** ‼️\n"
        "Це видалить УСІХ користувачів, їх монети, склади та колекції.\n"
        "Карточки та промокоди залишаться.\n"
        "Ви впевнені?", 
        parse_mode="Markdown", 
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_reset_confirm)

def process_reset_confirm(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    if message.text == "⚠️ ПІДТВЕРДЖУЮ ВАЙП":
        save_data({}, 'users')
        save_data({}, 'colls')
        save_data({}, 'squads')
        bot.send_message(
            message.chat.id, 
            "🧨 **БАЗУ ДАНИХ ОЧИЩЕНО.** Гравці, економіка та склади видалені.", 
            parse_mode="Markdown", 
            reply_markup=create_admin_menu()
        )
        logger.critical(f"АДМІН {message.from_user.id} ЗРОБИВ ПОВНИЙ ВАЙП БАЗИ!")
    else:
        back_to_main_menu(message)

# ==============================================================================
# [9] ПРОФІЛЬ, ТОП ГРАВЦІВ ТА АКТИВАЦІЯ ПРОМОКОДІВ (РОЗШИРЕНІ)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile_handler(message):
    """
    Генерує детальну картку профілю користувача з підрахунком статистики.
    """
    if check_ban_status(message.from_user): return
    
    user_id = str(message.from_user.id)
    users_db = load_data('users')
    
    if user_id not in users_db:
        bot.send_message(
            message.chat.id, 
            "Ваш профіль ще не створено. Натисніть /start", 
            reply_markup=types.ReplyKeyboardRemove()
        )
        return
        
    user_data = users_db[user_id]
    nick = user_data.get('nick', 'Менеджер')
    coins = user_data.get('score', 0)
    rolls = user_data.get('free_rolls', 0)
    refs = user_data.get('refs', 0)
    
    colls_db = load_data('colls')
    my_cards = colls_db.get(user_id, [])
    
    total_power = calculate_total_power(message.from_user.id)
    
    # Розрахунок орієнтовної вартості клубу (сума вартостей карток)
    club_value = 0
    legendary_count = 0
    for card_id in my_cards:
        # Пошук інформації про картку в загальній базі
        cards_global = load_data('cards')
        for c in cards_global:
            if c.get('id') == card_id:
                stars = c.get('stars', 1)
                club_value += RARITY_STATS.get(stars, {}).get('score', 0)
                if stars == 5:
                    legendary_count += 1
                break
                
    profile_text = (
        f"👤 **КАРТКА МЕНЕДЖЕРА:** {nick}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 **Баланс:** `{coins}` монет\n"
        f"🎟 **Доступно прокрутів:** `{rolls}`\n"
        f"👥 **Запрошено друзів:** `{refs}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡️ **Бойова міць складу (ПВП):** `{total_power}`\n"
        f"🗂 **Зібрано унікальних карток:** `{len(my_cards)}`\n"
        f"👑 **Легендарних гравців у колекції:** `{legendary_count}`\n"
        f"💎 **Орієнтовна вартість клубу:** `{club_value}` монет\n"
    )
    
    bot.send_message(
        message.chat.id, 
        profile_text, 
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text == "🏆 Топ монет")
def top_score_handler(message):
    """
    Виводить глобальний рейтинг найбагатших гравців за кількістю монет.
    """
    if check_ban_status(message.from_user): return
    
    users_db = load_data('users')
    if not users_db:
        bot.send_message(message.chat.id, "Сервер поки порожній. Станьте першим!")
        return
        
    # Сортування словника за значенням 'score' (монети) за спаданням
    sorted_users = sorted(
        users_db.items(), 
        key=lambda item: item[1].get('score', 0), 
        reverse=True
    )
    
    top_text = "🏆 **ГЛОБАЛЬНИЙ РЕЙТИНГ (МОНЕТИ)** 🏆\n\n"
    
    for i, (uid, udata) in enumerate(sorted_users[:15]):  # Топ-15
        if i == 0: medal = "🥇"
        elif i == 1: medal = "🥈"
        elif i == 2: medal = "🥉"
        else: medal = f"`{i+1}.`"
        
        nick = udata.get('nick', 'Unknown')
        # Обрізаємо занадто довгі ніки
        if len(nick) > 15: nick = nick[:12] + "..."
        
        coins = udata.get('score', 0)
        top_text += f"{medal} {nick} ➖ `{coins}`\n"
        
    top_text += "\n*Грайте в ПВП та відкривайте паки, щоб піднятися вище!*"
    bot.send_message(message.chat.id, top_text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎟 Промокод")
def promo_handler(message):
    """
    Обробник для активації промокодів користувачами.
    """
    if check_ban_status(message.from_user): return
    
    msg = bot.send_message(
        message.chat.id, 
        "🎁 **АКТИВАЦІЯ ПРОМОКОДУ**\n\n"
        "Введіть ваш секретний код нижче:", 
        parse_mode="Markdown",
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, process_promo_input)

def process_promo_input(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    
    code = message.text.strip().upper()
    user_id = str(message.from_user.id)
    
    promos_db = load_data('promos')
    users_db = load_data('users')
    
    if code not in promos_db:
        bot.send_message(
            message.chat.id, 
            "❌ Невірний промокод або його термін дії закінчився.", 
            reply_markup=create_main_menu(message.from_user.id)
        )
        return
        
    user_profile = users_db.get(user_id, {})
    used_promos = user_profile.get('used_promos', [])
    
    if code in used_promos:
        bot.send_message(
            message.chat.id, 
            "⚠️ Ви вже активували цей промокод раніше на цьому акаунті!", 
            reply_markup=create_main_menu(message.from_user.id)
        )
        return
        
    promo_data = promos_db[code]
    activations = promo_data.get('activations', 0)
    limit = promo_data.get('limit', 0)
    
    if limit > 0 and activations >= limit:
        bot.send_message(
            message.chat.id, 
            "❌ На жаль, ліміт активацій цього промокоду вичерпано.", 
            reply_markup=create_main_menu(message.from_user.id)
        )
        return
        
    # Нарахування нагород
    reward_coins = promo_data.get('coins', 0)
    reward_rolls = promo_data.get('rolls', 0)
    
    users_db[user_id]['score'] = users_db[user_id].get('score', 0) + reward_coins
    users_db[user_id]['free_rolls'] = users_db[user_id].get('free_rolls', 0) + reward_rolls
    
    if 'used_promos' not in users_db[user_id]:
        users_db[user_id]['used_promos'] = []
    users_db[user_id]['used_promos'].append(code)
    
    promos_db[code]['activations'] = activations + 1
    
    save_data(users_db, 'users')
    save_data(promos_db, 'promos')
    
    success_msg = f"✅ **УСПІХ! ПРОМОКОД АКТИВОВАНО!**\n\nВи отримали бонуси на свій рахунок:\n"
    if reward_coins > 0: success_msg += f"💰 Монети: `+{reward_coins}`\n"
    if reward_rolls > 0: success_msg += f"🎫 Спіни: `+{reward_rolls}`\n"
    
    bot.send_message(
        message.chat.id, 
        success_msg, 
        parse_mode="Markdown", 
        reply_markup=create_main_menu(message.from_user.id)
    )
    logger.info(f"Гравець {user_id} активував промокод {code}")


# ==============================================================================
# [10] СИСТЕМА ВИПАДАННЯ КАРТОК (GACHA / РОЛЛ)
# ==============================================================================

def get_random_card_by_rarity(target_rarity):
    """
    Алгоритм вибору випадкової картки з бази даних на основі заданої рідкісності.
    Якщо карток такої рідкісності немає, повертає будь-яку доступну картку.
    """
    cards_db = load_data('cards')
    if not cards_db:
        return None
        
    filtered_cards = [c for c in cards_db if c.get('stars', 1) == target_rarity]
    if not filtered_cards:
        logger.warning(f"У базі немає карток рідкісності {target_rarity}. Видаємо випадкову.")
        return random.choice(cards_db)
        
    return random.choice(filtered_cards)

def roll_gacha_logic():
    """
    Обчислює рідкісність картки, що випаде, на основі закладених шансів.
    """
    roll_val = random.randint(1, 100)
    cumulative = 0
    
    # RARITY_STATS визначена у Частині 1
    # 1: 35%, 2: 30%, 3: 20%, 4: 10%, 5: 5%
    for rarity, data in sorted(RARITY_STATS.items()):
        cumulative += data['chance']
        if roll_val <= cumulative:
            return rarity
    return 1

@bot.message_handler(func=lambda m: m.text == "🎰 Крутить карту")
def roll_card_handler(message):
    """
    Обробник відкриття футбольного пака.
    Перевіряє наявність безкоштовних прокрутів або монет.
    """
    if check_ban_status(message.from_user): return
    
    user_id = str(message.from_user.id)
    users_db = load_data('users')
    cards_db = load_data('cards')
    
    if not cards_db:
        bot.send_message(message.chat.id, "❌ У базі поки що немає жодної картки. Адміністратор має додати їх.")
        return
        
    if user_id not in users_db:
        bot.send_message(message.chat.id, "Ваш профіль не знайдено. Напишіть /start")
        return
        
    user_data = users_db[user_id]
    free_rolls = user_data.get('free_rolls', 0)
    coins = user_data.get('score', 0)
    
    roll_cost_coins = 1000  # Вартість одного прокруту в монетах
    
    # Перевірка балансу
    if free_rolls > 0:
        users_db[user_id]['free_rolls'] -= 1
        payment_type = "Безкоштовний спін 🎫"
    elif coins >= roll_cost_coins:
        users_db[user_id]['score'] -= roll_cost_coins
        payment_type = f"💰 {roll_cost_coins} монет"
    else:
        bot.send_message(
            message.chat.id, 
            f"❌ Недостатньо коштів!\nВідкриття паку коштує `{roll_cost_coins}` монет.\nВаш баланс: `{coins}` монет.",
            parse_mode="Markdown"
        )
        return
        
    save_data(users_db, 'users')
    
    # Анімація відкриття паку (затримка для інтриги)
    anim_msg = bot.send_message(message.chat.id, "🔄 Відкриваємо футбольний пак...")
    time.sleep(1)
    bot.edit_message_text("⚽️ М'яч летить у сітку...", chat_id=message.chat.id, message_id=anim_msg.message_id)
    time.sleep(1)
    
    # Логіка випадіння
    won_rarity = roll_gacha_logic()
    won_card = get_random_card_by_rarity(won_rarity)
    
    if not won_card:
        bot.send_message(message.chat.id, "Помилка генерації картки. Зверніться до адміна.")
        return
        
    # Додавання до колекції гравця
    colls_db = load_data('colls')
    if user_id not in colls_db:
        colls_db[user_id] = []
        
    colls_db[user_id].append(won_card['id'])
    save_data(colls_db, 'colls')
    
    # Формування результату
    rarity_label = RARITY_STATS[won_rarity]['label']
    atk_power = RARITY_STATS[won_rarity]['atk']
    
    bot.delete_message(chat_id=message.chat.id, message_id=anim_msg.message_id)
    
    result_text = (
        f"🎉 **ВІТАЄМО З НОВИМ ГРАВЦЕМ!** 🎉\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Ім'я:** {won_card['name']}\n"
        f"⭐ **Рідкісність:** {won_rarity} ({rarity_label})\n"
        f"🎯 **Позиція:** {won_card['pos']} ({POSITIONS_RU.get(won_card['pos'], 'Невідомо')})\n"
        f"⚔️ **Сила атаки:** `{atk_power}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 Оплачено: {payment_type}"
    )
    
    # Відправка фотографії з підписом
    try:
        bot.send_photo(
            message.chat.id, 
            won_card['photo'], 
            caption=result_text, 
            parse_mode="Markdown",
            reply_markup=create_main_menu(message.from_user.id)
        )
    except Exception as e:
        logger.error(f"Помилка відправки фото картки {won_card['id']}: {e}")
        bot.send_message(message.chat.id, result_text + "\n*(Зображення тимчасово недоступне)*", parse_mode="Markdown")
        
    logger.info(f"Гравець {user_id} вибив картку ID {won_card['id']} (Рідкісність: {won_rarity})")

# ==============================================================================
# [11] УПРАВЛІННЯ КОЛЕКЦІЄЮ (ІНВЕНТАР)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🗂 Коллекция")
def collection_handler(message):
    """
    Відображає всі картки, які є у гравця, з використанням простої пагінації в тексті.
    """
    if check_ban_status(message.from_user): return
    
    user_id = str(message.from_user.id)
    colls_db = load_data('colls')
    my_card_ids = colls_db.get(user_id, [])
    
    if not my_card_ids:
        bot.send_message(
            message.chat.id, 
            "📭 Ваша колекція порожня. Використовуйте '🎰 Крутить карту', щоб отримати гравців."
        )
        return
        
    cards_db = load_data('cards')
    
    # Підрахунок кількості кожної картки (у разі дублікатів)
    inventory_counts = {}
    for cid in my_card_ids:
        inventory_counts[cid] = inventory_counts.get(cid, 0) + 1
        
    collection_text = f"🗂 **ВАША ФУТБОЛЬНА КОЛЕКЦІЯ** (Всього: {len(my_card_ids)})\n\n"
    
    # Сортуємо картки за рідкісністю (від найсильніших до найслабших)
    my_cards_full_info = []
    for cid, count in inventory_counts.items():
        for c in cards_db:
            if c['id'] == cid:
                my_cards_full_info.append({
                    "id": cid,
                    "name": c['name'],
                    "stars": c['stars'],
                    "pos": c['pos'],
                    "count": count
                })
                break
                
    my_cards_full_info.sort(key=lambda x: x['stars'], reverse=True)
    
    for c in my_cards_full_info:
        star_str = "⭐" * c['stars']
        collection_text += f"ID:`{c['id']}` | **{c['name']}** | {c['pos']} | {star_str} | x{c['count']}\n"
        
    if len(collection_text) > 4000:
        collection_text = collection_text[:3900] + "\n\n... (Показано не всі картки через ліміти Telegram)"
        
    bot.send_message(message.chat.id, collection_text, parse_mode="Markdown")

# ==============================================================================
# [12] ФОРМУВАННЯ СУПЕР-СКЛАДУ (7 ПОЗИЦІЙ)
# ==============================================================================

def generate_squad_markup(user_id):
    """
    Генерує інлайн-клавіатуру для керування складом.
    Кожна кнопка відповідає за одну з 7 позицій (SQUAD_SLOTS з Частини 1).
    """
    squads_db = load_data('squads')
    my_squad = squads_db.get(str(user_id), [None] * 7)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for i in range(7):
        slot_info = SQUAD_SLOTS[i]
        card_in_slot = my_squad[i]
        
        if card_in_slot:
            btn_text = f"{slot_info['label']}: {card_in_slot['name']} (⭐{card_in_slot['stars']})"
        else:
            btn_text = f"{slot_info['label']}: ❌ Порожньо"
            
        callback_data = f"set_squad_{i}"
        markup.add(types.InlineKeyboardButton(text=btn_text, callback_data=callback_data))
        
    markup.add(types.InlineKeyboardButton(text="🔄 Оновити міць складу", callback_data="refresh_squad"))
    return markup

@bot.message_handler(func=lambda m: m.text == "📋 Состав")
def squad_menu_handler(message):
    """
    Головне меню управління складом команди.
    """
    if check_ban_status(message.from_user): return
    
    user_id = message.from_user.id
    total_power = calculate_total_power(user_id)
    
    text = (
        "📋 **СУПЕР-СКЛАД ВАШОЇ КОМАНДИ**\n\n"
        "Сформуйте найкращу команду для участі в ПВП арені.\n"
        f"⚡️ **Загальна бойова міць:** `{total_power}`\n\n"
        "Натисніть на позицію нижче, щоб призначити або змінити гравця:"
    )
    
    bot.send_message(
        message.chat.id, 
        text, 
        parse_mode="Markdown", 
        reply_markup=generate_squad_markup(user_id)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_squad_'))
def handle_set_squad_slot(call):
    """
    Обробка натискання на конкретний слот складу.
    Запитує у користувача ID картки для встановлення.
    """
    slot_index = int(call.data.split('_')[2])
    slot_info = SQUAD_SLOTS[slot_index]
    
    msg = bot.send_message(
        call.message.chat.id,
        f"Ви обрали позицію **{slot_info['label']}**.\n\n"
        f"Відкрийте свою '🗂 Коллекция' та знайдіть потрібного гравця.\n"
        f"Введіть числовий **ID картки**, яку хочете поставити на цю позицію\n"
        f"(Увага: картка повинна відповідати позиції `{slot_info['code']}`):",
        parse_mode="Markdown",
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, process_equip_card, slot_index, slot_info['code'])
    bot.answer_callback_query(call.id)

def process_equip_card(message, slot_index, required_pos):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    
    try:
        card_id = int(message.text.strip())
    except ValueError:
        msg = bot.send_message(message.chat.id, "⚠️ ID має бути числом. Введіть ще раз:")
        bot.register_next_step_handler(msg, process_equip_card, slot_index, required_pos)
        return
        
    user_id = str(message.from_user.id)
    colls_db = load_data('colls')
    my_collection = colls_db.get(user_id, [])
    
    if card_id not in my_collection:
        bot.send_message(
            message.chat.id, 
            "❌ У вас немає картки з таким ID у колекції.",
            reply_markup=create_main_menu(message.from_user.id)
        )
        return
        
    cards_db = load_data('cards')
    target_card = next((c for c in cards_db if c['id'] == card_id), None)
    
    if not target_card:
        bot.send_message(message.chat.id, "❌ Картку не знайдено в глобальній базі.", reply_markup=create_main_menu(message.from_user.id))
        return
        
    if target_card['pos'] != required_pos:
        bot.send_message(
            message.chat.id, 
            f"❌ Цей гравець не може грати на цій позиції!\nЙого позиція: {target_card['pos']}, а потрібна: {required_pos}.",
            reply_markup=create_main_menu(message.from_user.id)
        )
        return
        
    # Встановлюємо гравця у склад
    squads_db = load_data('squads')
    if user_id not in squads_db:
        squads_db[user_id] = [None] * 7
        
    # Перевірка на дублікати у складі (щоб не поставити Мессі двічі)
    for i, c in enumerate(squads_db[user_id]):
        if c and c.get('id') == card_id and i != slot_index:
            bot.send_message(
                message.chat.id, 
                "⚠️ Цей гравець вже стоїть на іншій позиції у вашому складі!",
                reply_markup=create_main_menu(message.from_user.id)
            )
            return
            
    squads_db[user_id][slot_index] = target_card
    save_data(squads_db, 'squads')
    
    bot.send_message(
        message.chat.id, 
        f"✅ Гравця **{target_card['name']}** успішно призначено на позицію {required_pos}!",
        parse_mode="Markdown",
        reply_markup=create_main_menu(message.from_user.id)
    )

@bot.callback_query_handler(func=lambda call: call.data == "refresh_squad")
def handle_refresh_squad(call):
    """Оновлює повідомлення зі складом (для перерахунку міці)."""
    user_id = call.from_user.id
    total_power = calculate_total_power(user_id)
    
    text = (
        "📋 **СУПЕР-СКЛАД ВАШОЇ КОМАНДИ**\n\n"
        "Сформуйте найкращу команду для участі в ПВП арені.\n"
        f"⚡️ **Загальна бойова міць:** `{total_power}`\n\n"
        "Натисніть на позицію нижче, щоб призначити або змінити гравця:"
    )
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=generate_squad_markup(user_id)
        )
    except:
        pass # Якщо текст не змінився, ігноруємо помилку Telegram
    bot.answer_callback_query(call.id, "Склад оновлено!")

# ==============================================================================
# [13] СИСТЕМА ПВП АРЕНИ (МАТЧМЕЙКІНГ, ВИКЛИКИ ТА БОЇ)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🏟 ПВП Арена")
def pvp_menu_handler(message):
    """
    Головне меню ПВП. Перевіряє кулдаун (1 година) та пропонує вибір типу бою.
    Адміністратори ігнорують кулдаун.
    """
    if check_ban_status(message.from_user): return
    
    user_id = message.from_user.id
    
    # Перевірка кулдауну (3600 секунд = 1 година)
    is_admin = check_admin_permission(message.from_user)
    if not is_admin:
        last_played = pvp_cooldowns.get(user_id, 0)
        time_since_played = time.time() - last_played
        if time_since_played < 3600:
            minutes_left = int((3600 - time_since_played) // 60)
            bot.send_message(
                message.chat.id, 
                f"⏳ Ваша команда відновлює сили.\nНаступний матч буде доступний через **{minutes_left} хвилин**.",
                parse_mode="Markdown"
            )
            return
            
    # Перевірка, чи не порожній склад
    total_power = calculate_total_power(user_id)
    if total_power == 0:
        bot.send_message(
            message.chat.id, 
            "⚠️ Ваш склад абсолютно порожній! Зайдіть у '📋 Состав' та екіпіруйте гравців перед виходом на поле."
        )
        return
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_search = types.InlineKeyboardButton("🔍 Пошук випадкового супротивника", callback_data="pvp_search")
    btn_challenge = types.InlineKeyboardButton("⚔️ Виклик за @username", callback_data="pvp_challenge")
    markup.add(btn_search, btn_challenge)
    
    bot.send_message(
        message.chat.id, 
        "🏟 **ВІТАЄМО НА ПВП АРЕНІ**\n\n"
        "Тут ви можете змагатися з реальними гравцями!\n"
        "Переможець забирає цінні монети, а переможений втрачає частину балансу.\n\n"
        "Оберіть режим:",
        parse_mode="Markdown",
        reply_markup=markup
    )

# --- РЕЖИМ 1: ПОШУК ВИПАДКОВОГО ГРАВЦЯ ---
@bot.callback_query_handler(func=lambda call: call.data == "pvp_search")
def pvp_search_matchmaking(call):
    user_id = call.from_user.id
    
    # Видаляємо повідомлення з кнопками, щоб уникнути спаму кліками
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    if user_id in global_pvp_queue:
        bot.send_message(call.message.chat.id, "Ви вже знаходитесь у черзі пошуку матчу. Очікуйте...")
        return
        
    # Якщо черга не порожня, і в ній інший гравець — починаємо матч
    opponent_id = None
    for queued_id in global_pvp_queue:
        if queued_id != user_id:
            opponent_id = queued_id
            break
            
    if opponent_id:
        global_pvp_queue.remove(opponent_id)
        bot.send_message(call.message.chat.id, "🔍 Супротивника знайдено! Починаємо матч...")
        try:
            bot.send_message(opponent_id, "🔍 Для вас знайдено супротивника в черзі! Починаємо матч...")
        except:
            pass # Якщо супротивник заблокував бота
            
        execute_pvp_match(user_id, opponent_id, call.message.chat.id)
    else:
        # Додаємо себе в чергу
        global_pvp_queue.append(user_id)
        bot.send_message(call.message.chat.id, "🔍 Ви додані в глобальну чергу пошуку матчу...\nБот надішле сповіщення, як тільки знайдеться суперник.")

# --- РЕЖИМ 2: ВИКЛИК ПО @USERNAME ---
@bot.callback_query_handler(func=lambda call: call.data == "pvp_challenge")
def pvp_challenge_init(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    msg = bot.send_message(
        call.message.chat.id, 
        "Введіть `@username` гравця, якого хочете викликати на дуель:",
        parse_mode="Markdown",
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, process_pvp_challenge_username)

def process_pvp_challenge_username(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    
    target_uname = message.text.strip()
    challenger_id = message.from_user.id
    target_id = get_user_id_by_username(target_uname)
    
    if not target_id:
        bot.send_message(message.chat.id, "❌ Гравця з таким username не знайдено в базі бота.", reply_markup=create_main_menu(challenger_id))
        return
        
    if str(target_id) == str(challenger_id):
        bot.send_message(message.chat.id, "⚠️ Ви не можете викликати самі себе!", reply_markup=create_main_menu(challenger_id))
        return
        
    # Зберігаємо виклик
    pvp_challenges[str(target_id)] = challenger_id
    
    # Відправляємо запит цілі
    markup = types.InlineKeyboardMarkup()
    btn_accept = types.InlineKeyboardButton("✅ Прийняти", callback_data=f"accept_pvp_{challenger_id}")
    btn_decline = types.InlineKeyboardButton("❌ Відхилити", callback_data=f"decline_pvp_{challenger_id}")
    markup.add(btn_accept, btn_decline)
    
    try:
        challenger_nick = message.from_user.first_name
        bot.send_message(
            int(target_id), 
            f"⚔️ **ВИКЛИК НА ДУЕЛЬ!**\nГравець {challenger_nick} викликає вас на ПВП матч!",
            parse_mode="Markdown",
            reply_markup=markup
        )
        bot.send_message(message.chat.id, f"✅ Виклик надіслано гравцю {target_uname}. Очікуємо на його відповідь...", reply_markup=create_main_menu(challenger_id))
    except Exception as e:
        logger.error(f"Не вдалося надіслати виклик {target_id}: {e}")
        bot.send_message(message.chat.id, "❌ Не вдалося надіслати повідомлення гравцю. Можливо, він заблокував бота.", reply_markup=create_main_menu(challenger_id))

@bot.callback_query_handler(func=lambda call: call.data.startswith('accept_pvp_') or call.data.startswith('decline_pvp_'))
def handle_challenge_response(call):
    target_id = str(call.from_user.id)
    action = call.data.split('_')[0]
    challenger_id = int(call.data.split('_')[2])
    
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    if pvp_challenges.get(target_id) != challenger_id:
        bot.send_message(call.message.chat.id, "Цей виклик вже застарів або був скасований.")
        return
        
    del pvp_challenges[target_id] # Очищаємо запит
    
    if action == "decline":
        bot.send_message(call.message.chat.id, "Ви відхилили виклик.")
        try:
            bot.send_message(challenger_id, f"❌ Гравець {call.from_user.first_name} відхилив ваш виклик.")
        except:
            pass
    elif action == "accept":
        bot.send_message(call.message.chat.id, "⚔️ Ви прийняли виклик! Починаємо матч...")
        try:
            bot.send_message(challenger_id, f"⚔️ Гравець {call.from_user.first_name} прийняв виклик! Починаємо матч...")
        except:
            pass
        execute_pvp_match(challenger_id, call.from_user.id, call.message.chat.id)

# --- ЛОГІКА САМОГО МАТЧУ ТА БОЮ ---
def execute_pvp_match(player1_id, player2_id, chat_to_notify_initially):
    """
    Проводить матч між двома гравцями.
    Враховує базову силу + випадковий множник форми.
    """
    users_db = load_data('users')
    
    p1_nick = users_db.get(str(player1_id), {}).get('nick', f"Гравець {player1_id}")
    p2_nick = users_db.get(str(player2_id), {}).get('nick', f"Гравець {player2_id}")
    
    power1 = calculate_total_power(player1_id)
    power2 = calculate_total_power(player2_id)
    
    # Випадковий фактор (форма команди на сьогодні) від 80% до 120% міці
    luck1 = random.uniform(0.8, 1.2)
    luck2 = random.uniform(0.8, 1.2)
    
    final_score1 = int(power1 * luck1)
    final_score2 = int(power2 * luck2)
    
    # Визначаємо переможця
    if final_score1 > final_score2:
        winner_id, loser_id = str(player1_id), str(player2_id)
        winner_nick, loser_nick = p1_nick, p2_nick
        win_score, lose_score = final_score1, final_score2
    elif final_score2 > final_score1:
        winner_id, loser_id = str(player2_id), str(player1_id)
        winner_nick, loser_nick = p2_nick, p1_nick
        win_score, lose_score = final_score2, final_score1
    else:
        # Нічия
        draw_text = f"⚖️ **МАТЧ ЗАВЕРШЕНО НІЧИЄЮ!**\n\nКоманди {p1_nick} та {p2_nick} зіграли на рівних.\nСили: {final_score1} vs {final_score2}"
        try: bot.send_message(player1_id, draw_text, parse_mode="Markdown")
        except: pass
        try: bot.send_message(player2_id, draw_text, parse_mode="Markdown")
        except: pass
        return

    # Нагороди: Переможець отримує 2500 монет, той, хто програв, втрачає 500
    reward = 2500
    penalty = 500
    
    users_db[winner_id]['score'] = users_db[winner_id].get('score', 0) + reward
    users_db[loser_id]['score'] = max(0, users_db[loser_id].get('score', 0) - penalty)
    save_data(users_db, 'users')
    
    # Встановлюємо кулдауни (1 година), якщо вони не адміни
    class MockUser:
        def __init__(self, uid): self.id = int(uid)
        
    if not check_admin_permission(MockUser(winner_id)):
        pvp_cooldowns[int(winner_id)] = time.time()
    if not check_admin_permission(MockUser(loser_id)):
        pvp_cooldowns[int(loser_id)] = time.time()

    # Звіти про матч
    winner_report = (
        f"🏆 **ПЕРЕМОГА В ПВП!** 🏆\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Ви розгромили команду гравця {loser_nick}!\n\n"
        f"📊 **Ваш результат:** `{win_score}` (Базова міць: {max(power1, power2)})\n"
        f"📉 **Результат ворога:** `{lose_score}`\n\n"
        f"🎁 **Нагорода:** `+{reward}` монет!"
    )
    
    loser_report = (
        f"💀 **ПОРАЗКА В ПВП!** 💀\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Команда гравця {winner_nick} виявилася сильнішою.\n\n"
        f"📉 **Ваш результат:** `{lose_score}`\n"
        f"📊 **Результат ворога:** `{win_score}`\n\n"
        f"💔 **Штраф:** `-{penalty}` монет."
    )
    
    try: bot.send_message(int(winner_id), winner_report, parse_mode="Markdown")
    except Exception as e: logger.warning(f"Не зміг відправити звіт переможцю: {e}")
        
    try: bot.send_message(int(loser_id), loser_report, parse_mode="Markdown")
    except Exception as e: logger.warning(f"Не зміг відправити звіт переможеному: {e}")

# ==============================================================================
# [14] ЗАПУСК БОТА (ГОЛОВНИЙ ЦИКЛ)
# ==============================================================================

if __name__ == '__main__':
    logger.info("=====================================================")
    logger.info("СИМУЛЯТОР ФУТБОЛЬНИХ КАРТОК (ВЕРСІЯ 3.0) ЗАПУЩЕНО")
    logger.info("Всі системи ініціалізовано. Бот готовий до роботи.")
    logger.info("=====================================================")
    
    while True:
        try:
            # Запуск поллінгу (бота) у безперервному режимі
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as crash_error:
            logger.critical(f"КРИТИЧНА ПОМИЛКА З'ЄДНАННЯ З TELEGRAM API: {crash_error}")
            logger.info("Спроба перезапуску через 5 секунд...")
            time.sleep(5)
