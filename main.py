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
roll_cooldowns = {1800}
pvp_cooldowns = {3600}

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
# [7] МОДУЛЬ ПРОМОКОДОВ (ИНТЕРАКТИВНЫЙ ВВОД, ВАЛИДАЦИЯ И НАГРАДЫ)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🎟 Промокод")
def promo_input_start(message):
    """Инициализирует процесс ввода промокода, переключая пользователя в режим ожидания текста."""
    if check_ban_status(message.from_user):
        return
        
    user_id = message.from_user.id
    log_action(user_id, "OPENED_PROMO_MENU")
    
    sent_msg = bot.send_message(
        message.chat.id, 
        "🎟 **АКТИВАЦИЯ ПРОМОКОДА**\n\nВведите ваш секретный промокод (регистр букв не имеет значения):", 
        reply_markup=create_cancel_menu(),
        parse_mode="Markdown"
    )
    # Регистрируем следующий шаг, передавая управление специализированной функции
    bot.register_next_step_handler(sent_msg, process_promo_logic)


def process_promo_logic(message):
    """Основной движок валидации введенного промокода и начисления внутриигровых бонусов."""
    user_id_key = str(message.from_user.id)
    
    # Обработка нажатия кнопки отмены
    if message.text == "❌ Отмена":
        log_action(user_id_key, "CANCELLED_PROMO_INPUT")
        bot.send_message(
            message.chat.id, 
            "🔄 Ввод промокода отменен. Вы вернулись в меню.", 
            reply_markup=create_main_menu(message.from_user.id)
        )
        return
        
    input_code = message.text.strip().upper()
    users_db = load_data('users')
    promos_db = load_data('promos')
    
    # Проверка существования пользователя в нашей базе данных
    if user_id_key not in users_db:
        bot.send_message(
            message.chat.id, 
            "❌ Системная ошибка: ваш профиль не найден. Перезапустите бота через /start", 
            reply_markup=create_main_menu(message.from_user.id)
        )
        return

    # Проверка: существует ли вообще такой промокод в базе данных
    if input_code not in promos_db:
        logger.info(f"Игрок {user_id_key} ввел неверный промокод: {input_code}")
        bot.send_message(
            message.chat.id, 
            "❌ К сожалению, такого промокода не существует или его срок действия истёк.", 
            reply_markup=create_main_menu(message.from_user.id)
        )
        return

    # Проверка: не активировал ли данный пользователь этот код ранее
    if 'used_promos' not in users_db[user_id_key]:
        users_db[user_id_key]['used_promos'] = []
        
    if input_code in users_db[user_id_key]['used_promos']:
        logger.info(f"Игрок {user_id_key} пытался повторно активировать код: {input_code}")
        bot.send_message(
            message.chat.id, 
            "❌ Вы уже активировали этот промокод ранее! Повторная активация невозможна.", 
            reply_markup=create_main_menu(message.from_user.id)
        )
        return

    # Извлечение параметров промокода
    code_info = promos_db[input_code]
    reward_type = code_info.get('type', 'score')
    reward_val = code_info.get('value', 0)
    
    success_msg = ""
    
    # Начисление награды в зависимости от типа промокода
    if reward_type == 'rolls':
        users_db[user_id_key]['free_rolls'] = users_db[user_id_key].get('free_rolls', 0) + int(reward_val)
        success_msg = f"🎉 **УСПЕШНО!**\n\nВы активировали промокод `{input_code}`!\n🎁 Награда: **+{int(reward_val)} бонусных прокрутов** карт!"
        
    elif reward_type == 'luck':
        users_db[user_id_key]['bonus_luck'] = float(reward_val)
        success_msg = f"🎉 **УСПЕШНО!**\n\nВы активировали промокод `{input_code}`!\n🎁 Награда: **Множитель удачи х{float(reward_val)}** на следующий бесплатный ролл!"
        
    elif reward_type == 'score':
        users_db[user_id_key]['score'] = users_db[user_id_key].get('score', 0) + int(reward_val)
        success_msg = f"🎉 **УСПЕШНО!**\n\nВы активировали промокод `{input_code}`!\n🎁 Награда: **+{int(reward_val):,} очков** на ваш баланс!"
        
    else:
        # Резервный тип награды, если произошла ошибка конфигурации
        users_db[user_id_key]['score'] = users_db[user_id_key].get('score', 0) + 1000
        success_msg = f"🎉 **УСПЕШНО!**\n\nПромокод активирован. Начислен стандартный бонус: **+1,000 очков**."

    # Фиксация активации промокода в истории игрока
    users_db[user_id_key]['used_promos'].append(input_code)
    
    # Сохранение обновленных данных на диск
    if save_data(users_db, 'users'):
        log_action(user_id_key, f"ACTIVATED_PROMO_{input_code}_TYPE_{reward_type}")
        bot.send_message(message.chat.id, success_msg, reply_markup=create_main_menu(message.from_user.id), parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "❌ Произошла ошибка при сохранении данных базы. Попробуйте позже.", reply_markup=create_main_menu(message.from_user.id))

# ==============================================================================
# [8] СИСТЕМА ПРОКРУТОВ С РАНДОМИЗАЦИЕЙ ВЕСОВЫХ КОЭФФИЦИЕНТОВ (ROLL ENGINE)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🎰 Крутить карту")
def roll_card_handler(message):
    """Генерирует случайную футбольную карту, учитывая кулдауны, баланс роллов и множители удачи."""
    if check_ban_status(message.from_user):
        return
        
    user_id_key = str(message.from_user.id)
    users_db = load_data('users')
    all_cards = load_data('cards')
    
    # Проверка критической ошибки пустоты пула карт
    if not all_cards or len(all_cards) == 0:
        logger.warning(f"Игрок {user_id_key} вызвал прокрут, но база карт пуста.")
        bot.send_message(message.chat.id, "❌ В игре пока нет доступных футбольных карточек. Администрация скоро их добавит!")
        return
        
    current_time_stamp = time.time()
    bonus_rolls = users_db.get(user_id_key, {}).get('free_rolls', 0)
    
    # Проверка временного ограничения (3 часа кулдауна)
    # Администраторы полностью игнорируют временные ограничения для тестов
    if not check_admin_permission(message.from_user) and bonus_rolls <= 0:
        if user_id_key in roll_cooldowns:
            elapsed_time = current_time_stamp - roll_cooldowns[user_id_key]
            if elapsed_time < 10800:
                remaining_seconds = int(10800 - elapsed_time)
                hours = remaining_seconds // 3600
                minutes = (remaining_seconds % 3600) // 60
                bot.send_message(
                    message.chat.id, 
                    f"⏳ **Кулдаун на бесплатный ролл!**\n\nВы сможете запустить рулетку снова через **{hours}ч {minutes}м**.\n"
                    f"💡 Копите бонусные прокруты за приглашение друзей (меню 👥 Рефералы) или вводите промокоды!",
                    parse_mode="Markdown"
                )
                return

    # Рассчет шансов выпадения карт с учетом динамического множителя удачи (Luck Factor)
    user_luck_multiplier = users_db.get(user_id_key, {}).get('bonus_luck', 1.0)
    rarity_indices = sorted(RARITY_STATS.keys())
    
    calculated_weights = []
    for r_level in rarity_indices:
        base_chance = RARITY_STATS[r_level]['chance']
        # Удача увеличивает шансы исключительно на Эпические (4) и Легендарные (5) карточки
        if r_level >= 4:
            calculated_weights.append(base_chance * user_luck_multiplier)
        else:
            calculated_weights.append(base_chance)

    # Математический выбор случайной редкости на основе весов
    chosen_rarity_level = random.choices(rarity_indices, weights=calculated_weights)[0]
    
    # Фильтрация глобального пула карт под выбранную редкость
    filtered_card_pool = [card for card in all_cards if card.get('stars', 1) == chosen_rarity_level]
    
    # Защитный фоллбэк: если карт выбранной редкости нет в файле, берем любую случайную карту
    if not filtered_card_pool:
        won_card_object = random.choice(all_cards)
        chosen_rarity_level = won_card_object.get('stars', 1)
    else:
        won_card_object = random.choice(filtered_card_pool)
        
    # Списание прокрута или обновление таймера кулдауна
    if bonus_rolls > 0:
        users_db[user_id_key]['free_rolls'] -= 1
        attempt_info_text = f"🎫 Использован 1 бонусный прокрут. Осталось: **{users_db[user_id_key]['free_rolls']}** шт."
    else:
        roll_cooldowns[user_id_key] = current_time_stamp
        attempt_info_text = "⏳ Следующий бесплатный запуск рулетки доступен через **3 часа**."

    # Сброс множителя удачи до стандартного значения 1.0 после совершения ролла
    users_db[user_id_key]['bonus_luck'] = 1.0
    
    # Загрузка и проверка коллекции пользователя
    collections_db = load_data('colls')
    if user_id_key not in collections_db:
        collections_db[user_id_key] = []
        
    # Проверка на наличие дубликата карточки по её имени
    has_duplicate = any(existing_card.get('name') == won_card_object.get('name') for existing_card in collections_db[user_id_key])
    
    if has_duplicate:
        # Формула компенсации: 30% от базовой стоимости очков редкости карты
        earned_points = int(RARITY_STATS[chosen_rarity_level]['score'] * 0.3)
        result_status_label = f"🔄 **ДУБЛИКАТ!** Вы получили компенсацию **30%** очков: `+{earned_points:,}`"
    else:
        # Начисление 100% очков за новую карту
        earned_points = RARITY_STATS[chosen_rarity_level]['score']
        result_status_label = f"✨ **НОВАЯ КАРТА!** Она добавлена в коллекцию: `+{earned_points:,}` очков."
        collections_db[user_id_key].append(won_card_object)
        save_data(collections_db, 'colls')

    # Обновление баланса счета игрока в базе
    users_db[user_id_key]['score'] = users_db[user_id_key].get('score', 0) + earned_points
    save_data(users_db, 'users')
    
    # Формирование красивой информационной карточки игрока
    stars_visual_representation = "⭐" * chosen_rarity_level
    rarity_text_label = RARITY_STATS[chosen_rarity_level]['label']
    card_position_ru = POSITIONS_RU.get(won_card_object.get('position', 'ЦП'), 'Полузащитник')
    card_club = won_card_object.get('club', 'Свободный агент')
    
    caption_message = (
        f"🏆 **СПИН РУЛЕТКИ ЗАВЕРШЕН!**\n\n"
        f"🏃‍♂️ Игрок: **{won_card_object.get('name')}**\n"
        f"🛡 Позиция: `{card_position_ru}`\n"
        f"🏢 Клуб: _{card_club}_\n"
        f"📊 Редкость: {stars_visual_representation} ({rarity_text_label})\n"
        f"⚡ Сила атаки (АТК): **{RARITY_STATS[chosen_rarity_level]['atk']}**\n\n"
        f"{result_status_label}\n"
        f"💰 Ваш новый баланс: **{users_db[user_id_key]['score']:,}** очков.\n\n"
        f"{attempt_info_text}"
    )

    # Безопасная отправка фотографии с отловом возможных ошибок невалидных ссылок
    try:
        bot.send_photo(
            message.chat.id, 
            won_card_object.get('photo'), 
            caption=caption_message, 
            parse_mode="Markdown"
        )
    except Exception as photo_send_error:
        logger.error(f"Не удалось отправить фото карты через send_photo: {photo_send_error}")
        # Запасной текстовый вариант вывода, если URL картинки сломан
        bot.send_message(
            message.chat.id, 
            f"🖼 *(Изображение недоступно)*\n\n{caption_message}", 
            parse_mode="Markdown"
        )

# ==============================================================================
# [9] ИНТЕРАКТИВНАЯ ГАЛЕРЕЯ И СОРТИРОВКА КОЛЛЕКЦИИ (COLLECTION ENGINE)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🗂 Коллекция")
def collection_menu_handler(message):
    """Отображает общую сводную статистику альбома карточек игрока и выводит интерактивные кнопки категорий."""
    if check_ban_status(message.from_user):
        return
        
    user_id_key = str(message.from_user.id)
    collections_db = load_data('colls')
    my_cards_list = collections_db.get(user_id_key, [])
    
    if not my_cards_list:
        bot.send_message(
            message.chat.id, 
            "🗂 **ВАША КОЛЛЕКЦИЯ**\n\nУ вас пока нет ни одной футбольной карточки.\n"
            "Запустите рулетку в меню: **🎰 Крутить карту**, чтобы собрать свой первый состав!", 
            parse_mode="Markdown"
        )
        return

    # Подсчет статистики распределения карт по категориям редкости
    stats_by_rarity = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for card in my_cards_list:
        stars = card.get('stars', 1)
        if stars in stats_by_rarity:
            stats_by_rarity[stars] += 1

    summary_text = (
        f"🗂 **ГЛАВНЫЙ АЛЬБОМ КОЛЛЕКЦИИ**\n\n"
        f"Всего карточек во владении: **{len(my_cards_list)}** шт.\n\n"
        f"⚪️ Обычные (⭐): **{stats_by_rarity[1]}** шт.\n"
        f"🟢 Необычные (⭐⭐): **{stats_by_rarity[2]}** шт.\n"
        f"🔵 Редкие (⭐⭐⭐): **{stats_by_rarity[3]}** шт.\n"
        f"🟡 Эпические (⭐⭐⭐⭐): **{stats_by_rarity[4]}** шт.\n"
        f"🔴 Легендарные (⭐⭐⭐⭐⭐): **{stats_by_rarity[5]}** шт.\n\n"
        f"Выберите интересующую категорию редкости для просмотра подробного списка карт:"
    )

    # Генерация инлайн-кнопок для фильтрации карт по звездам
    inline_markup = types.InlineKeyboardMarkup(row_width=2)
    btn_r1 = types.InlineKeyboardButton("⭐ Обычные", callback_data="view_rarity_1")
    btn_r2 = types.InlineKeyboardButton("⭐⭐ Необычные", callback_data="view_rarity_2")
    btn_r3 = types.InlineKeyboardButton("⭐⭐⭐ Редкие", callback_data="view_rarity_3")
    btn_r4 = types.InlineKeyboardButton("⭐⭐⭐⭐ Эпики", callback_data="view_rarity_4")
    btn_r5 = types.InlineKeyboardButton("👑 Легенды", callback_data="view_rarity_5")
    
    inline_markup.add(btn_r1, btn_r2)
    inline_markup.add(btn_r3, btn_r4)
    inline_markup.add(btn_r5)

    bot.send_message(message.chat.id, summary_text, reply_markup=inline_markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith("view_rarity_"))
def process_view_rarity_callback(call):
    """Динамический обработчик инлайн-кнопок категорий коллекции. Выводит детальный список отфильтрованных карт."""
    user_id_key = str(call.from_user.id)
    rarity_level_to_filter = int(call.data.replace("view_rarity_", ""))
    
    collections_db = load_data('colls')
    my_cards_list = collections_db.get(user_id_key, [])
    
    # Фильтруем карты пользователя по нажатой редкости
    filtered_cards = [c for c in my_cards_list if c.get('stars', 1) == rarity_level_to_filter]
    label_text = RARITY_STATS[rarity_level_to_filter]['label']
    stars_str = "⭐" * rarity_level_to_filter

    if not filtered_cards:
        bot.answer_callback_query(call.id, f"У вас нет карт редкости {label_text}!", show_alert=True)
        return

    # Всплывающее мини-уведомление в клиенте Telegram
    bot.answer_callback_query(call.id, f"Загрузка категории: {label_text}")

    response_page_text = f"🗂 **СПИСОК КАРТ [{label_text.upper()} {stars_str}]**\n\n"
    for index, card in enumerate(filtered_cards, 1):
        pos = POSITIONS_RU.get(card.get('position', 'ЦП'), 'Полузащитник')
        club = card.get('club', 'Свободный агент')
        power = RARITY_STATS[rarity_level_to_filter]['atk']
        response_page_text += f"{index}. **{card.get('name')}** (`{pos}`) — Клуб: _{club}_ | АТК: **{power}**\n"

    response_page_text += "\n*Вы можете использовать данные карты для формирования тактического состава команды.*"
    
    # Отправляем отдельным сообщением, сохраняя структуру главного меню
    bot.send_message(call.message.chat.id, response_page_text, parse_mode="Markdown")

# ==============================================================================
# [10] УПРАВЛЕНИЕ СВОИМ ТАКТИЧЕСКИМ СОСТАВОМ (SQUAD ENGINE)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "📋 Состав")
def squad_menu_handler(message):
    """Отображает текущий футбольный ростер из 7 позиций и предоставляет интерфейс для замены игроков."""
    if check_ban_status(message.from_user):
        return
        
    user_id_key = str(message.from_user.id)
    squads_db = load_data('squads')
    
    # Инициализация пустого состава из 7 слотов (None), если записей о пользователе нет
    if user_id_key not in squads_db:
        squads_db[user_id_key] = [None] * 7
        save_data(squads_db, 'squads')

    current_user_squad = squads_db[user_id_key]
    total_calculated_power = calculate_total_power(message.from_user.id)
    
    squad_view_text = (
        f"📋 **ВАШ ТАКТИЧЕСКИЙ СОСТАВКОМАНДЫ**\n\n"
        f"Здесь отображаются футболисты, защищающие честь вашего клуба на ПВП Аренах. "
        f"Правильно подобранный состав максимизирует боевую силу команды.\n\n"
        f"⚔️ Суммарная мощь состава (АТК): **{total_calculated_power}**\n\n"
        f"=== ТЕКУЩИЙ РОСТЕР ПОЗИЦИЙ ===\n"
    )

    inline_squad_markup = types.InlineKeyboardMarkup(row_width=1)
    
    for slot_id, slot_meta in SQUAD_SLOTS.items():
        # Безопасное извлечение карты из слота с проверкой выхода за индексы массива
        assigned_card = None
        if slot_id < len(current_user_squad):
            assigned_card = current_user_squad[slot_id]
            
        if assigned_card:
            card_rarity_stars = "⭐" * assigned_card.get('stars', 1)
            slot_status_string = f"{slot_meta['label']}: {assigned_card.get('name')} ({card_rarity_stars})"
        else:
            slot_status_string = f"{slot_meta['label']}: ❌ Позиция пуста"
            
        squad_view_text += f"• {slot_status_string}\n"
        
        # Создаем индивидуальную кнопку настройки для каждого слота
        button_callback_data = f"manage_slot_{slot_id}"
        inline_squad_markup.add(types.InlineKeyboardButton(f"⚙️ Настроить {slot_meta['code']}", callback_data=button_callback_data))

    squad_view_text += "\nНажмите на кнопку соответствующей позиции ниже, чтобы выставить игрока из вашей коллекции."
    bot.send_message(message.chat.id, squad_view_text, reply_markup=inline_squad_markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith("manage_slot_"))
def process_manage_slot_callback(call):
    """Выводит список доступных карт из коллекции пользователя для размещения в выбранный слот."""
    user_id_key = str(call.from_user.id)
    slot_id_to_change = int(call.data.replace("manage_slot_", ""))
    
    slot_configuration = SQUAD_SLOTS.get(slot_id_to_change)
    if not slot_configuration:
        bot.answer_callback_query(call.id, "Критическая ошибка конфигурации слота.", show_alert=True)
        return

    required_position_code = slot_configuration['code']
    collections_db = load_data('colls')
    my_cards_list = collections_db.get(user_id_key, [])
    
    # Фильтруем коллекцию: подходят только те карты, позиция которых строго совпадает с позицией слота
    eligible_cards = [c for c in my_cards_list if c.get('position') == required_position_code]
    
    if not eligible_cards:
        bot.answer_callback_query(
            call.id, 
            f"В вашей коллекции нет игроков позиции {required_position_code}!\nКрутите рулетку, чтобы выбить их.", 
            show_alert=True
        )
        return

    bot.answer_callback_query(call.id, "Загрузка доступных футболистов...")
    
    selection_markup = types.InlineKeyboardMarkup(row_width=1)
    
    for index, card in enumerate(eligible_cards):
        stars_visual = "⭐" * card.get('stars', 1)
        button_text = f"{card.get('name')} [{stars_visual}] (АТК: {RARITY_STATS[card.get('stars', 1)]['atk']})"
        # Кодируем в callback_data ID слота и индекс выбранной карты в коллекции игрока
        cb_data = f"setcard_{slot_id_to_change}_{index}"
        selection_markup.add(types.InlineKeyboardButton(button_text, callback_data=cb_data))
        
    # Добавляем опцию полной очистки текущего слота
    selection_markup.add(types.InlineKeyboardButton("🗑 Очистить слот (убрать игрока)", callback_data=f"clear_slot_{slot_id_to_change}"))

    bot.send_message(
        call.message.chat.id, 
        f"🏃‍♂️ **ВЫБОР ИГРОКА НА ПОЗИЦИЮ {slot_configuration['label']}**\n\n"
        f"Ниже представлены все подходящие футболисты из вашего альбома.\n"
        f"Нажмите на нужного игрока, чтобы заявить его в стартовый состав:",
        reply_markup=selection_markup,
        parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("setcard_") or call.data.startswith("clear_slot_"))
def process_apply_card_to_slot_callback(call):
    """Записывает выбранную карту в массив состава JSON файла или производит очистку слота."""
    user_id_key = str(call.from_user.id)
    squads_db = load_data('squads')
    
    if user_id_key not in squads_db:
        squads_db[user_id_key] = [None] * 7

    if call.data.startswith("clear_slot_"):
        slot_to_clear = int(call.data.replace("clear_slot_", ""))
        if slot_to_clear < len(squads_db[user_id_key]):
            squads_db[user_id_key][slot_to_clear] = None
            
        save_data(squads_db, 'squads')
        bot.answer_callback_query(call.id, "Позиция успешно освобождена.", show_alert=False)
        bot.send_message(call.message.chat.id, "✅ Игрок убран из состава. Обновите меню состава через кнопку **📋 Состав**.", parse_mode="Markdown")
        return

    # Логика назначения карты в слот
    # Формат данных: setcard_[slot_id]_[card_index_in_eligible_list]
    parsed_parameters = call.data.split("_")
    slot_id = int(parsed_parameters[1])
    card_index = int(parsed_parameters[2])
    
    slot_configuration = SQUAD_SLOTS.get(slot_id)
    required_position_code = slot_configuration['code']
    
    collections_db = load_data('colls')
    my_cards_list = collections_db.get(user_id_key, [])
    eligible_cards = [c for c in my_cards_list if c.get('position') == required_position_code]
    
    if card_index >= len(eligible_cards):
        bot.answer_callback_query(call.id, "Ошибка: выбранная карта больше не существует.", show_alert=True)
        return
        
    chosen_card_object = eligible_cards[card_index]
    
    # Запись карты в соответствующий индекс массива состава
    squads_db[user_id_key][slot_id] = chosen_card_object
    
    if save_data(squads_db, 'squads'):
        bot.answer_callback_query(call.id, f"{chosen_card_object.get('name')} теперь в старте!", show_alert=False)
        log_action(user_id_key, f"SET_CARD_{chosen_card_object.get('name')}_TO_SLOT_{slot_id}")
        bot.send_message(
            call.message.chat.id, 
            f"✅ **СОСТАВ ОБНОВЛЕН!**\n\nФутболист **{chosen_card_object.get('name')}** успешно занял позицию `{slot_configuration['label']}`.\n"
            f"Откройте вкладку **📋 Состав** снова, чтобы увидеть изменения и общую силу атаки команды.",
            parse_mode="Markdown"
        )
    else:
        bot.send_message(call.message.chat.id, "❌ Произошла техническая ошибка записи состава.")

# ==============================================================================
# [11] ПРОФИЛЬНЫЙ МОДУЛЬ И ГЛОБАЛЬНЫЕ РЕЙТИНГИ
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile_view_handler(message):
    """Выводит личную сводную карточку игрока, баланс очков, общее число собранных уникальных карт и мощь."""
    if check_ban_status(message.from_user):
        return
        
    user_id_string = str(message.from_user.id)
    users_db = load_data('users')
    collections_db = load_data('colls')
    
    user_profile_data = users_db.get(user_id_string, {})
    total_unique_cards_owned = len(collections_db.get(user_id_string, []))
    total_combat_power = calculate_total_power(message.from_user.id)
    
    current_luck = user_profile_data.get('bonus_luck', 1.0)
    luck_status_string = f"Удача повышенная (х{current_luck})" if current_luck > 1.0 else "Стандартная (х1.0)"
    
    profile_card_text = (
        f"👤 **ЛИЧНЫЙ ПРОФИЛЬ МЕНЕДЖЕРА**\n\n"
        f"🆔 Ваш Telegram ID: `{user_id_string}`\n"
        f"📝 Имя в игре: **{user_profile_data.get('nick', 'Не указано')}**\n"
        f"🌐 Юзернейм: {user_profile_data.get('username', '@нет')}\n\n"
        f"💰 Финансовый баланс: **{user_profile_data.get('score', 0):,}** очков счета\n"
        f"🎫 Бонусные прокруты в запасе: **{user_profile_data.get('free_rolls', 0)}** шт.\n"
        f"🍀 Текущий статус удачи: `{luck_status_string}`\n\n"
        f"📊 Военно-футбольные показатели:\n"
        f"— Открыто карточек в альбоме: **{total_unique_cards_owned}** шт.\n"
        f"— Боевая мощь основы состава (АТК): **{total_combat_power}** единиц силы"
    )
    
    bot.send_message(message.chat.id, profile_card_text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "🏆 Топ очков")
def global_top_handler(message):
    """Формирует и выводит таблицу лидеров из 10 пользователей с наивысшим балансом очков."""
    if check_ban_status(message.from_user):
        return
        
    users_db = load_data('users')
    
    # Сортировка словаря пользователей по убыванию значения поля 'score'
    sorted_leaderboard = sorted(
        users_db.items(), 
        key=lambda item: item[1].get('score', 0), 
        reverse=True
    )[:10]
    
    leaderboard_text = "🏆 **ТАБЛИЦА МИРОВЫХ ЛИДЕРОВ (ТОП-10 ИГРОКОВ)**\n\n"
    leaderboard_text += "Позиция | Менеджер | Текущий баланс очков\n"
    leaderboard_text += "—" * 20 + "\n"
    
    # Красивые эмодзи медалей для призовой тройки лидеров
    medal_mapping = {1: "🥇", 2: "🥈", 3: "🥉"}
    
    for position_rank, (uid, info) in enumerate(sorted_leaderboard, 1):
        medal_or_rank_prefix = medal_mapping.get(position_rank, f"{position_rank}.")
        user_name = info.get('username', f"id_{uid}")
        score_formatted = info.get('score', 0)
        
        leaderboard_text += f"{medal_or_rank_prefix} {user_name} — **{score_formatted:,}** очков\n"
        
    leaderboard_text += "\n*Рейтинг обновляется в реальном времени. Крутите рулетку и побеждайте в ПВП, чтобы подняться на вершину!*"
    bot.send_message(message.chat.id, leaderboard_text, parse_mode="Markdown")

# ==============================================================================
# КОНЕЦ ВТОРOЙ ЧАСТИ. СЛЕДУЮЩАЯ ЧАСТЬ ЗАКЛЮЧИТЕЛЬНАЯ (ПВП И АДМИН-ПАНЕЛЬ)
# ==============================================================================

# ==============================================================================
# [12] МОДУЛЬ ПВП АРЕНЫ (КЛАССИЧЕСКИЙ СИМУЛЯТОР МАТЧЕЙ С ЗАЩИТОЙ ОТ АБУЗА)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🏟 ПВП Арена")
def pvp_arena_entryPOINT(message):
    """Точка входа на PVP Арену. Проверяет баны, рассчитывает мощь состава и выводит инлайн-вызов."""
    if check_ban_status(message.from_user):
        return

    user_id_key = str(message.from_user.id)
    log_action(user_id_key, "OPENED_PVP_ARENA")
    
    user_combat_power = calculate_total_power(message.from_user.id)
    
    # Защитная блокировка: если у игрока пустой состав (0 АТК), не допускаем до подбора матча
    if user_combat_power <= 0:
        bot.send_message(
            message.chat.id,
            "🏟 **ПВП АРЕНА БЛОКИРОВАНА!**\n\n"
            "❌ Вы не можете выйти на поле, так как ваш текущий состав совершенно пуст!\n"
            "💡 Пожалуйста, перейдите в меню **📋 Состав**, выберите доступных игроков из "
            "вашей коллекции на тактические позиции, и только после этого возвращайтесь на арену.",
            parse_mode="Markdown"
        )
        return

    current_timestamp = time.time()
    
    # Проверка глобального кулдауна на ПВП поединки (5 минут = 300 секунд)
    # Администраторы пропускаются без задержек для проведения системных тестов
    if not check_admin_permission(message.from_user):
        if user_id_key in pvp_cooldowns:
            time_passed = current_timestamp - pvp_cooldowns[user_id_key]
            if time_passed < 300:
                seconds_left = int(300 - time_passed)
                bot.send_message(
                    message.chat.id,
                    f"⏳ **Ваша команда восстанавливает силы после прошлого матча!**\n\n"
                    f"Следующий поединок на ПВП Арене будет доступен через **{seconds_left} сек.**\n"
                    f"Отдохните или займитесь ротацией состава в меню!",
                    parse_mode="Markdown"
                )
                return

    pvp_intro_text = (
        f"🏟 **ДОБРО ПОЖАЛОВАТЬ НА СТАТУСНУЮ ПВП АРЕНУ!**\n\n"
        f"Здесь лучшие менеджеры выставляют свои составы против сильнейших клубов.\n\n"
        f"⚔️ Текущая боевая мощь вашей основы: **{user_combat_power} АТК**\n"
        f"🎲 Система подберет вам равного по силе оппонента в реальном времени.\n\n"
        f"⚠️ *Внимание! Кнопка вызова одноразовая. Сразу после клика сообщение сотрется для защиты от спама!*"
    )

    inline_pvp_markup = types.InlineKeyboardMarkup()
    btn_find_match = types.InlineKeyboardButton("🥊 Найти соперника и начать матч", callback_data="execute_pvp_match")
    inline_pvp_markup.add(btn_find_match)

    bot.send_message(message.chat.id, pvp_intro_text, reply_markup=inline_pvp_markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data == "execute_pvp_match")
def execute_pvp_match_callback_handler(call):
    """Движок симуляции футбольного боя. Немедленно стирает старое сообщение для ликвидации абуза."""
    user_id_key = str(call.from_user.id)
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    # [КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ]: Немедленное удаление старого интерактивного сообщения
    try:
        bot.delete_message(chat_id, message_id)
        logger.info(f"Сообщение {message_id} успешно стерто. Абуз кликов заблокирован для {user_id_key}.")
    except Exception as deletion_error:
        logger.error(f"Не удалось удалить сообщение {message_id}: {deletion_error}. Возможно, оно уже удалено.")
        bot.answer_callback_query(call.id, "❌ Эта кнопка устарела или уже была нажата!", show_alert=True)
        return

    # Всплывающий статус
    bot.answer_callback_query(call.id, "Оппонент найден! Начинаем симуляцию матча...")

    users_db = load_data('users')
    user_power = calculate_total_power(call.from_user.id)
    
    # Двойная скрытая проверка на силу (если игрок умудрился очистить состав в другом окне)
    if user_power <= 0:
        bot.send_message(chat_id, "❌ Ошибка: ваш состав пуст. Симуляция отменена.")
        return

    # Генерация параметров оппонента (случайный клуб вокруг силы игрока от 75% до 125%)
    opponent_club_name = random.choice(FOOTBALL_CLUBS_POOL)
    opponent_power = int(user_power * random.uniform(0.75, 1.25))
    
    # Фиксация времени проведения матча в кулдауны
    pvp_cooldowns[user_id_key] = time.time()

    # Текстовая трансляция опасных моментов матча
    match_narration_intro = (
        f"⚽️ **МАТЧ НАЧАЛСЯ! ГРАНДИОЗНОЕ ПВП ПРОТИВОСТОЯНИЕ!**\n\n"
        f"🏃‍♂️ Ваш клуб (Сила: **{user_power}**) vs 🛡 **{opponent_club_name}** (Сила: **{opponent_power}**)\n"
        f"⚡️ Судья дает стартовый свисток! Смотрим за развитием событий на поле...\n"
    )
    
    interim_msg = bot.send_message(chat_id, match_narration_intro, parse_mode="Markdown")
    time.sleep(2.0) # Имитация ожидания первого тайма

    # Математический расчет исхода поединка на основе пропорции сил
    total_combined_power = user_power + opponent_power
    user_victory_chance = (user_power / total_combined_power) * 100
    random_roll = random.uniform(0, 100)

    # Генерация случайного счета матча
    if random_roll <= user_victory_chance:
        user_goals = random.randint(1, 5)
        opponent_goals = random.randint(0, user_goals - 1)
        match_result_status = "WIN"
    else:
        opponent_goals = random.randint(1, 5)
        user_goals = random.randint(0, opponent_goals - 1)
        # Если силы абсолютно равны, возможна ничья
        if user_goals == opponent_goals:
            user_goals = max(0, user_goals - 1)
        match_result_status = "LOSE"

    # Текстовые логи игровых минут
    minute_30_event = random.choice([
        "⏱ **30' минута**: Ваша команда проводит стремительную фланговую атаку! Пас в центр штрафной...",
        "⏱ **30' минута**: Соперник прессингует на вашей половине поля, жесткий подкат в обороне!"
    ])
    minute_70_event = random.choice([
        "⏱ **70' минута**: Опасный штрафной удар возле ворот противника! Мяч летит в девятку...",
        "⏱ **70' минута**: Вратарь вашей команды совершает невероятный сейв кончиками пальцев!"
    ])

    # Формирование финального вердикта
    if match_result_status == "WIN":
        reward_points = random.randint(10000, 20000)
        users_db[user_id_key]['score'] = users_db[user_id_key].get('score', 0) + reward_points
        
        final_verdict_text = (
            f"🎉 **ПОБЕДА ВЕЛИКОЛЕПНОГО МЕНЕДЖЕРА!**\n\n"
            f"📊 Финальный счет: 🏆 **{user_goals} : {opponent_goals}**\n"
            f"💪 Ваш тактический гений оказался сильнее клуба _{opponent_club_name}_.\n\n"
            f"🎁 **Ваша заслуженная награда:**\n"
            f"— 💰 **+{reward_points:,} очков счета**\n\n"
            f"💰 Текущий капитал: **{users_db[user_id_key]['score']:,}** очков."
        )
        log_action(user_id_key, f"PVP_WIN_AGAINST_{opponent_club_name}_REWARD_{reward_points}")
    else:
        consolation_points = 1500
        users_db[user_id_key]['score'] = users_db[user_id_key].get('score', 0) + consolation_points
        
        final_verdict_text = (
            f"❌ **ДОСАДНОЕ ПОРАЖЕНИЕ НА ПОЛЕ...**\n\n"
            f"📊 Финальный счет: **{user_goals} : {opponent_goals}** в пользу _{opponent_club_name}_\n"
            f"😔 Сегодня удача была на стороне оппонента. Пересмотрите состав команды и улучшите позиции!\n\n"
            f"🎁 **Утешительный бонус:**\n"
            f"— 💰 **+{consolation_points:,} очков счета**\n\n"
            f"💰 Текущий капитал: **{users_db[user_id_key]['score']:,}** очков."
        )
        log_action(user_id_key, f"PVP_LOSE_AGAINST_{opponent_club_name}")

    # Сохраняем экономические изменения в файл
    save_data(users_db, 'users')

    # Сборка и отправка полного отчета о матче
    full_report_text = (
        f"🏟 **ОФИЦИАЛЬНЫЙ РЕЗУЛЬТАТ МАТЧА АРЕНЫ**\n\n"
        f"🏃‍♂️ Ваша АТК: `{user_power}` | 🛡 Оппонент АТК: `{opponent_power}`\n"
        f"🏢 Соперник: **{opponent_club_name}**\n"
        f"—”—”—”—”—”—”—”—”—”—”—”—”—\n"
        f"{minute_30_event}\n\n"
        f"{minute_70_event}\n"
        f"—”—”—”—”—”—”—”—”—”—”—”—”—\n"
        f"{final_verdict_text}"
    )

    try:
        bot.edit_message_text(full_report_text, chat_id=chat_id, message_id=interim_msg.message_id, parse_mode="Markdown")
    except Exception as edit_err:
        logger.error(f"Не удалось отредактировать сообщение трансляции: {edit_err}")
        bot.send_message(chat_id, full_report_text, parse_mode="Markdown")

# ==============================================================================
# [13] МОДУЛЬ АДМИНИСТРИРОВАНИЯ (УПРАВЛЕНИЕ ФАЙЛАМИ КОНФИГУРАЦИЙ И БАНАМИ)
# ==============================================================================

@bot.message_handler(func=lambda m: m.text == "🛠 Админ-панель")
def admin_panel_root_handler(message):
    """Открывает специализированное инженерное меню для администраторов из списка ADMINS."""
    class LocalUser:
        def __init__(self, uid): self.id = uid
        
    if not check_admin_permission(LocalUser(message.from_user.id)):
        return

    log_action(message.from_user.id, "OPENED_ADMIN_PANEL")
    bot.send_message(
        message.chat.id,
        "🛠 **ГЛАВНЫЙ ПУЛЬТ УПРАВЛЕНИЯ БОТОМ**\n\n"
        "Вы авторизованы как главный администратор системы.\n"
        "Используйте кнопки нижнего меню для внесения изменений в базы данных JSON.",
        reply_markup=create_admin_menu(),
        parse_mode="Markdown"
    )


@bot.message_handler(func=lambda m: m.text == "🏠 Назад в меню")
def admin_back_to_main_menu_handler(message):
    """Обеспечивает корректный возврат из админ-панели в стандартный интерфейс игрока."""
    if check_ban_status(message.from_user):
        return
    bot.send_message(
        message.chat.id,
        "🔄 Вы покинули пульт управления и вернулись в главное меню симулятора.",
        reply_markup=create_main_menu(message.from_user.id)
    )

# ------------------------------------------------------------------------------
# ПОДМОДУЛЬ: ДОБАВЛЕНИЕ НОВОЙ КАРТЫ В ОБЩИЙ ПУЛ (WIZARD STEPS)
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "➕ Добавить карту")
def admin_add_card_step_1_name(message):
    if not check_admin_permission(message.from_user): return
    
    msg = bot.send_message(message.chat.id, "➕ **ДОБАВЛЕНИЕ КАРТЫ [ШАГ 1]**\n\nВведите ФИО или имя футболиста:", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, admin_add_card_step_2_pos, {})


def admin_add_card_step_2_pos(message, card_wizard_data):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Добавление карты прервано.", reply_markup=create_admin_menu())
        return
        
    card_wizard_data['name'] = message.text.strip()
    
    pos_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    pos_markup.add("ГК", "ЛЗ", "ПЗ", "ЦП", "ЛВ", "ПВ", "КФ", "❌ Отмена")
    
    msg = bot.send_message(
        message.chat.id, 
        f"➕ **ДОБАВЛЕНИЕ КАРТЫ [ШАГ 2]**\n\nИмя: *{card_wizard_data['name']}*\n\nВыберите позицию на поле из списка:", 
        reply_markup=pos_markup, 
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_add_card_step_3_club, card_wizard_data)


def admin_add_card_step_3_club(message, card_wizard_data):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Добавление карты прервано.", reply_markup=create_admin_menu())
        return
        
    card_wizard_data['position'] = message.text.strip().upper()
    
    msg = bot.send_message(
        message.chat.id,
        f"➕ **ДОБАВЛЕНИЕ КАРТЫ [ШАГ 3]**\n\nПозиция: `{card_wizard_data['position']}`\n\nВведите название футбольного клуба карточки:",
        reply_markup=create_cancel_menu(),
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_add_card_step_4_stars, card_wizard_data)


def admin_add_card_step_4_stars(message, card_wizard_data):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Добавление карты прервано.", reply_markup=create_admin_menu())
        return
        
    card_wizard_data['club'] = message.text.strip()
    
    stars_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    stars_markup.add("1", "2", "3", "4", "5", "❌ Отмена")
    
    msg = bot.send_message(
        message.chat.id,
        f"➕ **ДОБАВЛЕНИЕ КАРТЫ [ШАГ 4]**\n\nКлуб: _{card_wizard_data['club']}_\n\nУкажите редкость карты в звездах (от 1 до 5):",
        reply_markup=stars_markup,
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_add_card_step_5_photo, card_wizard_data)


def admin_add_card_step_5_photo(message, card_wizard_data):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Добавление карты прервано.", reply_markup=create_admin_menu())
        return
        
    try:
        card_wizard_data['stars'] = int(message.text.strip())
    except ValueError:
        card_wizard_data['stars'] = 1
        
    msg = bot.send_message(
        message.chat.id,
        f"➕ **ДОБАВЛЕНИЕ КАРТЫ [ШАГ 5]**\n\nЗвездность: {card_wizard_data['stars']} ⭐\n\nОтправьте прямую URL ссылку на картинку/фотографию карты:",
        reply_markup=create_cancel_menu(),
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_add_card_finalize, card_wizard_data)


def admin_add_card_finalize(message, card_wizard_data):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Добавление карты прервано.", reply_markup=create_admin_menu())
        return
        
    card_wizard_data['photo'] = message.text.strip()
    
    cards_list = load_data('cards')
    cards_list.append(card_wizard_data)
    
    if save_data(cards_list, 'cards'):
        bot.send_message(
            message.chat.id,
            f"✅ **КАРТОЧКА УСПЕШНО ИНИЦИАЛИЗИРОВАНА И ДОБАВЛЕНА!**\n\n"
            f"🏃‍♂️ Имя: **{card_wizard_data['name']}**\n"
            f"🛡 Позиция: `{card_wizard_data['position']}`\n"
            f"🏢 Клуб: _{card_wizard_data['club']}_\n"
            f"⭐ Звезд: **{card_wizard_data['stars']}**",
            reply_markup=create_admin_menu(),
            parse_mode="Markdown"
        )
        logger.info(f"Администратор добавил новую карту: {card_wizard_data['name']}")
    else:
        bot.send_message(message.chat.id, "❌ Произошла ошибка записи файла карты.", reply_markup=create_admin_menu())

# ------------------------------------------------------------------------------
# ПОДМОДУЛЬ: УДАЛЕНИЕ КАРТЫ ИЗ ИГРЫ
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "🗑 Удалить карту")
def admin_delete_card_start(message):
    if not check_admin_permission(message.from_user): return
    
    msg = bot.send_message(message.chat.id, "🗑 **УДАЛЕНИЕ КАРТЫ**\n\nВведите ТОЧНОЕ имя футболиста, карту которого нужно стереть:", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, admin_delete_card_process)


def admin_delete_card_process(message):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Удаление отменено.", reply_markup=create_admin_menu())
        return
        
    target_name = message.text.strip()
    cards_pool = load_data('cards')
    
    # Поиск и фильтрация всех карт, чье имя не совпадает с указанным
    initial_length = len(cards_pool)
    updated_pool = [card for card in cards_pool if card.get('name', '').lower() != target_name.lower()]
    
    if len(updated_pool) == initial_length:
        bot.send_message(message.chat.id, f"❌ Карта с именем '{target_name}' не обнаружена в файле cards.json", reply_markup=create_admin_menu())
    else:
        if save_data(updated_pool, 'cards'):
            bot.send_message(message.chat.id, f"✅ Карта **{target_name}** полностью стёрта из пула роллов.", reply_markup=create_admin_menu(), parse_mode="Markdown")
            logger.info(f"Администратор удалил карту: {target_name}")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при сохранении обновленного пула карт.", reply_markup=create_admin_menu())

# ------------------------------------------------------------------------------
# ПОДМОДУЛЬ: ИЗМЕНЕНИЕ (РЕДАКТИРОВАНИЕ) КАРТЫ
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "📝 Изменить карту")
def admin_edit_card_start(message):
    if not check_admin_permission(message.from_user): return
    msg = bot.send_message(message.chat.id, "📝 **РЕДАКТИРОВАНИЕ КАРТЫ**\n\nВведите точное имя футболиста для изменения параметров:", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, admin_edit_card_find)

def admin_edit_card_find(message):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Редактирование отменено.", reply_markup=create_admin_menu())
        return
    
    target_name = message.text.strip()
    cards_pool = load_data('cards')
    
    found_card = None
    for card in cards_pool:
        if card.get('name', '').lower() == target_name.lower():
            found_card = card
            break
            
    if not found_card:
        bot.send_message(message.chat.id, f"❌ Карточка '{target_name}' не найдена.", reply_markup=create_admin_menu())
        return
        
    msg = bot.send_message(
        message.chat.id, 
        f"Найдена карта: **{found_card['name']}**\nКлуб: {found_card.get('club')}\nПозиция: {found_card.get('position')}\n\nВведите новые звезды (1-5):",
        reply_markup=create_cancel_menu(),
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_edit_card_finalize, target_name)

def admin_edit_card_finalize(message, target_name):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=create_admin_menu())
        return
        
    try:
        new_stars = int(message.text.strip())
    except ValueError:
        new_stars = 1
        
    cards_pool = load_data('cards')
    for card in cards_pool:
        if card.get('name', '').lower() == target_name.lower():
            card['stars'] = new_stars
            break
            
    if save_data(cards_pool, 'cards'):
        bot.send_message(message.chat.id, f"✅ Звездность карты {target_name} успешно изменена на {new_stars} ⭐", reply_markup=create_admin_menu())
    else:
        bot.send_message(message.chat.id, "❌ Ошибка при изменении параметров карты.", reply_markup=create_admin_menu())

# ------------------------------------------------------------------------------
# ПОДМОДУЛЬ: УПРАВЛЕНИЕ СИСТЕМОЙ ПРОМОКОДОВ
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "🎟 +Промокод")
def admin_add_promo_step_1(message):
    if not check_admin_permission(message.from_user): return
    
    msg = bot.send_message(message.chat.id, "🎟 **ГЕНЕРАЦИЯ ПРОМОКОДА [ШАГ 1]**\n\nВведите кодовое слово промокода (английские буквы/цифры):", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, admin_add_promo_step_2_type, {})


def admin_add_promo_step_2_type(message, promo_wizard_data):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Создание промокода отменено.", reply_markup=create_admin_menu())
        return
        
    promo_wizard_data['code'] = message.text.strip().upper()
    
    type_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    type_markup.add("score", "rolls", "luck", "❌ Отмена")
    
    msg = bot.send_message(
        message.chat.id,
        f"🎟 **ГЕНЕРАЦИЯ ПРОМОКОДА [ШАГ 2]**\n\nКод: `{promo_wizard_data['code']}`\n\nВыберите тип награды:\n"
        f"— `score` — Очки на баланс счета\n"
        f"— `rolls` — Бонусные прокруты рулетки\n"
        f"— `luck` — Повышение множителя удачи",
        reply_markup=type_markup,
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_add_promo_step_3_val, promo_wizard_data)


def admin_add_promo_step_3_val(message, promo_wizard_data):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Создание промокода отменено.", reply_markup=create_admin_menu())
        return
        
    promo_wizard_data['type'] = message.text.strip().lower()
    
    msg = bot.send_message(
        message.chat.id,
        f"🎟 **ГЕНЕРАЦИЯ ПРОМОКОДА [ШАГ 3]**\n\nТип награды: `{promo_wizard_data['type']}`\n\n"
        f"Введите численное значение награды (например, 50000 для score, 10 для rolls, 3.5 для luck):",
        reply_markup=create_cancel_menu(),
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_add_promo_finalize, promo_wizard_data)


def admin_add_promo_finalize(message, promo_wizard_data):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Создание промокода отменено.", reply_markup=create_admin_menu())
        return
        
    raw_value = message.text.strip()
    code_key = promo_wizard_data['code']
    
    promos_dict = load_data('promos')
    promos_dict[code_key] = {
        "type": promo_wizard_data['type'],
        "value": float(raw_value) if promo_wizard_data['type'] == 'luck' else int(raw_value)
    }
    
    if save_data(promos_dict, 'promos'):
        bot.send_message(
            message.chat.id,
            f"✅ **ПРОМОКОД УСПЕШНО ЗАРЕГИСТРИРОВАН!**\n\n"
            f"🎟 Код: `{code_key}`\n"
            f"📊 Награда: `{promos_dict[code_key]['value']}` ({promo_wizard_data['type']})",
            reply_markup=create_admin_menu(),
            parse_mode="Markdown"
        )
        logger.info(f"Администратор создал промокод: {code_key}")
    else:
        bot.send_message(message.chat.id, "❌ Критическая ошибка записи конфигурации промокодов.", reply_markup=create_admin_menu())


@bot.message_handler(func=lambda m: m.text == "🗑 Удалить промокод")
def admin_delete_promo_start(message):
    if not check_admin_permission(message.from_user): return
    msg = bot.send_message(message.chat.id, "🗑 **УДАЛЕНИЕ ПРОМОКОДА**\n\nВведите текстовое название промокода для удаления:", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, admin_delete_promo_process)


def admin_delete_promo_process(message):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=create_admin_menu())
        return
        
    target_code = message.text.strip().upper()
    promos_dict = load_data('promos')
    
    if target_code in promos_dict:
        del promos_dict[target_code]
        if save_data(promos_dict, 'promos'):
            bot.send_message(message.chat.id, f"✅ Промокод `{target_code}` навсегда деактивирован и удален.", reply_markup=create_admin_menu(), parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ Не удалось сохранить изменения базы промокодов.", reply_markup=create_admin_menu())
    else:
        bot.send_message(message.chat.id, f"❌ Промокод `{target_code}` не найден в системе.", reply_markup=create_admin_menu(), parse_mode="Markdown")

# ------------------------------------------------------------------------------
# ПОДМОДУЛЬ: МОДЕРАЦИЯ ПОЛЬЗОВАТЕЛЕЙ (БАНЫ / РАЗБАНЫ)
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "🚫 Забанить")
def admin_ban_user_start(message):
    if not check_admin_permission(message.from_user): return
    msg = bot.send_message(
        message.chat.id, 
        "🚫 **БЛОКИРОВКА ДОСТУПА**\n\nВведите цифровой Telegram ID нарушителя или его текстовый юзернейм (без знака @):", 
        reply_markup=create_cancel_menu()
    )
    bot.register_next_step_handler(msg, admin_ban_user_process)


def admin_ban_user_process(message):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Операция бана прервана.", reply_markup=create_admin_menu())
        return
        
    input_ban_target = message.text.strip().lower()
    ban_list = load_data('bans')
    
    if input_ban_target not in ban_list:
        ban_list.append(input_ban_target)
        if save_data(ban_list, 'bans'):
            bot.send_message(message.chat.id, f"✅ Субъект **{input_ban_target}** занесен в черный список бота. Доступ заблокирован.", reply_markup=create_admin_menu(), parse_mode="Markdown")
            logger.warning(f"Администратор выдал бан для: {input_ban_target}")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка записи черного списка.", reply_markup=create_admin_menu())
    else:
        bot.send_message(message.chat.id, f"⚠️ Данный пользователь ({input_ban_target}) уже находится в бане.", reply_markup=create_admin_menu())


@bot.message_handler(func=lambda m: m.text == "✅ Разбанить")
def admin_unban_user_start(message):
    if not check_admin_permission(message.from_user): return
    msg = bot.send_message(message.chat.id, "✅ **РАЗБЛОКИРОВКА ДОСТУПА**\n\nВведите ID или юзернейм для амнистии:", reply_markup=create_cancel_menu())
    bot.register_next_step_handler(msg, admin_unban_user_process)


def admin_unban_user_process(message):
    if message.text == "❌ Отмена":
        bot.send_message(message.chat.id, "❌ Операция амнистии прервана.", reply_markup=create_admin_menu())
        return
        
    input_unban_target = message.text.strip().lower()
    ban_list = load_data('bans')
    
    if input_unban_target in ban_list:
        ban_list.remove(input_unban_target)
        if save_data(ban_list, 'bans'):
            bot.send_message(message.chat.id, f"✅ Пользователь **{input_unban_target}** успешно амнистирован и удален из черного списка.", reply_markup=create_admin_menu(), parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка сохранения базы банов.", reply_markup=create_admin_menu())
    else:
        bot.send_message(message.chat.id, f"❌ Пользователь '{input_unban_target}' не найден в структуре черного списка.", reply_markup=create_admin_menu())

# ------------------------------------------------------------------------------
# ПОДМОДУЛЬ: ПОЛНОЕ ОБНУЛЕНИЕ ВСЕЙ ИГРОВОЙ ВСЕЛЕННОЙ (HARD RESET)
# ------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.text == "🧨 Обнулить бота")
def admin_hard_reset_confirmation_1(message):
    if not check_admin_permission(message.from_user): return
    
    confirm_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    confirm_markup.add("🔥 ДА, СТЕРЕТЬ ВСЕ ДАННЫЕ", "❌ Отмена")
    
    msg = bot.send_message(
        message.chat.id,
        "🚨 **КРИТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ! HARD RESET!** 🚨\n\n"
        "Вы инициировали полную очистку игрового прогресса бота.\n"
        "Это сотрет все балансы игроков, рефералов, их коллекции карточек и составы!\n"
        "Вы абсолютно уверены в этом действии?",
        reply_markup=confirm_markup,
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_hard_reset_finalize)


def admin_hard_reset_finalize(message):
    if message.text == "🔥 ДА, СТЕРЕТЬ ВСЕ ДАННЫЕ":
        logger.critical(f"АДМИНИСТРАТОР {message.from_user.id} ЗАПУСТИЛ ПРОЦЕДУРУ HARD RESET!")
        
        # Полная очистка словарей данных пользователей, коллекций и составов
        empty_data_dictionary = {}
        
        save_data(empty_data_dictionary, 'users')
        save_data(empty_data_dictionary, 'colls')
        save_data(empty_data_dictionary, 'squads')
        
        bot.send_message(
            message.chat.id,
            "🧨 **БАЗА ДАННЫХ ИГРОКОВ УСПЕШНО УНИЧТОЖЕНА!**\n\n"
            "Все профили, очки, составы и альбомы коллекций стёрты до нуля.\n"
            "Пул доступных карт (`cards.json`) и промокоды остались нетронутыми.",
            reply_markup=create_admin_menu(),
            parse_mode="Markdown"
        )
    else:
        bot.send_message(message.chat.id, "❌ Глобальное обнуление отменено. Данные в безопасности.", reply_markup=create_admin_menu())

# ==============================================================================
# [14] ПРЕДОХРАНИТЕЛЬНЫЙ ДЕФОЛТНЫЙ ОБРАБОТЧИК НЕИЗВЕСТНОГО ТЕКСТА
# ==============================================================================

@bot.message_handler(func=lambda message: True)
def default_fallback_text_handler(message):
    """Отлавливает любые нераспознанные текстовые команды и мягко возвращает игрока в меню."""
    if check_ban_status(message.from_user):
        return
        
    logger.info(f"Неизвестный текстовый ввод от {message.from_user.id}: {message.text}")
    bot.send_message(
        message.chat.id,
        "❓ **Неизвестная команда.**\n\n"
        "Пожалуйста, используйте встроенные интерактивные кнопки графического меню "
        "для стабильного управления симулятором футбольных карточек.",
        reply_markup=create_main_menu(message.from_user.id),
        parse_mode="Markdown"
    )

# ==============================================================================
# [15] БЕЗКОНЕЧНЫЙ ЦИКЛ ОПРОСА СЕРВЕРОВ TELEGRAM (POLLING START)
# ==============================================================================

if __name__ == '__main__':
    logger.info("==================================================")
    logger.info(" СИСТЕМА УСПЕШНО ИНИЦИАЛИЗИРОВАНА И СКОМПИЛИРОВАНА")
    logger.info(" БОТ ФУТБОЛЬНЫХ КАРТОЧЕК ЗАПУСКАЕТСЯ В INFINITY_POLLING...")
    logger.info("==================================================")
    
    # Запуск бота в режиме игнорирования сетевых ошибок таймаута
    bot.infinity_polling(skip_pending=True)
