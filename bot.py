import logging
import asyncio
import csv
import io
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes, 
    ConversationHandler,
    CallbackQueryHandler
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import config
from database import db
import pytz
BELARUS_TZ = pytz.timezone('Europe/Minsk')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_debug.log'  # Добавляем запись в файл
)
logger = logging.getLogger(__name__)

# Состояния
INSTAGRAM_USERNAME = 1
ADMIN_MENU = 2
ADMIN_MARK_COUPON = 3 

# Эмодзи для оформления
EMOJIS = {
    'wheel': '🎡',
    'gift': '🎁',
    'star': '🌟',
    'snowman': '⛄',
    'snowflake': '❄️',
    'calendar': '📅',
    'stats': '📊',
    'users': '👥',
    'search': '🔍',
    'export': '📤',
    'back': '⬅️',
    'home': '🏠',
    'refresh': '🔄',
    'coupon': '🎫',
    'list': '📋',
    'clock': '⏰',
    'check': '✅',
    'cross': '❌'
}

async def show_active_coupons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /mycoupons - показать активные купоны пользователя"""
    # Проверка на None
    if not update or not update.effective_user:
        logger.error("update.effective_user is None в show_active_coupons")
        if update and update.message:
            await update.message.reply_text(
                "❌ Ошибка определения пользователя. Попробуйте снова."
            )
        return
    
    user = update.effective_user 
    
    if update.callback_query:
        user = update.callback_query.from_user
        message = update.callback_query.message
    elif update.message:
        user = update.message.from_user
        message = update.message
    else:
        logger.error("Не удалось получить message или user")
        return
    
    telegram_id = user.id
    
    # Получаем активные купоны
    active_coupons = db.get_active_coupons(telegram_id)
    user_stats = db.get_user_stats(telegram_id)
    
    if not active_coupons:
        # Если нет активных купонов
        message  = (
            f"{EMOJIS['coupon']} *Ваши купоны*\n\n"
            f"У вас пока нет активных купонов.\n\n"
            f"🎯 *Статистика:*\n"
            f"• Всего получено: {user_stats['total']}\n"
            f"• Использовано: {user_stats['used']}\n\n"
            f"🎡 Используйте /start чтобы получить новый купон!"
        )
        
        keyboard = [[
            InlineKeyboardButton(f"{EMOJIS['wheel']} Получить купон", callback_data="spin_wheel"),
            InlineKeyboardButton(f"{EMOJIS['stats']} Статистика", callback_data="show_stats")
        ]]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # Формируем сообщение с активными купонами
    message = f"{EMOJIS['coupon']} *ВАШИ АКТИВНЫЕ КУПОНЫ*\n\n"
    message += f"📊 *Статистика:*\n"
    message += f"• Активных: {len(active_coupons)}\n"
    message += f"• Всего получено: {user_stats['total']}\n"
    message += f"• Использовано: {user_stats['used']}\n\n"
    message += "=" * 30 + "\n\n"
    
    for i, coupon in enumerate(active_coupons, 1):
        # Парсим даты
        created_date = datetime.strptime(str(coupon['created_at']).split('.')[0], '%Y-%m-%d %H:%M:%S')
        valid_until_date = datetime.strptime(str(coupon['valid_until']).split('.')[0], '%Y-%m-%d %H:%M:%S')

        # Форматируем даты
        created_str = created_date.strftime('%d.%m.%Y')
        valid_until_str = valid_until_date.strftime('%d.%m.%Y')
        
        # Считаем сколько дней осталось
        current_date = datetime.now(BELARUS_TZ).date()
        valid_until_date_only = valid_until_date.date()

        # Подсчитываем количество дней ОСТАВШИХСЯ (включая сегодня)
        days_left = (valid_until_date_only - current_date).days + 1  # +1 чтобы включить сегодняшний день

        if days_left > 0:
            days_text = f"{days_left} дн."
        else:
            days_text = "истёк"
        
        # Эмодзи для срочности
        if days_left <= 1:
            time_emoji = "⏰"
        elif days_left <= 2:
            time_emoji = "⚠️"
        else:
            time_emoji = "🕒"
        
        message += (
            f"🎄 *Купон #{i}*\n"
            f"{EMOJIS['gift']} *Скидка:* {coupon['coupon']}\n"
            f"🔤 *Кодовое слово:* {coupon['code_word']}\n"
            f"📅 *Получен:* {created_str}\n"
            f"⏳ *Действует до:* {valid_until_str}\n"
            f"{time_emoji} *Осталось:* {days_text}\n"
        )
        
        # Разделитель между купонами
        if i < len(active_coupons):
            message += f"\n{'-'*25}\n\n"
    
    # Кнопки под сообщением
    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJIS['wheel']} Получить новый", callback_data="spin_wheel"),
            InlineKeyboardButton(f"{EMOJIS['refresh']} Обновить", callback_data="refresh_coupons")
        ],
        [
            InlineKeyboardButton(f"{EMOJIS['stats']} Статистика", callback_data="show_stats"),
            InlineKeyboardButton(f"{EMOJIS['gift']} Правила", callback_data="show_rules")
        ]
    ]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start - точка входа для всех пользователей"""
    
    # Безопасное получение пользователя
    if update.callback_query:
        user = update.callback_query.from_user
        message = update.callback_query.message
    elif update.message:
        user = update.message.from_user
        message = update.message
    else:
        logger.error("Не удалось получить пользователя в /start")
        return
    
    telegram_id = user.id
    
    # Проверяем, новый ли пользователь
    if not db.user_exists(telegram_id):
        # НОВЫЙ ПОЛЬЗОВАТЕЛЬ - просим Instagram
        await message.reply_text(
            f"{EMOJIS['wheel']} *Привет, {user.first_name}!* 👋\n\n"
            "🎄 *Добро пожаловать в Новогоднее Колесо Удачи!* 🎄\n\n"
            "   *Для получения первого купона отправьте ваш Instagram username (без @):*",
            parse_mode='Markdown'
        )
        return INSTAGRAM_USERNAME
    else:
        # СУЩЕСТВУЮЩИЙ ПОЛЬЗОВАТЕЛЬ - показываем меню
        await show_user_menu(update, context)
        return ConversationHandler.END

async def handle_instagram_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка Instagram username для новых пользователей с автоматическим запуском spin"""
    
    username = update.message.text.strip()
    user = update.effective_user
    
    if len(username) > 100:
        await update.message.reply_text(
            "Имя пользователя слишком длинное. Пожалуйста, введите корректный Instagram username:"
        )
        return INSTAGRAM_USERNAME
    
    # Сохраняем Instagram в контекст
    context.user_data['instagram'] = username
    
    # Создаем fake update для вызова spin_wheel_handler
    if update.callback_query:
        query = update.callback_query
        fake_update = Update(
            update_id=update.update_id,
            callback_query=query
        )
    else:
        # Создаем Message с пользователем
        from telegram import Message
        
        fake_message = Message(
            message_id=update.message.message_id,
            date=update.message.date,
            chat=update.message.chat,
            from_user=user,
            text=""
        )
        # Устанавливаем бота
        fake_message._bot = update.message._bot
        
        fake_update = Update(
            update_id=update.update_id,
            message=fake_message
        )
    
    # Запускаем spin_wheel_handler с переданным username
    await spin_wheel_handler(fake_update, context, username)
    
    return ConversationHandler.END

async def show_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню для существующего пользователя"""
    user = update.effective_user
    telegram_id = user.id
    
    # Проверяем, можно ли крутить сегодня
    # can_spin_today = not db.has_user_played_today(telegram_id)\
    can_spin_today = True
    
    # Получаем последний использованный Instagram
    last_instagram = db.get_last_instagram(telegram_id)
    
    if can_spin_today:
        # Можно крутить сегодня - предлагаем крутить
        message = (
            f"{EMOJIS['wheel']} *С возвращением, {user.first_name}!*\n\n"
            f"*Ваш Instagram:* @{last_instagram}\n\n"
            "*Сегодня вы можете:*\n"
            "1. 🎡 Крутить колесо (новый купон)\n"
            "2. 🎫 Смотреть активные купоны\n"
            "3. 📊 Посмотреть статистику\n\n"
            "🎄 *Выберите действие:*"
        )
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['wheel']} Крутить колесо", callback_data="spin_wheel")],
            [
                InlineKeyboardButton(f"{EMOJIS['coupon']} Мои купоны", callback_data="show_my_coupons"),
                InlineKeyboardButton(f"{EMOJIS['stats']} Статистика", callback_data="show_stats")
            ]
        ]
    else:
        # Уже крутил сегодня - только просмотр
        message = (
            f"{EMOJIS['wheel']} *С возвращением, {user.first_name}!*\n\n"
            f"*Ваш Instagram:* @{last_instagram}\n\n"
            "*Вы уже крутили колесо сегодня.*\n"
            "Новый купон будет доступен завтра!\n\n"
            "*Сегодня вы можете:*\n"
            "1. 🎫 Смотреть активные купоны\n"
            "2. 📊 Посмотреть статистику\n"
            "3. ℹ️ Посмотреть правила\n\n"
            "🎄 *Выберите действие:*"
        )
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['coupon']} Мои купоны", callback_data="show_my_coupons")],
            [
                InlineKeyboardButton(f"{EMOJIS['stats']} Статистика", callback_data="show_stats"),
                InlineKeyboardButton(f"{EMOJIS['gift']} Правила", callback_data="show_rules")
            ]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.message:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def spin_wheel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /spin для существующих пользователей"""
    
    # Безопасное получение пользователя
    if update.callback_query:
        user = update.callback_query.from_user
        message = update.callback_query.message
    elif update.message:
        user = update.message.from_user
        message = update.message
    else:
        return
    
    telegram_id = user.id
    
    # Проверяем, существует ли пользователь
    if not db.user_exists(telegram_id):
        await message.reply_text(
            "Вы еще не зарегистрированы! Используйте /start для начала.",
            parse_mode='Markdown'
        )
        return
    
    # Проверяем, можно ли крутить сегодня
    if db.has_user_played_today(telegram_id):
        await message.reply_text(
            f"⏳ *Вы уже крутили колесо сегодня!*\n\n"
            f"Новый купон будет доступен завтра.\n"
            f"Используйте /mycoupons чтобы посмотреть активные купоны.",
            parse_mode='Markdown'
        )
        return
    
    # Запускаем spin_wheel_handler
    await spin_wheel_handler(update, context)

async def spin_wheel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str = None):
    """Универсальный обработчик кручения колеса (для новых и существующих)"""
    
    # Получаем пользователя
    if update.callback_query:
        user = update.callback_query.from_user
        message_func = update.callback_query.edit_message_text
        original_message = update.callback_query.message
        chat_id = update.callback_query.message.chat_id
    elif update.message:
        user = update.message.from_user
        message_func = update.message.reply_text
        original_message = update.message
        chat_id = update.message.chat_id
    else:
        return
    
    telegram_id = user.id
    
    # Если username не передан (существующий пользователь), берем из базы
    if not username:
        username = db.get_last_instagram(telegram_id)
    
    # Симуляция кручения колеса с анимацией
    wheel_message = await original_message.reply_text(
        f"{EMOJIS['wheel']} *Крутим новогоднее колесо...*\n"
        "🎄🎁🌟⛄❄️🎄🎁🌟⛄❄️"
    )
    
    # Анимация кручения
    wheel_frames = [
        "🎄...🎁...🌟...⛄...❄️",
        "❄️...🎄...🎁...🌟...⛄",
        "⛄...❄️...🎄...🎁...🌟",
        "🌟...⛄...❄️...🎄...🎁",
        "🎁...🌟...⛄...❄️...🎄"
    ]
    
    for frame in wheel_frames:
        await wheel_message.edit_text(f"{EMOJIS['wheel']} *Крутим новогоднее колесо...*\n{frame}")
        await asyncio.sleep(0.5)
    
    await asyncio.sleep(1)
    await wheel_message.edit_text(f"{EMOJIS['wheel']} *Колесо остановилось!*")
    await asyncio.sleep(0.5)
    
    # Генерация купона
    coupon_data = db.generate_coupon()
    save_result = db.save_coupon(telegram_id, username, coupon_data)
    
    # Форматирование дат
    created_date = save_result['created_at'].astimezone(BELARUS_TZ).strftime("%d.%m.%Y")
    valid_until_date = save_result['valid_until'].astimezone(BELARUS_TZ).strftime("%d.%m.%Y")
    
    # Сообщение с результатом
    result_message = (
        f"{coupon_data['emoji']} *🎉 ПОЗДРАВЛЯЕМ! 🎉*\n\n"
        f"✨ *Ваш новогодний подарок:*\n"
        f"📊 *Скидка:* {coupon_data['coupon']}\n"
        f"🎭 *Кодовое слово:* {coupon_data['code_word']}\n"
        f"📅 *Действует:* с {created_date} до {valid_until_date}\n"
        f"📱 *Instagram:* @{username}\n\n"
        f"🎄 *Как использовать:*\n"
        f"1. Сделайте заказ\n"
        f"2. Назовите кодовое слово\n"
        f"3. Получите скидку!\n\n"
        f"⭐ *Важная информация:*\n"
        f"• Купон действует 3 дня\n"
        f"• Один купон на один заказ\n"
        f"• Не передавайте кодовое слово другим\n\n"
        f"{EMOJIS['gift']} *Счастливого Нового Года!*"
    )

    # Отправляем результат
    if context and hasattr(context, 'bot'):
        await context.bot.send_message(
            chat_id=chat_id,
            text=result_message,
            parse_mode='Markdown'
        )
    else:
        await original_message.reply_text(result_message, parse_mode='Markdown')
    
    # Кнопки для быстрого доступа
    reminder_keyboard = [[
        InlineKeyboardButton(f"{EMOJIS['coupon']} Мои купоны", callback_data="show_my_coupons"),
        InlineKeyboardButton(f"{EMOJIS['stats']} Статистика", callback_data="show_stats")
    ]]
    
    reminder_message = (
        f"📋 *Что дальше?*\n"
        f"• Используйте /mycoupons чтобы посмотреть все купоны\n"
        f"• Новый купон - завтра!\n"
        f"• Удачных покупок!"
    )
    
    if context and hasattr(context, 'bot'):
        await context.bot.send_message(
            chat_id=chat_id,
            text=reminder_message,
            reply_markup=InlineKeyboardMarkup(reminder_keyboard),
            parse_mode='Markdown'
        )
    else:
        await original_message.reply_text(
            reminder_message,
            reply_markup=InlineKeyboardMarkup(reminder_keyboard),
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text(
        "Операция отменена. Используйте /start для начала."
    )
    return ConversationHandler.END

# АДМИН КОМАНДЫ
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель (команда /admin)"""
    user = update.effective_user
    
    if str(user.id) != config.ADMIN_ID:
        await update.message.reply_text("⛔ Доступ запрещен.")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJIS['stats']} Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(f"{EMOJIS['users']} Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(f"{EMOJIS['export']} Экспорт", callback_data="admin_export")],
        [InlineKeyboardButton(f"{EMOJIS['check']} Пометить купон", callback_data="admin_mark_used")],
        [InlineKeyboardButton(f"{EMOJIS['refresh']} Обновить", callback_data="admin_refresh")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⚙️ *Админ-панель*\n\n"
        f"Бот: {config.BOT_NAME}\n"
        f"Описание: {config.BOT_DESCRIPTION}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback для админ-панели"""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"Admin callback received: {query.data}")
    
    if query.data == "admin_stats":
        await show_admin_stats(query=query)
    elif query.data == "admin_users":
        # Показываем первую страницу пользователей
        await show_admin_users(query, page=0)
    elif query.data.startswith("admin_users_page_"):
        # Обработка пагинации
        try:
            page_num = int(query.data.split("_")[-1])
            await show_admin_users(query, page=page_num)
        except (ValueError, IndexError):
            await show_admin_users(query, page=0)
    elif query.data == "admin_export":
        await export_data(query)
    elif query.data == "admin_mark_used":
        logger.info("Admin wants to mark coupon as used")
        await query.edit_message_text(
            f"{EMOJIS['check']} *Пометить купон использованным*\n\n"
            f"Отправьте данные в формате:\n"
            f"`instagram_username скидка`\n\n"
            f"*Пример:*\n"
            f"`username123 15%`\n\n"
            f"Бот найдет активный купон этого пользователя с указанной скидкой "
            f"и пометит один любой купон как использованный.",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_mark_coupon'] = True
        return ADMIN_MARK_COUPON
    elif query.data == "admin_refresh":
        await show_admin_menu(update, context)
    elif query.data == "back_to_admin":
        await show_admin_menu(update, context)
    
    return ADMIN_MENU

async def handle_admin_mark_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка пометки купона использованным"""

    logger.info(f"handle_admin_mark_coupon called with text: {update.message.text}")
    
    input_text = update.message.text.strip()

    # Парсим ввод
    parts = input_text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Неверный формат. Используйте: `instagram_username скидка`\n"
            "Пример: `username123 15%`",
            parse_mode='Markdown'
        )
        return ADMIN_MARK_COUPON
    
    instagram = parts[0].replace('@', '')  # Убираем @ если есть
    coupon_value = parts[1]
    
    # Добавляем % если его нет
    if not coupon_value.endswith('%'):
        coupon_value = coupon_value + '%'
    
    logger.info(f"Searching for coupon: instagram={instagram}, coupon={coupon_value}")
    
    # Ищем активный купон
    result = db.mark_coupon_used_by_instagram(instagram, coupon_value)
    
    if result['success']:
        message = (
            f"{EMOJIS['check']} *Купон отмечен использованным!*\n\n"
            f"👤 Instagram: @{instagram}\n"
            f"🎁 Скидка: {coupon_value}\n"
            f"📅 Дата создания: {result['created_at']}\n"
            f"🏷️ ID купона: {result['coupon_id']}\n\n"
            f"✅ Купон успешно помечен как использованный."
        )
    else:
        message = (
            f"{EMOJIS['cross']} *Не удалось найти активный купон*\n\n"
            f"👤 Instagram: @{instagram}\n"
            f"🎁 Скидка: {coupon_value}\n\n"
            f"*Возможные причины:*\n"
            f"1. Пользователь не найден\n"
            f"2. Нет активных купонов с такой скидкой\n"
            f"3. Все купоны уже использованы\n"
            f"4. Купоны истекли"
        )
    
    await update.message.reply_text(message, parse_mode='Markdown')
    
    # Очищаем состояние и возвращаем в админ-меню
    context.user_data['awaiting_mark_coupon'] = False
    
    # Возвращаем кнопку для возврата в админ-меню
    keyboard = [[
        InlineKeyboardButton(f"{EMOJIS['back']} В админ-меню", callback_data="back_to_admin")
    ]]
    
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ADMIN_MENU

async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать админ-меню (для callback)"""
    query = update.callback_query
    user = query.from_user
    
    if str(user.id) != config.ADMIN_ID:
        await query.edit_message_text("⛔ Доступ запрещен.")
        return
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJIS['stats']} Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(f"{EMOJIS['users']} Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(f"{EMOJIS['export']} Экспорт", callback_data="admin_export")],
        [InlineKeyboardButton(f"{EMOJIS['check']} Пометить купон", callback_data="admin_mark_used")],
        [InlineKeyboardButton(f"{EMOJIS['refresh']} Обновить", callback_data="admin_refresh")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"⚙️ *Админ-панель*\n\n"
        f"Бот: {config.BOT_NAME}\n"
        f"Описание: {config.BOT_DESCRIPTION}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_admin_stats(query=None, update=None, context=None):
    """Показать статистику админа"""
    # Определяем откуда вызываем
    if query:
        message = query.message
    elif update and update.callback_query:
        query = update.callback_query
        await query.answer()
        message = query.message
    else:
        return
    
    stats = db.get_admin_stats()
    
    message_text = f"{EMOJIS['stats']} *Статистика бота*\n\n"
    message_text += f"📊 *Общая статистика:*\n"
    message_text += f"• Всего купонов: {stats['total_coupons']}\n"
    message_text += f"• Уникальных пользователей: {stats['unique_users']}\n"
    message_text += f"• Купонов сегодня: {stats['today_coupons']}\n\n"
    
    message_text += f"🎯 *Распределение купонов:*\n"
    for item in stats['coupon_distribution']:
        percentage = (item['count'] / stats['total_coupons'] * 100) if stats['total_coupons'] > 0 else 0
        coupon_config = config.COUPON_CONFIG.get(item['coupon'], {})
        code_word = coupon_config.get('code_word', 'N/A')
        message_text += f"• {item['coupon']} ({code_word}): {item['count']} ({percentage:.1f}%)\n"
    
    message_text += f"\n👥 *Топ пользователей:*\n"
    for i, user in enumerate(stats['top_users'][:5], 1):
        message_text += f"{i}. @{user['username'] or 'N/A'} - {user['total_spins']} спинов\n"
    
    keyboard = [[
        InlineKeyboardButton(f"{EMOJIS['back']} Назад", callback_data="back_to_admin"),
        InlineKeyboardButton(f"{EMOJIS['refresh']} Обновить", callback_data="admin_stats")
    ]]
    
    try:
        if query:
            await query.edit_message_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения: {e}")
        # Если не удалось отредактировать, отправляем новое сообщение
        if message:
            await message.reply_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

async def show_admin_users(query, page=0):
    """Показать пользователей с активными купонами с пагинацией"""
    try:
        users = db.get_all_users()
        
        if not users:
            await query.edit_message_text("Пользователей нет.")
            return
        
        # Настройки пагинации
        users_per_page = 10
        total_pages = (len(users) + users_per_page - 1) // users_per_page
        current_page = page
        start_idx = current_page * users_per_page
        end_idx = min(start_idx + users_per_page, len(users))
        
        message = f"{EMOJIS['users']} *Все пользователи:*\n"
        message += f"Страница {current_page + 1} из {total_pages}\n\n"
        
        for i, user in enumerate(users[start_idx:end_idx], start_idx + 1):
            # Получаем активные купоны пользователя
            active_coupons = db.get_active_coupons(user['telegram_id'])
            
            message += (
                f"{i}. *ID:* {user['telegram_id']}\n"
                f"   👤 Instagram: @{user['username'] or 'N/A'}\n"
                f"   📊 Всего купонов: {user['total_coupons']}\n"
            )
            
            if active_coupons:
                message += f"   🎁 *Активные купоны:*\n"
                for coupon in active_coupons[:3]:  # Показываем до 3 активных купонов
                    created_date = datetime.strptime(str(coupon['created_at']).split('.')[0], '%Y-%m-%d %H:%M:%S')
                    valid_until_date = datetime.strptime(str(coupon['valid_until']).split('.')[0], '%Y-%m-%d %H:%M:%S')
                    
                    message += (
                        f"      • {coupon['coupon']} (с {created_date.strftime('%d.%m')} по {valid_until_date.strftime('%d.%m')})\n"
                    )
                
                if len(active_coupons) > 3:
                    message += f"      ... и еще {len(active_coupons) - 3} активных\n"
            else:
                message += f"   📭 Нет активных купонов\n"
            
            message += f"{'-'*40}\n"
        
        # Создаем клавиатуру с кнопками пагинации
        keyboard = []
        
        # Кнопки навигации
        nav_buttons = []
        
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton(f"⬅️ Предыдущая", callback_data=f"admin_users_page_{current_page - 1}"))
        
        if current_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(f"Следующая ➡️", callback_data=f"admin_users_page_{current_page + 1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Основные кнопки
        keyboard.append([
            InlineKeyboardButton(f"{EMOJIS['back']} Назад", callback_data="back_to_admin"),
            InlineKeyboardButton(f"{EMOJIS['refresh']} Обновить", callback_data="admin_users_page_0")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка в show_admin_users: {e}")
        await query.message.reply_text(
            f"❌ Ошибка при загрузке пользователей: {e}",
            parse_mode='Markdown'
        )

async def export_data(query):
    """Экспорт данных"""
    data = db.export_data()
    
    # Создаем CSV файл с купонами с UTF-8 BOM для Excel
    coupons_csv = io.BytesIO()  # Изменяем на BytesIO
    coupons_writer = csv.writer(io.StringIO(), delimiter=',', quoting=csv.QUOTE_MINIMAL)
    
    # Создаем список строк для записи
    coupons_lines = []
    
    # Заголовки для купонов с BOM
    header = ['Дата создания', 'Пользователь', 'Instagram', 
              'Скидка', 'Кодовое слово', 'Действует по', 'Использован']
    
    # Добавляем UTF-8 BOM для корректного отображения в Excel
    coupons_lines.append('\ufeff' + ','.join(header))
    
    for coupon in data['coupons']:
        # Экранируем значения
        created_at = str(coupon['created_at']).replace(',', ' ')
        user_name = str(coupon['user_name']).replace(',', ' ')
        instagram = str(coupon['instagram']).replace(',', ' ')
        coupon_code = str(coupon['coupon']).replace(',', ' ')
        code_word = str(coupon['code_word']).replace(',', ' ')
        valid_until = str(coupon['valid_until']).replace(',', ' ')
        used = str(coupon['used']).replace(',', ' ')
        
        line = f'"{created_at}","{user_name}","{instagram}","{coupon_code}","{code_word}","{valid_until}","{used}"'
        coupons_lines.append(line)
    
    # Объединяем строки
    coupons_content = '\n'.join(coupons_lines)
    
    # Создаем CSV файл с пользователями с UTF-8 BOM
    users_lines = []
    
    # Заголовки для пользователей с BOM
    header = ['Telegram ID', 'Username', 'Имя', 'Фамилия', 
              'Дата регистрации', 'Всего спинов']
    
    users_lines.append('\ufeff' + ','.join(header))
    
    for user in data['users']:
        # Экранируем значения
        telegram_id = str(user['telegram_id']).replace(',', ' ')
        username = str(user['username'] or '').replace(',', ' ')
        first_name = str(user['first_name'] or '').replace(',', ' ')
        last_name = str(user['last_name'] or '').replace(',', ' ')
        joined_at = str(user['joined_at']).replace(',', ' ')
        total_spins = str(user['total_spins']).replace(',', ' ')
        
        line = f'"{telegram_id}","{username}","{first_name}","{last_name}","{joined_at}","{total_spins}"'
        users_lines.append(line)
    
    # Объединяем строки
    users_content = '\n'.join(users_lines)
    
    # Отправляем файлы
    await query.message.reply_document(
        document=io.BytesIO(coupons_content.encode('utf-8-sig')),  # utf-8-sig добавляет BOM
        filename='coupons_export.csv',
        caption="📤 Экспорт купонов (кодировка UTF-8)"
    )
    
    await query.message.reply_document(
        document=io.BytesIO(users_content.encode('utf-8-sig')),  # utf-8-sig добавляет BOM
        filename='users_export.csv',
        caption="📤 Экспорт пользователей (кодировка UTF-8)"
    )
    
    # Возвращаем в админ-панель
    keyboard = [[
        InlineKeyboardButton(f"{EMOJIS['back']} Назад", callback_data="back_to_admin")
    ]]
    
    await query.edit_message_text(
        "✅ Экспорт завершен!\n\n"
        "Файлы отправлены выше.\n",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        f"{EMOJIS['wheel']} *Новогоднее Колесо Удачи*\n\n"
        f"🎯 *Доступные команды:*\n"
        f"/start - Начать или проверить купоны\n"
        f"/mycoupons - Мои активные купоны\n"
        f"/help - Эта справка\n\n"
        
        f"🎁 *Как это работает:*\n"
        f"1. Крутите колесо раз в день\n"
        f"2. Получаете скидку и кодовое слово\n"
        f"3. Используете кодовое слово при заказе\n"
        f"4. Получаете скидку!\n\n"
        
        f"🎄 *Кодовые слова:*\n"
        f"• 🎁 Подарок - 5% скидка\n"
        f"• 🌟 Сочельник - 10% скидка\n"
        f"• ⛄ Снеговик - 15% скидка\n"
        f"• ❄️ Снегурочка - 20% скидка\n\n"
        
        f"📅 *Правила:*\n"
        f"• Один купон в день на человека\n"
        f"• Купон действует 3 дня\n"
        f"• Кодовое слово не передавать другим\n"
        f"• Используйте /mycoupons для просмотра\n\n"
        
        f"🎉 *Счастливого Нового Года!*"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

# CALLBACK HANDLERS ДЛЯ ПОЛЬЗОВАТЕЛЕЙ
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback для пользовательских кнопок"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "show_my_coupons":
        class SimpleUpdate:
            def __init__(self, query):
                self.callback_query = query
                self.effective_user = query.from_user
                self.effective_message = query.message
                self.message = query.message
                self.update_id = update.update_id,
        
        simple_update = SimpleUpdate(query)
        await show_active_coupons(simple_update, context)
        
    elif query.data == "show_stats":
        stats = db.get_user_stats(user_id)
        
        message = f"{EMOJIS['stats']} *Ваша статистика:*\n\n"
        message += f"🎯 Всего купонов: {stats['total']}\n"
        message += f"✅ Использовано: {stats['used']}\n"
        message += f"🔄 Активных: {stats['active']}\n"
        
        # Кнопки
        keyboard = [[
            InlineKeyboardButton(f"{EMOJIS['coupon']} Мои купоны", callback_data="show_my_coupons"),
            InlineKeyboardButton(f"{EMOJIS['wheel']} Крутить", callback_data="spin_wheel")
        ]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    elif query.data == "spin_wheel":
        # Проверяем, можно ли крутить сегодня
        if db.has_user_played_today(user_id):
            await query.edit_message_text(
                "Вы уже получали купон сегодня!\n"
                "Используйте /mycoupons чтобы посмотреть активные купоны.\n"
                "Новый купон будет доступен завтра.",
                parse_mode='Markdown'
            )
        else:
            await spin_wheel_handler(update, context)
    
    elif query.data == "refresh_coupons":
        class SimpleUpdate:
            def __init__(self, query):
                self.callback_query = query
                self.effective_user = query.from_user
                self.effective_message = query.message
                self.message = query.message
                self.update_id = update.update_id,
        
        simple_update = SimpleUpdate(query)
        await show_active_coupons(simple_update, context)
    
    elif query.data == "show_rules":
        rules_text = (
            f"{EMOJIS['check']} *Правила использования купонов:*\n\n"
            f"1. Один купон = один заказ\n"
            f"2. Купон действует 3 дня с момента получения\n"
            f"3. Кодовое слово нельзя передавать другим\n"
            f"4. Можно получить один купон в день\n"
            f"5. Купон нельзя обменять или вернуть\n"
            f"6. Купон привязан к вашему Instagram\n\n"
            f"{EMOJIS['cross']} *Купон недействителен если:*\n"
            f"• Истек срок действия\n"
            f"• Уже использован\n"
            f"• Передан другому человеку\n"
            f"• Instagram не совпадает\n\n"
            f"🎄 Приятных покупок!"
        )
        
        keyboard = [[
            InlineKeyboardButton(f"{EMOJIS['coupon']} Мои купоны", callback_data="show_my_coupons"),
            InlineKeyboardButton(f"{EMOJIS['back']} Назад", callback_data="back_to_coupons")
        ]]
        
        await query.edit_message_text(
            rules_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif query.data == "back_to_coupons":
        class SimpleUpdate:
            def __init__(self, query):
                self.callback_query = query
                self.effective_user = query.from_user
                self.effective_message = query.message
                self.message = query.message
                self.update_id = update.update_id,
        
        simple_update = SimpleUpdate(query)
        await show_active_coupons(simple_update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла ошибка. Пожалуйста, попробуйте позже."
        )

def main():
    """Запуск бота"""
    # Создание Application
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Conversation Handler для ПОЛЬЗОВАТЕЛЕЙ (только /start)
    user_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            INSTAGRAM_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_instagram_username)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Упрощенный Conversation Handler для АДМИНОВ
    admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('admin', admin)],
        states={
            ADMIN_MENU: [
                CallbackQueryHandler(admin_callback_handler)
            ],
            ADMIN_MARK_COUPON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_mark_coupon)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Регистрируем все хендлеры
    application.add_handler(user_conv_handler)
    application.add_handler(admin_conv_handler)
    
    # Обычные команды (не в conversation)
    application.add_handler(CommandHandler('mycoupons', show_active_coupons))
    application.add_handler(CommandHandler('spin', spin_wheel_command))
    application.add_handler(CommandHandler('help', help_command))
    
    # Обработчики callback - отдельно для админа
    application.add_handler(CallbackQueryHandler(
        admin_callback_handler,
        pattern="^(admin_stats|admin_users|admin_users_page_.*|admin_export|admin_mark_used|admin_refresh|back_to_admin)$"
    ))
    # Обработчики callback для пользователей
    application.add_handler(CallbackQueryHandler(
        button_callback_handler, 
        pattern="^(show_my_coupons|show_stats|spin_wheel|refresh_coupons|show_rules|back_to_coupons)$"
    ))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запуск бота
    print(f"🚀 {config.BOT_NAME} запускается в {datetime.now()}...")
    
    # Запуск polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()