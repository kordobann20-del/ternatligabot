# ==============================================================================
# СИМУЛЯТОР ФУТБОЛЬНЫХ КАРТОК - ЧАСТЬ 1 (ОСНОВНЫЕ СИСТЕМЫ И НАСТРОЙКИ)
# Версия без монет. Бесплатные паки (КД 30 минут) и Топ по Очкам.
# ==============================================================================

import telebot
from telebot import types
import json
import os
import time
import random
import logging
from datetime import datetime
import shutil

# ==============================================================================
# [1] НАСТРОЙКА ЛОГИРОВАНИЯ И КОНФИГУРАЦИЯ СЕРВЕРА
# ==============================================================================
# Настраиваем подробное логирование для отслеживания всех действий и ошибок.
# Это поможет находить баги в случае сбоев бота.

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] - %(message)s',
    handlers=[
        logging.FileHandler("bot_server.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Токен вашего бота (ЗАМЕНИТЕ НА СВОЙ ТОКЕН ОТ @BotFather)
BOT_TOKEN = "ВАШ_ТОКЕН_ЗДЕСЬ"
bot = telebot.TeleBot(BOT_TOKEN)

# Список ID администраторов (ЗАМЕНИТЕ НА ВАШ TELEGRAM ID)
ADMIN_IDS = [123456789, 987654321]

# Папка для хранения всех файлов базы данных
DB_DIR = "database"
BACKUP_DIR = "database/backups"

# Убеждаемся, что директории для баз данных существуют при запуске
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)
    logger.info(f"Создана директория для баз данных: {DB_DIR}")

if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)
    logger.info(f"Создана директория для резервных копий: {BACKUP_DIR}")

# Глобальные словари и списки для работы механик в реальном времени
global_pvp_queue = []       # Очередь игроков, ищущих случайный ПВП-матч
pvp_challenges = {}         # Словарь вызовов ПВП по username {target_id: challenger_id}
pvp_cooldowns = {}          # Отслеживание времени последнего ПВП {user_id: timestamp}
pack_cooldowns = {}         # Отслеживание времени открытия последнего пака {user_id: timestamp}

# ==============================================================================
# [2] ИГРОВЫЕ КОНСТАНТЫ И БАЛАНС
# ==============================================================================

# Характеристики редкости карточек
# chance - шанс выпадения в Gacha (в процентах)
# atk - базовая сила атаки карточки в ПВП
RARITY_STATS = {
    1: {"label": "Обычная",    "chance": 45, "atk": 10},
    2: {"label": "Необычная",  "chance": 30, "atk": 25},
    3: {"label": "Редкая",     "chance": 15, "atk": 50},
    4: {"label": "Эпическая",  "chance": 7,  "atk": 85},
    5: {"label": "Легендарная","chance": 3,  "atk": 150}
}

# Доступные позиции на футбольном поле и их расшифровка на русском
POSITIONS_RU = {
    "ВРТ": "Вратарь",
    "ЛЗ": "Левый защитник",
    "ЦЗ": "Центральный защитник",
    "ПЗ": "Правый защитник",
    "ЦОП": "Центр. опорный полузащитник",
    "ЦП": "Центральный полузащитник",
    "ЛП": "Левый полузащитник",
    "ПП": "Правый полузащитник",
    "ЦАП": "Центр. атакующий полузащитник",
    "ЛВ": "Левый вингер (нападающий)",
    "ПВ": "Правый вингер (нападающий)",
    "ФРВ": "Форвард (Центральный нападающий)"
}

# Настройки структуры команды игрока (7 слотов)
SQUAD_SLOTS = [
    {"index": 0, "code": "ФРВ", "label": "Форвард (ФРВ)"},
    {"index": 1, "code": "ЛВ",  "label": "Левый Вингер (ЛВ)"},
    {"index": 2, "code": "ПВ",  "label": "Правый Вингер (ПВ)"},
    {"index": 3, "code": "ЦП",  "label": "Центр. Полузащитник (ЦП)"},
    {"index": 4, "code": "ЛЗ",  "label": "Левый Защитник (ЛЗ)"},
    {"index": 5, "code": "ПЗ",  "label": "Правый Защитник (ПЗ)"},
    {"index": 6, "code": "ВРТ", "label": "Вратарь (ВРТ)"}
]

# Время перезарядки (в секундах)
PACK_COOLDOWN_TIME = 1800  # 30 минут
PVP_COOLDOWN_TIME = 3600   # 1 час (для ПВП, если нужно, можно изменить)

# ==============================================================================
# [3] БЕЗОПАСНАЯ РАБОТА С БАЗОЙ ДАННЫХ (JSON) И БЭКАПЫ
# ==============================================================================

def create_backup(filename):
    """Создает резервную копию файла базы данных перед его перезаписью."""
    filepath = os.path.join(DB_DIR, f"{filename}.json")
    if os.path.exists(filepath):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"{filename}_backup_{timestamp}.json")
        try:
            shutil.copy2(filepath, backup_path)
            backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith(f"{filename}_backup")])
            # Храним только 10 последних бэкапов для каждого файла, чтобы не засорять диск
            if len(backups) > 10:
                os.remove(os.path.join(BACKUP_DIR, backups[0]))
        except Exception as e:
            logger.error(f"Ошибка при создании бэкапа {filename}: {e}")

def load_data(filename):
    """
    Загружает данные из JSON файла.
    Если файл отсутствует или поврежден, возвращает пустую структуру.
    """
    filepath = os.path.join(DB_DIR, f"{filename}.json")
    if not os.path.exists(filepath):
        if filename == 'users': return {}
        if filename == 'cards': return []
        if filename == 'colls': return {}
        if filename == 'squads': return {}
        if filename == 'promos': return {}
        if filename == 'bans': return []
        return {}

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Файл {filename}.json поврежден! Ошибка: {e}")
        if filename == 'users': return {}
        if filename == 'cards': return []
        return {}
    except Exception as e:
        logger.error(f"Неизвестная ошибка при чтении {filename}: {e}")
        return {}

def save_data(data, filename):
    """
    Безопасно сохраняет данные в JSON файл.
    Сначала создает резервную копию старого файла.
    """
    create_backup(filename)
    filepath = os.path.join(DB_DIR, f"{filename}.json")
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении {filename}: {e}")
        return False

# ==============================================================================
# [4] ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И ПРОВЕРКИ ДОСТУПА
# ==============================================================================

def check_admin_permission(user):
    """Проверяет, является ли пользователь администратором."""
    return user.id in ADMIN_IDS

def check_ban_status(user):
    """
    Проверяет, не заблокирован ли пользователь.
    Возвращает True, если игрок в бане (и отправляет ему сообщение).
    """
    bans_db = load_data('bans')
    username = user.username.lower() if user.username else str(user.id)
    
    if str(user.id) in bans_db or username in bans_db:
        try:
            bot.send_message(
                user.id, 
                "⛔️ **ВАШ АККАУНТ ЗАБЛОКИРОВАН.**\n\nВы нарушили правила проекта, и доступ к боту закрыт.", 
                parse_mode="Markdown",
                reply_markup=types.ReplyKeyboardRemove()
            )
        except Exception:
            pass
        return True
    return False

def calculate_total_power(user_id):
    """
    Подсчитывает общую боевую мощь (силу) текущего состава игрока.
    Суммирует параметры 'atk' всех карточек, установленных в слоты.
    """
    squads_db = load_data('squads')
    my_squad = squads_db.get(str(user_id), [None] * 7)
    
    total_power = 0
    for card in my_squad:
        if card:
            stars = card.get('stars', 1)
            total_power += RARITY_STATS.get(stars, {}).get('atk', 0)
            
    return total_power

def get_user_id_by_username(username):
    """Ищет Telegram ID пользователя в базе по его @username."""
    target = username.replace("@", "").lower()
    users_db = load_data('users')
    
    for uid, data in users_db.items():
        if data.get('username', '').lower() == target:
            return uid
    return None

# ==============================================================================
# [5] ГЕНЕРАЦИЯ КЛАВИАТУР (ИНТЕРФЕЙС БОТА)
# ==============================================================================

def create_main_menu(user_id):
    """
    Создает главную клавиатуру пользователя.
    Адаптировано под систему без монет (с топом по очкам).
    """
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    btn_arena = types.KeyboardButton("🏟 ПВП Арена")
    btn_squad = types.KeyboardButton("📋 Состав")
    btn_coll = types.KeyboardButton("🗂 Коллекция")
    btn_gacha = types.KeyboardButton("🎰 Крутить карту")
    btn_profile = types.KeyboardButton("👤 Профиль")
    btn_top = types.KeyboardButton("🏆 Топ (Очки)") # Изменено с Топ монет на Топ очков
    btn_promo = types.KeyboardButton("🎟 Промокод")
    
    markup.add(btn_arena)
    markup.add(btn_gacha, btn_coll)
    markup.add(btn_squad, btn_profile)
    markup.add(btn_top, btn_promo)
    
    # Кнопка для админов
    if user_id in ADMIN_IDS:
        markup.add(types.KeyboardButton("🛠 Админ-панель"))
        
    return markup

def create_admin_menu():
    """Создает клавиатуру для администратора."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("➕ Добавить карту"),
        types.KeyboardButton("📝 Изменить карту"),
        types.KeyboardButton("🗑 Удалить карту"),
        types.KeyboardButton("🎟 +Промокод"),
        types.KeyboardButton("🗑 Удалить промокод"),
        types.KeyboardButton("🚫 Забанить"),
        types.KeyboardButton("✅ Разбанить"),
        types.KeyboardButton("🧨 Обнулить бота"),
        types.KeyboardButton("🏠 Назад в меню")
    )
    return markup

def create_cancel_menu():
    """Создает кнопку отмены для возврата в меню во время ввода данных."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("❌ Отмена"))
    return markup

# ==============================================================================
# [6] РЕГИСТРАЦИЯ И СТАРТ (/start)
# ==============================================================================

@bot.message_handler(commands=['start'])
def start_command(message):
    """
    Обработчик команды /start.
    Регистрирует новых пользователей, обрабатывает реферальные ссылки.
    Монет больше нет, счетчик начинается с 0 очков рейтинга.
    """
    if check_ban_status(message.from_user): return
    
    user_id = str(message.from_user.id)
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "Менеджер"
    
    users_db = load_data('users')
    args = message.text.split()
    inviter_id = args[1] if len(args) > 1 else None

    if user_id not in users_db:
        # Регистрация нового игрока (score теперь означает ОЧКИ РЕЙТИНГА, а не монеты)
        users_db[user_id] = {
            "nick": first_name,
            "username": username,
            "score": 0,             # Стартовые очки рейтинга
            "refs": 0,              # Количество приглашенных друзей
            "used_promos": [],      # Список использованных промокодов
            "registration_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Логика обработки пригласившего (рефовода)
        if inviter_id and inviter_id != user_id and inviter_id in users_db:
            # Награда пригласившему (например, бонусные очки рейтинга)
            users_db[inviter_id]['refs'] = users_db[inviter_id].get('refs', 0) + 1
            users_db[inviter_id]['score'] = users_db[inviter_id].get('score', 0) + 50
            
            try:
                bot.send_message(
                    int(inviter_id), 
                    f"🎉 По вашей ссылке зарегистрировался новый игрок: **{first_name}**!\n"
                    f"🎁 Вы получаете: `+50 очков рейтинга`!",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление рефоводу {inviter_id}: {e}")
                
        save_data(users_db, 'users')
        logger.info(f"Новый пользователь зарегистрирован: {first_name} (ID: {user_id})")
        
        welcome_text = (
            f"👋 **Добро пожаловать в Симулятор Футбольных Карток, {first_name}!**\n\n"
            "Здесь ты можешь стать настоящим менеджером:\n"
            "⚽️ **Крутить карту:** получай новых игроков каждые 30 минут абсолютно бесплатно!\n"
            "📋 **Состав:** собирай непобедимую команду из 7 карточек.\n"
            "🏟 **ПВП Арена:** сражайся с другими игроками и зарабатывай **очки рейтинга**, "
            "чтобы подняться в глобальном топе!\n\n"
            "Используй кнопки ниже, чтобы начать игру!"
        )
    else:
        # Обновляем имя и username на случай, если игрок их сменил
        users_db[user_id]['nick'] = first_name
        users_db[user_id]['username'] = username
        save_data(users_db, 'users')
        
        welcome_text = f"С возвращением, **{first_name}**! Твоя команда ждет тебя. Выбирай действие в меню:"

    # Отправляем приветственное сообщение и показываем меню
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        parse_mode="Markdown",
        reply_markup=create_main_menu(message.from_user.id)
    )

@bot.message_handler(commands=['ref'])
def ref_command(message):
    """
    Генерирует уникальную реферальную ссылку для игрока.
    """
    if check_ban_status(message.from_user): return
    
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"
    
    text = (
        "🔗 **ВАША РЕФЕРАЛЬНАЯ ССЫЛКА**\n\n"
        f"`{ref_link}`\n\n"
        "Отправьте эту ссылку друзьям!\n"
        "За каждого нового игрока, который запустит бота по вашей ссылке, вы получите:\n"
        "🏆 `+50 очков рейтинга` для продвижения в топе!"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- КОНЕЦ ЧАСТИ 1 ---

# ==============================================================================
# [7] АДМИН-ПАНЕЛЬ И УПРАВЛЕНИЕ КОНТЕНТОМ (БЕЗ МОНЕТ)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🏠 Назад в меню")
def back_to_main_menu(message):
    """
    Универсальная функция возврата в главное меню.
    Сбрасывает все текущие шаги и очищает контекст диалога.
    """
    if check_ban_status(message.from_user): 
        return
        
    bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
    bot.send_message(
        message.chat.id, 
        "Вы вернулись в главное меню.", 
        reply_markup=create_main_menu(message.from_user.id)
    )

@bot.message_handler(func=lambda m: m.text == "🛠 Админ-панель")
def admin_panel_open(message):
    """
    Открывает панель администратора и генерирует сводку по серверу.
    """
    if check_ban_status(message.from_user): 
        return
        
    if not check_admin_permission(message.from_user):
        bot.send_message(
            message.chat.id, 
            "⛔️ Ошибка доступа: Ваш ID не найден в списке администраторов."
        )
        return

    # Генерация статистики сервера
    users_db = load_data('users')
    cards_db = load_data('cards')
    promos_db = load_data('promos')
    bans_db = load_data('bans')
    
    total_users = len(users_db)
    total_cards = len(cards_db)
    total_promos = len(promos_db)
    total_bans = len(bans_db)
    
    total_rating_points = sum(u.get('score', 0) for u in users_db.values())
    
    admin_welcome_text = (
        "🔐 **ПАНЕЛЬ УПРАВЛЕНИЯ СЕРВЕРОМ**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 **Глобальная статистика:**\n"
        f"👥 Зарегистрировано игроков: `{total_users}`\n"
        f"🗂 Карточек в базе: `{total_cards}`\n"
        f"🎟 Активных промокодов: `{total_promos}`\n"
        f"🚫 Пользователей в бане: `{total_bans}`\n"
        f"🏆 Всего очков рейтинга в игре: `{total_rating_points}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Выберите действие на клавиатуре ниже:"
    )
    
    bot.send_message(
        message.chat.id, 
        admin_welcome_text, 
        parse_mode="Markdown",
        reply_markup=create_admin_menu()
    )

# ------------------------------------------------------------------------------
# 7.1 СИСТЕМА ДОБАВЛЕНИЯ КАРТОЧЕК
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "➕ Добавить карту")
def admin_add_card_start(message):
    if not check_admin_permission(message.from_user): 
        return
        
    msg = bot.send_message(
        message.chat.id, 
        "📝 **ШАГ 1/4: Имя футболиста**\n\n"
        "Введите полное имя игрока (например, Lionel Messi или Mykhailo Mudryk):", 
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
            "⚠️ Ошибка: Имя должно содержать от 2 до 50 символов. Попробуйте еще раз:"
        )
        bot.register_next_step_handler(msg, process_card_name_add)
        return
        
    msg = bot.send_message(
        message.chat.id, 
        f"📝 **ШАГ 2/4: Редкость**\n\n"
        f"Выбранное имя: {name}\n"
        "Введите цифру от 1 до 5, где:\n"
        "1 - Обычная (самая слабая)\n"
        "2 - Необычная\n"
        "3 - Редкая\n"
        "4 - Эпическая\n"
        "5 - Легендарная (самая сильная)",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_card_rarity_add, name)

def process_card_rarity_add(message, name):
    if message.text == "❌ Отмена": 
        return back_to_main_menu(message)
        
    try:
        rarity = int(message.text.strip())
        if rarity not in RARITY_STATS:
            raise ValueError("Редкость вне допустимого диапазона.")
    except ValueError as e:
        logger.warning(f"Админ ошибся при вводе редкости: {e}")
        msg = bot.send_message(
            message.chat.id, 
            "⚠️ Ошибка! Введите только одну цифру от 1 до 5:"
        )
        bot.register_next_step_handler(msg, process_card_rarity_add, name)
        return

    positions_list = "\n".join([f"🔸 {k} — {v}" for k, v in POSITIONS_RU.items()])
    msg = bot.send_message(
        message.chat.id, 
        f"📝 **ШАГ 3/4: Позиция на поле**\n\n"
        f"Выберите одну из доступных позиций и введите ее код (например, ВРТ или ЦЗ):\n\n"
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
            "⚠️ Неизвестная позиция. Введите точный код из предложенных (например, ЛЗ):"
        )
        bot.register_next_step_handler(msg, process_card_pos_add, name, rarity)
        return

    msg = bot.send_message(
        message.chat.id, 
        "📝 **ШАГ 4/4: Фотография**\n\n"
        "Теперь отправьте **картинку** (фото) футболиста прямо в этот чат.\n"
        "Бот автоматически загрузит ее на серверы Telegram и сохранит.", 
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_card_photo_add, name, rarity, pos)

def process_card_photo_add(message, name, rarity, pos):
    if message.text == "❌ Отмена": 
        return back_to_main_menu(message)
    
    if not message.photo:
        msg = bot.send_message(
            message.chat.id, 
            "⚠️ Это не фотография! Пожалуйста, прикрепите изображение как фото:"
        )
        bot.register_next_step_handler(msg, process_card_photo_add, name, rarity, pos)
        return

    try:
        photo_file_id = message.photo[-1].file_id
        cards_db = load_data('cards')
        
        # Генерация уникального ID для новой карточки
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
                f"✅ **КАРТОЧКА УСПЕШНО ДОБАВЛЕНА!**\n\n"
                f"🆔 ID карточки: `{new_id}`\n"
                f"👤 Имя: **{name}**\n"
                f"⭐ Редкость: **{rarity}** ({RARITY_STATS[rarity]['label']})\n"
                f"🎯 Позиция: **{pos}** ({POSITIONS_RU[pos]})\n"
                f"⚔️ Сила атаки (ПВП): `{RARITY_STATS[rarity]['atk']}`"
            )
            bot.send_photo(
                message.chat.id, 
                photo_file_id, 
                caption=card_info,
                parse_mode="Markdown",
                reply_markup=create_admin_menu()
            )
            logger.info(f"[АДМИН] Карточка '{name}' (ID {new_id}) успешно создана.")
        else:
            bot.send_message(message.chat.id, "❌ Критическая ошибка при сохранении базы данных.", reply_markup=create_admin_menu())
    except Exception as e:
        logger.error(f"Ошибка при обработке фотографии карточки: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при загрузке фотографии.", reply_markup=create_admin_menu())

# ------------------------------------------------------------------------------
# 7.2 СИСТЕМА УДАЛЕНИЯ КАРТОЧЕК
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "🗑 Удалить карту")
def admin_delete_card_start(message):
    if not check_admin_permission(message.from_user): return
    
    msg = bot.send_message(
        message.chat.id, 
        "🗑 **УДАЛЕНИЕ КАРТОЧКИ**\n\n"
        "Введите числовой ID карточки, которую вы хотите навсегда удалить из игры:", 
        parse_mode="Markdown",
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, process_card_delete)

def process_card_delete(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    
    try:
        target_id = int(message.text.strip())
    except ValueError:
        msg = bot.send_message(message.chat.id, "⚠️ ID должен быть числом. Введите ID еще раз:")
        bot.register_next_step_handler(msg, process_card_delete)
        return
        
    cards_db = load_data('cards')
    card_index = -1
    card_name = ""
    
    for i, card in enumerate(cards_db):
        if card.get('id') == target_id:
            card_index = i
            card_name = card.get('name', 'Неизвестно')
            break
            
    if card_index != -1:
        del cards_db[card_index]
        save_data(cards_db, 'cards')
        
        bot.send_message(
            message.chat.id, 
            f"✅ Карточка **{card_name}** (ID: `{target_id}`) была успешно удалена из базы.",
            parse_mode="Markdown",
            reply_markup=create_admin_menu()
        )
        logger.warning(f"[АДМИН] Удалена карточка ID {target_id} ({card_name}).")
    else:
        bot.send_message(message.chat.id, f"❌ Карточка с ID `{target_id}` не найдена.", parse_mode="Markdown", reply_markup=create_admin_menu())

# ------------------------------------------------------------------------------
# 7.3 СИСТЕМА РЕДАКТИРОВАНИЯ КАРТОЧЕК
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "📝 Изменить карту")
def admin_edit_card_start(message):
    if not check_admin_permission(message.from_user): return
    msg = bot.send_message(message.chat.id, "Введите ID карточки, которую нужно отредактировать:", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, process_card_edit_find)

def process_card_edit_find(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    
    try:
        target_id = int(message.text.strip())
    except ValueError:
        msg = bot.send_message(message.chat.id, "⚠️ Ошибка: Введите число. Попробуйте еще раз:")
        bot.register_next_step_handler(msg, process_card_edit_find)
        return
        
    cards_db = load_data('cards')
    card_found = None
    
    for card in cards_db:
        if card.get('id') == target_id:
            card_found = card
            break
            
    if not card_found:
        bot.send_message(message.chat.id, f"❌ Карточка с ID {target_id} не найдена.", reply_markup=create_admin_menu())
        return
        
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("✏️ Имя"), 
        types.KeyboardButton("✏️ Редкость"),
        types.KeyboardButton("✏️ Позицию"),
        types.KeyboardButton("🖼 Фото"),
        types.KeyboardButton("❌ Отмена")
    )
    
    msg = bot.send_message(
        message.chat.id, 
        f"Карточка найдена: **{card_found.get('name')}** (⭐ {card_found.get('stars')})\nЧто именно вы хотите изменить?",
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_card_edit_field, target_id)

def process_card_edit_field(message, target_id):
    choice = message.text
    if choice == "❌ Отмена": return back_to_main_menu(message)
    
    if choice == "✏️ Имя":
        msg = bot.send_message(message.chat.id, "Введите новое имя:", reply_markup=create_cancel_menu())
        bot.register_next_step_handler(msg, apply_card_edit, target_id, 'name')
    elif choice == "✏️ Редкость":
        msg = bot.send_message(message.chat.id, "Введите новую редкость (1-5):", reply_markup=create_cancel_menu())
        bot.register_next_step_handler(msg, apply_card_edit, target_id, 'stars')
    elif choice == "✏️ Позицию":
        msg = bot.send_message(message.chat.id, "Введите новую позицию (напр., ЛВ):", reply_markup=create_cancel_menu())
        bot.register_next_step_handler(msg, apply_card_edit, target_id, 'pos')
    elif choice == "🖼 Фото":
        msg = bot.send_message(message.chat.id, "Отправьте новое фото:", reply_markup=create_cancel_menu())
        bot.register_next_step_handler(msg, apply_card_edit, target_id, 'photo')
    else:
        bot.send_message(message.chat.id, "Неизвестное действие.", reply_markup=create_admin_menu())

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
                    bot.send_message(message.chat.id, "⚠️ Неверная редкость.", reply_markup=create_admin_menu())
                    return
            elif field == 'pos':
                pos = message.text.strip().upper()
                if pos not in POSITIONS_RU:
                    bot.send_message(message.chat.id, "⚠️ Неверная позиция.", reply_markup=create_admin_menu())
                    return
                card['pos'] = pos
            elif field == 'photo':
                if not message.photo:
                    bot.send_message(message.chat.id, "⚠️ Нужно прикрепить фото.", reply_markup=create_admin_menu())
                    return
                card['photo'] = message.photo[-1].file_id
                
            save_data(cards_db, 'cards')
            bot.send_message(message.chat.id, f"✅ Карточка успешно обновлена!", reply_markup=create_admin_menu())
            return

# ------------------------------------------------------------------------------
# 7.4 УПРАВЛЕНИЕ ПРОМОКОДАМИ (НА ОЧКИ РЕЙТИНГА)
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "🎟 +Промокод")
def admin_add_promo_start(message):
    if not check_admin_permission(message.from_user): return
    msg = bot.send_message(
        message.chat.id, 
        "Введите текст промокода (например, FREEPOINTS2026):", 
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, process_promo_code_add)

def process_promo_code_add(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    code = message.text.strip().upper()
    msg = bot.send_message(message.chat.id, f"Сколько **очков рейтинга** даст промокод {code}?")
    bot.register_next_step_handler(msg, process_promo_points_add, code)

def process_promo_points_add(message, code):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    try:
        points = int(message.text.strip())
    except:
        msg = bot.send_message(message.chat.id, "Введите число!")
        bot.register_next_step_handler(msg, process_promo_points_add, code)
        return
        
    msg = bot.send_message(message.chat.id, "Сколько раз его можно активировать в сумме всеми игроками? (Введите 0 для безлимита):")
    bot.register_next_step_handler(msg, process_promo_limit_add, code, points)

def process_promo_limit_add(message, code, points):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    try:
        limit = int(message.text.strip())
    except:
        msg = bot.send_message(message.chat.id, "Введите число!")
        bot.register_next_step_handler(msg, process_promo_limit_add, code, points)
        return
        
    promos_db = load_data('promos')
    promos_db[code] = {
        "points": points,
        "limit": limit,
        "activations": 0
    }
    save_data(promos_db, 'promos')
    
    bot.send_message(
        message.chat.id, 
        f"✅ Промокод `{code}` создан!\n"
        f"🏆 Очков рейтинга: {points}\n"
        f"🔄 Лимит активаций: {'Безлимит' if limit == 0 else limit}",
        parse_mode="Markdown",
        reply_markup=create_admin_menu()
    )

@bot.message_handler(func=lambda m: m.text == "🗑 Удалить промокод")
def admin_del_promo_start(message):
    if not check_admin_permission(message.from_user): return
    promos_db = load_data('promos')
    if not promos_db:
        bot.send_message(message.chat.id, "Активных промокодов нет.")
        return
        
    promo_list = "\n".join(list(promos_db.keys()))
    msg = bot.send_message(message.chat.id, f"Список промокодов:\n{promo_list}\n\nВведите код для удаления:", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, process_promo_del)

def process_promo_del(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    code = message.text.strip().upper()
    promos_db = load_data('promos')
    if code in promos_db:
        del promos_db[code]
        save_data(promos_db, 'promos')
        bot.send_message(message.chat.id, f"✅ Промокод {code} удален.", reply_markup=create_admin_menu())
    else:
        bot.send_message(message.chat.id, "❌ Такого промокоду не существует.", reply_markup=create_admin_menu())

# ------------------------------------------------------------------------------
# 7.5 БЛОКИРОВКА И РАЗБЛОКИРОВКА, ВАЙП
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "🚫 Забанить")
def admin_ban_start(message):
    if not check_admin_permission(message.from_user): return
    msg = bot.send_message(message.chat.id, "Введите Telegram ID или @username нарушителя:", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, process_ban_user)

def process_ban_user(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    target = message.text.strip().lower().replace("@", "")
    bans_db = load_data('bans')
    
    if target not in bans_db:
        bans_db.append(target)
        save_data(bans_db, 'bans')
        bot.send_message(message.chat.id, f"✅ Игрок `{target}` заблокирован.", parse_mode="Markdown", reply_markup=create_admin_menu())
    else:
        bot.send_message(message.chat.id, "⚠️ Этот игрок уже в бане.", reply_markup=create_admin_menu())

@bot.message_handler(func=lambda m: m.text == "✅ Разбанить")
def admin_unban_start(message):
    if not check_admin_permission(message.from_user): return
    msg = bot.send_message(message.chat.id, "Введите ID или @username для разбана:", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, process_unban_user)

def process_unban_user(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    target = message.text.strip().lower().replace("@", "")
    bans_db = load_data('bans')
    
    if target in bans_db:
        bans_db.remove(target)
        save_data(bans_db, 'bans')
        bot.send_message(message.chat.id, f"✅ Игрок `{target}` разблокирован.", parse_mode="Markdown", reply_markup=create_admin_menu())
    else:
        bot.send_message(message.chat.id, "⚠️ Этого игрока нет в черном списке.", reply_markup=create_admin_menu())

@bot.message_handler(func=lambda m: m.text == "🧨 Обнулить бота")
def admin_reset_start(message):
    if not check_admin_permission(message.from_user): return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("⚠️ ПОДТВЕРЖДАЮ ВАЙП"), types.KeyboardButton("❌ Отмена"))
    msg = bot.send_message(
        message.chat.id, 
        "‼️ **ВНИМАНИЕ!** ‼️\nЭто удалит ВСЕХ пользователей, их очки, составы и коллекции. Карточки останутся.\nВы уверены?", 
        parse_mode="Markdown", 
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_reset_confirm)

def process_reset_confirm(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    if message.text == "⚠️ ПОДТВЕРЖДАЮ ВАЙП":
        save_data({}, 'users')
        save_data({}, 'colls')
        save_data({}, 'squads')
        bot.send_message(message.chat.id, "🧨 **БАЗА ДАННЫХ ОЧИЩЕНА.** Игроки, очки и составы удалены.", parse_mode="Markdown", reply_markup=create_admin_menu())
    else:
        back_to_main_menu(message)

# ==============================================================================
# [8] ПРОФИЛЬ, ТОП ИГРОКОВ (ПО ОЧКАМ) И АКТИВАЦИЯ ПРОМОКОДОВ
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile_handler(message):
    """Генерирует детальную карточку профиля пользователя со статистикой."""
    if check_ban_status(message.from_user): return
    
    user_id = str(message.from_user.id)
    users_db = load_data('users')
    
    if user_id not in users_db:
        bot.send_message(message.chat.id, "Ваш профиль еще не создан. Нажмите /start", reply_markup=types.ReplyKeyboardRemove())
        return
        
    user_data = users_db[user_id]
    nick = user_data.get('nick', 'Менеджер')
    points = user_data.get('score', 0)
    refs = user_data.get('refs', 0)
    
    colls_db = load_data('colls')
    my_cards = colls_db.get(user_id, [])
    
    total_power = calculate_total_power(message.from_user.id)
    
    # Расчет статуса готовности открытия пака
    last_pack_time = pack_cooldowns.get(message.from_user.id, 0)
    time_since_pack = time.time() - last_pack_time
    
    if time_since_pack >= PACK_COOLDOWN_TIME:
        pack_status = "✅ Готов к открытию!"
    else:
        mins_left = int((PACK_COOLDOWN_TIME - time_since_pack) // 60)
        pack_status = f"⏳ Будет доступен через {mins_left} мин."
                
    profile_text = (
        f"👤 **КАРТОЧКА МЕНЕДЖЕРА:** {nick}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 **Очки рейтинга:** `{points}`\n"
        f"👥 **Приглашено друзей:** `{refs}`\n"
        f"📦 **Бесплатный пак:** {pack_status}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡️ **Боевая мощь состава (ПВП):** `{total_power}`\n"
        f"🗂 **Собрано карточек:** `{len(my_cards)}`\n"
    )
    bot.send_message(message.chat.id, profile_text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🏆 Топ (Очки)")
def top_score_handler(message):
    """Выводит глобальный рейтинг лучших игроков по количеству ОЧКОВ."""
    if check_ban_status(message.from_user): return
    
    users_db = load_data('users')
    if not users_db:
        bot.send_message(message.chat.id, "Сервер пока пуст. Станьте первым!")
        return
        
    # Сортировка словаря по значению 'score' (очки) по убыванию
    sorted_users = sorted(
        users_db.items(), 
        key=lambda item: item[1].get('score', 0), 
        reverse=True
    )
    
    top_text = "🏆 **ГЛОБАЛЬНЫЙ РЕЙТИНГ (ОЧКИ)** 🏆\n\n"
    
    for i, (uid, udata) in enumerate(sorted_users[:15]):  # Топ-15
        if i == 0: medal = "🥇"
        elif i == 1: medal = "🥈"
        elif i == 2: medal = "🥉"
        else: medal = f"`{i+1}.`"
        
        nick = udata.get('nick', 'Unknown')
        if len(nick) > 15: nick = nick[:12] + "..."
        
        points = udata.get('score', 0)
        top_text += f"{medal} {nick} ➖ `{points} очков`\n"
        
    top_text += "\n*Сражайтесь в ПВП, чтобы заработать очки и подняться выше!*"
    bot.send_message(message.chat.id, top_text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎟 Промокод")
def promo_handler(message):
    """Обработчик для активации промокодов пользователями."""
    if check_ban_status(message.from_user): return
    msg = bot.send_message(
        message.chat.id, 
        "🎁 **АКТИВАЦИЯ ПРОМОКОДА**\n\nВведите ваш секретный код ниже:", 
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
        bot.send_message(message.chat.id, "❌ Неверный промокод.", reply_markup=create_main_menu(message.from_user.id))
        return
        
    user_profile = users_db.get(user_id, {})
    used_promos = user_profile.get('used_promos', [])
    
    if code in used_promos:
        bot.send_message(message.chat.id, "⚠️ Вы уже активировали этот промокод ранее!", reply_markup=create_main_menu(message.from_user.id))
        return
        
    promo_data = promos_db[code]
    activations = promo_data.get('activations', 0)
    limit = promo_data.get('limit', 0)
    
    if limit > 0 and activations >= limit:
        bot.send_message(message.chat.id, "❌ Лимит активаций этого промокода исчерпан.", reply_markup=create_main_menu(message.from_user.id))
        return
        
    reward_points = promo_data.get('points', 0)
    users_db[user_id]['score'] = users_db[user_id].get('score', 0) + reward_points
    
    if 'used_promos' not in users_db[user_id]:
        users_db[user_id]['used_promos'] = []
    users_db[user_id]['used_promos'].append(code)
    
    promos_db[code]['activations'] = activations + 1
    
    save_data(users_db, 'users')
    save_data(promos_db, 'promos')
    
    bot.send_message(
        message.chat.id, 
        f"✅ **УСПЕХ! ПРОМОКОД АКТИВИРОВАН!**\n\nВы получили: `+{reward_points} очков рейтинга`!", 
        parse_mode="Markdown", 
        reply_markup=create_main_menu(message.from_user.id)
    )

# ==============================================================================
# [9] СИСТЕМА GACHA (ОТКРЫТИЕ ПАКОВ С КУЛДАУНОМ 30 МИНУТ)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🎰 Крутить карту")
def gacha_handler(message):
    """
    Выдает случайную карточку игроку. 
    Пак полностью бесплатный, но имеет кулдаун 30 минут.
    """
    if check_ban_status(message.from_user): return
    
    user_id = message.from_user.id
    current_time = time.time()
    
    # Проверяем кулдаун (время с момента последнего открытия)
    last_opened = pack_cooldowns.get(user_id, 0)
    time_passed = current_time - last_opened
    
    if time_passed < PACK_COOLDOWN_TIME:
        # Если время еще не прошло, считаем остаток
        time_left = int(PACK_COOLDOWN_TIME - time_passed)
        minutes = time_left // 60
        seconds = time_left % 60
        bot.send_message(
            message.chat.id,
            f"⏳ **Пак еще не готов!**\n\n"
            f"Бесплатная карточка будет доступна через `{minutes} мин. {seconds} сек.`",
            parse_mode="Markdown"
        )
        return

    cards_db = load_data('cards')
    if not cards_db:
        bot.send_message(message.chat.id, "В базе пока нет карточек! Администратор должен их добавить.")
        return

    # Обновляем время последнего открытия (ставим кулдаун)
    pack_cooldowns[user_id] = current_time

    bot.send_message(message.chat.id, "🎲 Открываем пак... Посмотрим, кто вам выпадет!")
    time.sleep(1.5)  # Небольшая задержка для интриги

    # Логика выпадения (Гача)
    rand_val = random.uniform(0, 100)
    cumulative = 0
    selected_rarity = 1

    # Определяем редкость на основе шансов из RARITY_STATS
    for rarity, data in RARITY_STATS.items():
        cumulative += data['chance']
        if rand_val <= cumulative:
            selected_rarity = rarity
            break

    # Фильтруем карты из базы по выпавшей редкости
    available_cards = [c for c in cards_db if c.get('stars') == selected_rarity]
    
    # Если карт такой редкости нет в базе, берем вообще любую случайную
    if not available_cards:
        available_cards = cards_db

    pulled_card = random.choice(available_cards)
    
    # Сохраняем карту в коллекцию игрока
    user_id_str = str(user_id)
    colls_db = load_data('colls')
    
    if user_id_str not in colls_db:
        colls_db[user_id_str] = []
        
    # Добавляем уникальный идентификатор (uuid), чтобы можно было иметь дубликаты
    new_card_entry = pulled_card.copy()
    new_card_entry['uid'] = f"{pulled_card['id']}_{int(time.time()*1000)}"
    colls_db[user_id_str].append(new_card_entry)
    
    save_data(colls_db, 'colls')

    # Отправляем результат игроку
    rarity_label = RARITY_STATS[pulled_card['stars']]['label']
    stars_str = "⭐" * pulled_card['stars']
    
    caption = (
        f"🎉 **ПОЗДРАВЛЯЕМ! ВАМ ВЫПАЛА НОВАЯ КАРТОЧКА!** 🎉\n\n"
        f"👤 Имя: **{pulled_card['name']}**\n"
        f"🎯 Позиция: **{pulled_card['pos']}**\n"
        f"✨ Редкость: {stars_str} ({rarity_label})\n"
        f"⚔️ Сила атаки: `{RARITY_STATS[pulled_card['stars']]['atk']}`\n\n"
        f"Следующий пак будет доступен через 30 минут!"
    )
    
    if pulled_card.get('photo'):
        bot.send_photo(message.chat.id, pulled_card['photo'], caption=caption, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, caption, parse_mode="Markdown")

# ==============================================================================
# [10] КОЛЛЕКЦИЯ ИГРОКА
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🗂 Коллекция")
def collection_handler(message):
    """Показывает список всех карточек, которые есть у игрока."""
    if check_ban_status(message.from_user): return
    
    user_id_str = str(message.from_user.id)
    colls_db = load_data('colls')
    my_cards = colls_db.get(user_id_str, [])
    
    if not my_cards:
        bot.send_message(
            message.chat.id, 
            "📭 Ваша коллекция пуста.\nОткройте пак в меню '🎰 Крутить карту', чтобы получить первых игроков!"
        )
        return
        
    # Группируем карты по редкости для красивого отображения
    my_cards.sort(key=lambda x: x.get('stars', 1), reverse=True)
    
    text = f"🗂 **ВАША КОЛЛЕКЦИЯ ({len(my_cards)} шт.)**\n\n"
    
    # Выводим до 30 карт, чтобы не превысить лимит сообщения Telegram
    display_limit = 30
    for i, card in enumerate(my_cards[:display_limit]):
        stars = "⭐" * card['stars']
        text += f"`{i+1}.` {card['name']} | {card['pos']} | {stars} (ПВП: {RARITY_STATS[card['stars']]['atk']})\n"
        
    if len(my_cards) > display_limit:
        text += f"\n*...и еще {len(my_cards) - display_limit} карточек.*"
        
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ==============================================================================
# [11] УПРАВЛЕНИЕ СОСТАВОМ (7 СЛОТОВ)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "📋 Состав")
def squad_menu_handler(message):
    """Показывает текущий состав игрока и меню для его редактирования."""
    if check_ban_status(message.from_user): return
    show_squad(message.chat.id, message.from_user.id)

def show_squad(chat_id, user_id):
    user_id_str = str(user_id)
    squads_db = load_data('squads')
    
    # Если состава нет, создаем пустой из 7 слотов
    if user_id_str not in squads_db:
        squads_db[user_id_str] = [None] * 7
        save_data(squads_db, 'squads')
        
    my_squad = squads_db[user_id_str]
    total_atk = calculate_total_power(user_id)
    
    text = f"📋 **ВАШ СТАРТОВЫЙ СОСТАВ**\n⚔️ Общая сила команды: `{total_atk}`\n\n"
    
    for slot in SQUAD_SLOTS:
        idx = slot['index']
        card = my_squad[idx]
        
        if card:
            stars = "⭐" * card['stars']
            text += f"*{slot['label']}:*\n✅ {card['name']} | {stars} | Сила: {RARITY_STATS[card['stars']]['atk']}\n\n"
        else:
            text += f"*{slot['label']}:*\n❌ Слот пуст\n\n"
            
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🔄 Заменить игрока"),
        types.KeyboardButton("🏠 Назад в меню")
    )
    
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🔄 Заменить игрока")
def change_squad_start(message):
    if check_ban_status(message.from_user): return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for slot in SQUAD_SLOTS:
        markup.add(types.KeyboardButton(f"Слот {slot['index'] + 1}: {slot['code']}"))
    markup.add(types.KeyboardButton("❌ Отмена"))
    
    msg = bot.send_message(
        message.chat.id, 
        "Выберите слот, в который хотите поставить новую карточку:", 
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_squad_slot_select)

def process_squad_slot_select(message):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    
    # Парсим выбранный слот
    try:
        slot_text = message.text.split(":")[0]  # "Слот X"
        slot_num = int(slot_text.replace("Слот ", "").strip()) - 1
        
        selected_slot_config = None
        for s in SQUAD_SLOTS:
            if s['index'] == slot_num:
                selected_slot_config = s
                break
                
        if not selected_slot_config: raise ValueError
    except:
        bot.send_message(message.chat.id, "❌ Неверный выбор слота.", reply_markup=create_main_menu(message.from_user.id))
        return

    required_pos = selected_slot_config['code']
    user_id_str = str(message.from_user.id)
    colls_db = load_data('colls')
    my_cards = colls_db.get(user_id_str, [])
    
    # Ищем карты в коллекции, которые подходят на эту позицию
    suitable_cards = [c for c in my_cards if c.get('pos') == required_pos]
    
    if not suitable_cards:
        bot.send_message(
            message.chat.id, 
            f"⚠️ У вас в коллекции нет карточек для позиции **{required_pos}** ({POSITIONS_RU.get(required_pos)}).",
            parse_mode="Markdown",
            reply_markup=create_main_menu(message.from_user.id)
        )
        return
        
    text = f"Позиция: **{required_pos}**. Подходящие игроки в коллекции:\n\n"
    for i, c in enumerate(suitable_cards):
        text += f"`{i+1}.` {c['name']} (⭐ {c['stars']}) - Сила: {RARITY_STATS[c['stars']]['atk']}\n"
        
    text += "\nВведите номер игрока из списка выше, чтобы поставить его в состав:"
    
    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, process_squad_card_equip, slot_num, suitable_cards)

def process_squad_card_equip(message, slot_num, suitable_cards):
    if message.text == "❌ Отмена": return back_to_main_menu(message)
    
    try:
        choice_idx = int(message.text.strip()) - 1
        if choice_idx < 0 or choice_idx >= len(suitable_cards):
            raise ValueError
    except:
        msg = bot.send_message(message.chat.id, "⚠️ Пожалуйста, введите корректный номер из списка:")
        bot.register_next_step_handler(msg, process_squad_card_equip, slot_num, suitable_cards)
        return
        
    chosen_card = suitable_cards[choice_idx]
    user_id_str = str(message.from_user.id)
    
    squads_db = load_data('squads')
    if user_id_str not in squads_db:
        squads_db[user_id_str] = [None] * 7
        
    # Проверка: если этот игрок уже стоит в другом слоте (по uid)
    for i, existing_card in enumerate(squads_db[user_id_str]):
        if existing_card and existing_card.get('uid') == chosen_card.get('uid') and i != slot_num:
            squads_db[user_id_str][i] = None # Убираем из старого слота
            
    # Ставим игрока в новый слот
    squads_db[user_id_str][slot_num] = chosen_card
    save_data(squads_db, 'squads')
    
    bot.send_message(
        message.chat.id, 
        f"✅ Игрок **{chosen_card['name']}** успешно установлен на позицию!", 
        parse_mode="Markdown",
        reply_markup=create_main_menu(message.from_user.id)
    )
    show_squad(message.chat.id, message.from_user.id)

# ==============================================================================
# [12] ПВП АРЕНА (БОИ МЕЖДУ ИГРОКАМИ ЗА ОЧКИ РЕЙТИНГА)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🏟 ПВП Арена")
def pvp_menu(message):
    """Главное меню ПВП Арены."""
    if check_ban_status(message.from_user): return
    
    # Проверяем, собран ли состав
    squads_db = load_data('squads')
    my_squad = squads_db.get(str(message.from_user.id), [None] * 7)
    
    if my_squad.count(None) == 7:
        bot.send_message(
            message.chat.id, 
            "⚠️ Ваш состав полностью пуст! Зайдите в '📋 Состав' и установите хотя бы одного игрока перед выходом на Арену."
        )
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("⚔️ Поиск противника"),
        types.KeyboardButton("🏠 Назад в меню")
    )
    
    power = calculate_total_power(message.from_user.id)
    bot.send_message(
        message.chat.id, 
        f"🏟 **ДОБРО ПОЖАЛОВАТЬ НА ПВП АРЕНУ!**\n\n"
        f"Ваша текущая сила команды: `{power}`\n"
        f"За победу вы получаете `+25 очков рейтинга`!\n"
        f"За поражение вы теряете `-10 очков рейтинга`.\n\n"
        f"Нажмите 'Поиск противника', чтобы найти случайного менеджера.",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == "⚔️ Поиск противника")
def pvp_search(message):
    """Поиск случайного противника из базы пользователей."""
    if check_ban_status(message.from_user): return
    
    user_id = message.from_user.id
    user_id_str = str(user_id)
    
    bot.send_message(message.chat.id, "🔍 Ищем достойного соперника...", reply_markup=types.ReplyKeyboardRemove())
    time.sleep(2) # Задержка для эффекта поиска
    
    users_db = load_data('users')
    
    # Выбираем всех возможных противников, кроме себя и ботов (забаненных)
    bans_db = load_data('bans')
    possible_opponents = []
    
    for uid, data in users_db.items():
        if uid != user_id_str and uid not in bans_db:
            # Желательно, чтобы у противника был состав
            opp_squads = load_data('squads').get(uid, [None]*7)
            if opp_squads.count(None) < 7:
                possible_opponents.append(uid)
                
    if not possible_opponents:
        bot.send_message(
            message.chat.id, 
            "😔 К сожалению, на Арене сейчас нет подходящих противников. Попробуйте позже.",
            reply_markup=create_main_menu(user_id)
        )
        return
        
    opponent_id = random.choice(possible_opponents)
    opponent_data = users_db[opponent_id]
    
    run_pvp_battle(message, user_id_str, opponent_id, opponent_data)

def run_pvp_battle(message, p1_id_str, p2_id_str, p2_data):
    """Логика автоматического боя на основе силы состава."""
    users_db = load_data('users')
    
    p1_power = calculate_total_power(int(p1_id_str))
    p2_power = calculate_total_power(int(p2_id_str))
    
    p1_name = users_db[p1_id_str].get('nick', 'Менеджер 1')
    p2_name = p2_data.get('nick', 'Менеджер 2')
    
    bot.send_message(
        message.chat.id, 
        f"⚔️ **МАТЧ НАЙДЕН!**\n\n"
        f"🔵 **Ваша команда** (Сила: {p1_power})\n"
        f"   🆚\n"
        f"🔴 **Команда {p2_name}** (Сила: {p2_power})\n\n"
        f"Матч начинается...",
        parse_mode="Markdown"
    )
    time.sleep(2)
    
    # Добавляем элемент случайности (рандомный бафф/дебафф до 15% к силе)
    p1_roll = p1_power * random.uniform(0.85, 1.15)
    p2_roll = p2_power * random.uniform(0.85, 1.15)
    
    if p1_roll >= p2_roll:
        # Победа игрока
        users_db[p1_id_str]['score'] = users_db[p1_id_str].get('score', 0) + 25
        # Вычитаем очки у проигравшего, если у него больше 0
        users_db[p2_id_str]['score'] = max(0, users_db[p2_id_str].get('score', 0) - 10)
        
        result_text = (
            f"🎉 **ПОБЕДА!**\n\n"
            f"Ваша команда оказалась сильнее и тактически переиграла соперника.\n"
            f"🏆 Вы получаете `+25 очков рейтинга`!"
        )
    else:
        # Поражение игрока
        users_db[p1_id_str]['score'] = max(0, users_db[p1_id_str].get('score', 0) - 10)
        users_db[p2_id_str]['score'] = users_db[p2_id_str].get('score', 0) + 25
        
        result_text = (
            f"💀 **ПОРАЖЕНИЕ.**\n\n"
            f"Команда соперника пробила вашу защиту.\n"
            f"📉 Вы теряете `-10 очков рейтинга`.\n"
            f"Улучшайте состав и возвращайтесь!"
        )
        
    save_data(users_db, 'users')
    
    bot.send_message(
        message.chat.id, 
        result_text, 
        parse_mode="Markdown",
        reply_markup=create_main_menu(message.from_user.id)
    )

# ==============================================================================
# [13] ЗАПУСК И ГЛАВНЫЙ ЦИКЛ БОТА
# ==============================================================================
# Эта часть кода должна находиться в самом низу файла. Она отвечает за 
# беспрерывную работу бота (polling) и отлов критических ошибок.

if __name__ == '__main__':
    logger.info("Бот успешно инициализирован и запускается...")
    while True:
        try:
            # Запуск приема сообщений
            # none_stop=True - бот не будет останавливаться при мелких ошибках
            # timeout=60 - таймаут соединения с серверами Telegram
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.critical(f"Критическая ошибка в работе bot.polling: {e}")
            logger.info("Перезапуск бота через 5 секунд...")
            time.sleep(5)
