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

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния
INSTAGRAM_USERNAME = 1
ADMIN_MENU = 2

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
        days_left = (valid_until_date - datetime.now()).days
        days_text = f"{days_left} дн." if days_left > 0 else "сегодня"
        
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
    created_date = save_result['created_at'].strftime("%d.%m.%Y")
    valid_until_date = save_result['valid_until'].strftime("%d.%m.%Y")
    
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
        return
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJIS['stats']} Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(f"{EMOJIS['users']} Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(f"{EMOJIS['search']} Поиск", callback_data="admin_search")],
        [InlineKeyboardButton(f"{EMOJIS['export']} Экспорт", callback_data="admin_export")],
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
    
    if query.data == "admin_stats":
        await show_admin_stats(query=query)
    elif query.data == "admin_users":
        await show_admin_users(query)
    elif query.data == "admin_search":
        await query.edit_message_text(
            "🔍 *Поиск купонов*\n\n"
            "Отправьте username, купон или кодовое слово для поиска:",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_search'] = True
    elif query.data == "admin_export":
        await export_data(query)
    elif query.data == "admin_refresh":
        await show_admin_menu(update, context)
    elif query.data == "back_to_admin":
        await show_admin_menu(update, context)
    
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
        [InlineKeyboardButton(f"{EMOJIS['search']} Поиск", callback_data="admin_search")],
        [InlineKeyboardButton(f"{EMOJIS['export']} Экспорт", callback_data="admin_export")],
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

async def show_admin_users(query):
    """Показать пользователей"""
    try:
        users = db.get_all_users()
        
        if not users:
            await query.edit_message_text("Пользователей нет.")
            return
        
        message = f"{EMOJIS['users']} *Все пользователи:*\n\n"
        
        for i, user in enumerate(users[:10], 1):  # Показываем первые 10
            joined_date = datetime.strptime(str(user['joined_at']).split('.')[0], '%Y-%m-%d %H:%M:%S')
            message += (
                f"{i}. ID: {user['telegram_id']}\n"
                f"   👤: @{user['username'] or 'N/A'}\n"
                f"   📅: {joined_date}\n"
                f"   🎯: {user['total_spins']} спинов\n"
                f"   🎁: {user['total_coupons']} купонов\n"
                f"{'-'*30}\n"
            )
        
        if len(users) > 10:
            message += f"\n... и еще {len(users) - 10} пользователей"
        
        keyboard = [[
            InlineKeyboardButton(f"{EMOJIS['back']} Назад", callback_data="back_to_admin"),
            InlineKeyboardButton(f"{EMOJIS['export']} Экспорт", callback_data="admin_export")
        ]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка в show_admin_users: {e}")
        # Отправляем новое сообщение в случае ошибки
        await query.message.reply_text(
            f"❌ Ошибка при загрузке пользователей: {e}",
            parse_mode='Markdown'
        )

async def handle_admin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка поиска админом"""
    if not context.user_data.get('awaiting_search'):
        return ADMIN_MENU
    
    query_text = update.message.text.strip()
    results = db.search_coupons(query_text)
    
    if not results:
        await update.message.reply_text("Ничего не найдено.")
        context.user_data['awaiting_search'] = False
        return ADMIN_MENU
    
    message = f"🔍 *Результаты поиска: '{query_text}'*\n\n"
    
    for i, coupon in enumerate(results[:10], 1):
        created_date = datetime.strptime(str(coupon['created_at']).split('.')[0], '%Y-%m-%d %H:%M:%S')
        valid_until_date = datetime.strptime(str(coupon['valid_until']).split('.')[0], '%Y-%m-%d %H:%M:%S')
        
        message += (
            f"{i}. 🎁 {coupon['coupon']} ({coupon['code_word']})\n"
            f"   👤: @{coupon['username']}\n"
            f"   📅: {created_date}\n"
            f"   ⏳: до {valid_until_date}\n"
            f"   🏷️: {'✅ Использован' if coupon['used'] else '🔄 Активен'}\n"
            f"{'-'*30}\n"
        )
    
    if len(results) > 10:
        message += f"\n... и еще {len(results) - 10} результатов"
    
    await update.message.reply_text(message, parse_mode='Markdown')
    context.user_data['awaiting_search'] = False
    return ADMIN_MENU

async def export_data(query):
    """Экспорт данных"""
    data = db.export_data()
    
    # Создаем CSV файл с купонами
    coupons_csv = io.StringIO()
    coupons_writer = csv.writer(coupons_csv)
    
    # Заголовки для купонов
    coupons_writer.writerow([
        'Дата создания', 'Пользователь', 'Instagram', 
        'Скидка', 'Кодовое слово', 'Действует до', 'Использован'
    ])
    
    for coupon in data['coupons']:
        coupons_writer.writerow([
            coupon['created_at'],
            coupon['user_name'],
            coupon['instagram'],
            coupon['coupon'],
            coupon['code_word'],
            coupon['valid_until'],
            coupon['used']
        ])
    
    # Создаем CSV файл с пользователями
    users_csv = io.StringIO()
    users_writer = csv.writer(users_csv)
    
    # Заголовки для пользователей
    users_writer.writerow([
        'Telegram ID', 'Username', 'Имя', 'Фамилия', 
        'Дата регистрации', 'Всего спинов'
    ])
    
    for user in data['users']:
        users_writer.writerow([
            user['telegram_id'],
            user['username'],
            user['first_name'],
            user['last_name'],
            user['joined_at'],
            user['total_spins']
        ])
    
    # Отправляем файлы
    await query.message.reply_document(
        document=io.BytesIO(coupons_csv.getvalue().encode()),
        filename='coupons_export.csv',
        caption="📤 Экспорт купонов"
    )
    
    await query.message.reply_document(
        document=io.BytesIO(users_csv.getvalue().encode()),
        filename='users_export.csv',
        caption="📤 Экспорт пользователей"
    )
    
    # Возвращаем в админ-панель
    keyboard = [[
        InlineKeyboardButton(f"{EMOJIS['back']} Назад", callback_data="back_to_admin")
    ]]
    
    await query.edit_message_text(
        "✅ Экспорт завершен!\n\n"
        "Файлы отправлены выше.",
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
    
    # Conversation Handler для основного потока
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            INSTAGRAM_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_instagram_username)
            ],
            ADMIN_MENU: [
                CallbackQueryHandler(admin_callback_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_search)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Регистрация обработчиков команд
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('admin', admin))
    application.add_handler(CommandHandler('mycoupons', show_active_coupons))
    application.add_handler(CommandHandler('spin', spin_wheel_command))
    application.add_handler(CommandHandler('help', help_command))
    
    # Обработчики callback
    application.add_handler(CallbackQueryHandler(
        button_callback_handler, 
        pattern="^(show_my_coupons|show_stats|spin_wheel|refresh_coupons|show_rules|back_to_coupons)$"
    ))
    application.add_handler(CallbackQueryHandler(
        admin_callback_handler,
        pattern="^(admin_stats|admin_users|admin_search|admin_export|admin_refresh|back_to_admin)$"
    ))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запуск бота
    print(f"🚀 {config.BOT_NAME} запускается...")
    print(f"🤖 ID администратора: {config.ADMIN_ID}")
    print(f"🎯 Доступные команды: /start, /mycoupons, /help, /admin")
    print(f"📊 Вероятности купонов: {config.COUPON_CONFIG}")
    
    # Запуск polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()