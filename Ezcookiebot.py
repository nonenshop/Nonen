cd ~ && cat > bot_perfect.py << 'EOF'
#!/usr/bin/env python3
import sqlite3
import logging
import asyncio
import tempfile
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = '8462779078:AAGvJWnFdYDLzkq2XxyQAg9yWvqE7ezDaPA'
ADMIN_ID = 8491984905
BOT_NAME = 'ezcookie🍪'
DB_FILE = 'bot_perfect.db'

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            total_earned INTEGER DEFAULT 0,
            reg_date TEXT,
            is_admin INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cookies (
            cookie_id INTEGER PRIMARY KEY AUTOINCREMENT,
            cookie_text TEXT,
            price INTEGER DEFAULT 10,
            added_by INTEGER,
            added_date TEXT,
            sold_to INTEGER DEFAULT NULL,
            sold_date TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT,
            task_type TEXT,
            reward INTEGER,
            target_username TEXT,
            target_id TEXT,
            is_active INTEGER DEFAULT 1,
            created_date TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_tasks (
            user_id INTEGER,
            task_id INTEGER,
            completed_date TEXT,
            PRIMARY KEY (user_id, task_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            cookie_id INTEGER,
            purchase_date TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_channels (
            channel_id INTEGER PRIMARY KEY,
            channel_username TEXT,
            added_by INTEGER,
            added_date TEXT,
            bot_is_admin INTEGER DEFAULT 0
        )
    ''')
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('INSERT OR IGNORE INTO users (user_id, balance, total_earned, reg_date, is_admin) VALUES (?, 0, 0, ?, 1)', 
                  (ADMIN_ID, now))
    
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('INSERT INTO users (user_id, balance, total_earned, reg_date) VALUES (?, 0, 0, ?)', (user_id, now))
        conn.commit()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
    
    conn.close()
    return user

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] == 1 if result else False

def is_blocked(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT is_blocked FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] == 1 if result else False

def add_cookie(cookie_text, price, admin_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('INSERT INTO cookies (cookie_text, price, added_by, added_date) VALUES (?, ?, ?, ?)',
                  (cookie_text.strip(), price, admin_id, now))
    conn.commit()
    cookie_id = cursor.lastrowid
    conn.close()
    return cookie_id

def get_available_cookies():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT cookie_id, cookie_text, price FROM cookies WHERE sold_to IS NULL')
    cookies = cursor.fetchall()
    conn.close()
    return cookies

def buy_cookie(user_id, quantity=1):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return False, 'Пользователь не найден', 0, 0, []
    balance = result[0]
    
    cursor.execute('SELECT cookie_id, cookie_text, price FROM cookies WHERE sold_to IS NULL ORDER BY RANDOM() LIMIT ?', (quantity,))
    cookies = cursor.fetchall()
    
    if not cookies:
        conn.close()
        return False, 'Нет доступных куков', 0, balance, []
    
    total_price = sum(cookie[2] for cookie in cookies)
    
    if balance < total_price:
        conn.close()
        return False, f'Недостаточно средств. Нужно {total_price} 🪙, у вас {balance} 🪙', total_price, balance, []
    
    purchased_cookies = []
    
    try:
        for cookie in cookies:
            cookie_id, cookie_text, price = cookie
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (price, user_id))
            cursor.execute('UPDATE cookies SET sold_to = ?, sold_date = ? WHERE cookie_id = ?', (user_id, now, cookie_id))
            cursor.execute('INSERT INTO purchases (user_id, cookie_id, purchase_date) VALUES (?, ?, ?)', 
                          (user_id, cookie_id, now))
            purchased_cookies.append(cookie_text)
        
        conn.commit()
        
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        new_balance = cursor.fetchone()[0]
        conn.close()
        
        return True, '', total_price, new_balance, purchased_cookies
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Ошибка при покупке куков: {e}")
        return False, 'Ошибка при покупке', 0, balance, []

def create_task(task_name, task_type, reward, target_username, target_id=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('INSERT INTO tasks (task_name, task_type, reward, target_username, target_id, created_date) VALUES (?, ?, ?, ?, ?, ?)',
                  (task_name, task_type, reward, target_username, target_id, now))
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id

def get_active_tasks():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT task_id, task_name, task_type, reward, target_username, target_id FROM tasks WHERE is_active = 1')
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def get_all_tasks():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT task_id, task_name, task_type, reward, target_username, is_active FROM tasks ORDER BY created_date DESC')
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def delete_task(task_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE task_id = ?', (task_id,))
    cursor.execute('DELETE FROM user_tasks WHERE task_id = ?', (task_id,))
    conn.commit()
    conn.close()
    return True

def deactivate_task(task_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE tasks SET is_active = 0 WHERE task_id = ?', (task_id,))
    conn.commit()
    conn.close()
    return True

def activate_task(task_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE tasks SET is_active = 1 WHERE task_id = ?', (task_id,))
    conn.commit()
    conn.close()
    return True

async def check_channel_subscription(bot, user_id, channel_id):
    try:
        chat_member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

def complete_task(user_id, task_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM user_tasks WHERE user_id = ? AND task_id = ?', (user_id, task_id))
    if cursor.fetchone()[0] > 0:
        conn.close()
        return False, 'Вы уже выполняли это задание', 0, 0
    
    cursor.execute('SELECT task_name, reward FROM tasks WHERE task_id = ? AND is_active = 1', (task_id,))
    task = cursor.fetchone()
    
    if not task:
        conn.close()
        return False, 'Задание не найдено', 0, 0
    
    task_name, reward = task
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute('INSERT INTO user_tasks (user_id, task_id, completed_date) VALUES (?, ?, ?)', 
                  (user_id, task_id, now))
    cursor.execute('UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?',
                  (reward, reward, user_id))
    conn.commit()
    
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    new_balance = cursor.fetchone()[0]
    conn.close()
    
    return True, task_name, reward, new_balance

def get_completed_tasks(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT task_id FROM user_tasks WHERE user_id = ?', (user_id,))
    completed = [row[0] for row in cursor.fetchall()]
    conn.close()
    return completed

def add_channel_db(channel_username, channel_id, admin_id, bot_is_admin=False):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('DELETE FROM admin_channels WHERE channel_username = ?', (channel_username,))
    cursor.execute('INSERT INTO admin_channels (channel_id, channel_username, added_by, added_date, bot_is_admin) VALUES (?, ?, ?, ?, ?)',
                  (channel_id, channel_username, admin_id, now, 1 if bot_is_admin else 0))
    conn.commit()
    conn.close()

def get_channels():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT channel_id, channel_username, bot_is_admin FROM admin_channels')
    channels = cursor.fetchall()
    conn.close()
    return channels

def remove_channel(channel_username):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM admin_channels WHERE channel_username = ?', (channel_username,))
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted > 0

def set_user_admin(user_id, status):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_admin = ? WHERE user_id = ?', (1 if status else 0, user_id))
    conn.commit()
    conn.close()

def set_user_blocked(user_id, status):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_blocked = ? WHERE user_id = ?', (1 if status else 0, user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name, balance, is_admin, is_blocked FROM users')
    users = cursor.fetchall()
    conn.close()
    return users

def get_user_info(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name, balance, total_earned, reg_date, is_admin, is_blocked FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_count():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def main_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton('👤 Профиль', callback_data='profile'),
         InlineKeyboardButton('💰 Баланс', callback_data='balance')],
        [InlineKeyboardButton('🛍️ Магазин', callback_data='shop'),
         InlineKeyboardButton('🎯 Задания', callback_data='tasks')],
        [InlineKeyboardButton('📊 Топ', callback_data='top'),
         InlineKeyboardButton('ℹ️ Помощь', callback_data='help')]
    ]
    
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton('👑 Админ панель', callback_data='admin_panel')])
    
    return InlineKeyboardMarkup(keyboard)

def admin_keyboard():
    keyboard = [
        [InlineKeyboardButton('📤 Добавить куки', callback_data='add_cookies'),
         InlineKeyboardButton('➕ Добавить задание', callback_data='add_task')],
        [InlineKeyboardButton('📢 Управление каналами', callback_data='manage_channels'),
         InlineKeyboardButton('🎯 Управление заданиями', callback_data='manage_tasks')],
        [InlineKeyboardButton('👥 Управление пользователями', callback_data='manage_users'),
         InlineKeyboardButton('📊 Статистика', callback_data='stats')],
        [InlineKeyboardButton('📨 Рассылка', callback_data='broadcast')],
        [InlineKeyboardButton('🔙 Главное меню', callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def shop_keyboard():
    keyboard = [
        [InlineKeyboardButton('🍪 Купить 1 кук', callback_data='buy_1'),
         InlineKeyboardButton('🍪🍪 Купить 5 куков', callback_data='buy_5')],
        [InlineKeyboardButton('🔙 Назад', callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def cancel_keyboard():
    keyboard = [[InlineKeyboardButton('❌ Отмена', callback_data='admin_panel')]]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if is_blocked(user_id):
        await update.message.reply_text('❌ Вы заблокированы в боте!')
        return
    
    get_user(user_id)
    
    text = f"🍪 *Добро пожаловать в {BOT_NAME}!*\n\nЗарабатывай изи коины и покупай Roblox куки!\n\nВыбери действие:"
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=main_keyboard(user_id))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if is_blocked(user_id):
        await query.edit_message_text('❌ Вы заблокированы в боте!')
        return
    
    try:
        if data == 'main_menu':
            await query.edit_message_text('🏠 *Главное меню*', parse_mode='Markdown', reply_markup=main_keyboard(user_id))
        
        elif data == 'profile':
            user = get_user(user_id)
            admin_status = '👑 Админ' if is_admin(user_id) else '👤 Пользователь'
            blocked_status = '🚫 Заблокирован' if user[7] == 1 else '✅ Активен'
            
            text = f"👤 *Твой профиль*\n\n{admin_status}\n{blocked_status}\n🆔 ID: `{user_id}`\n💰 Баланс: {user[3]} 🪙\n💸 Всего заработано: {user[4]} 🪙\n📅 Регистрация: {user[5][:10]}"
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=main_keyboard(user_id))
        
        elif data == 'balance':
            user = get_user(user_id)
            text = f'💰 *Твой баланс:* {user[3]} 🪙\n\nВыполняй задания чтобы заработать больше!'
            keyboard = [[InlineKeyboardButton('🎯 Задания', callback_data='tasks')],
                       [InlineKeyboardButton('🔙 Назад', callback_data='main_menu')]]
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == 'shop':
            cookies = get_available_cookies()
            user = get_user(user_id)
            
            if cookies:
                prices = [c[2] for c in cookies]
                min_price = min(prices)
                max_price = max(prices)
                avg_price = sum(prices) // len(prices)
                
                text = f"🛍️ *Магазин куков*\n\n🍪 Доступно куков: {len(cookies)}\n💰 Твой баланс: {user[3]} 🪙\n💵 Цены: от {min_price} до {max_price} 🪙 (в среднем {avg_price} 🪙)\n\nВыбери количество:"
            else:
                text = f"🛍️ *Магазин куков*\n\n😔 Нет доступных куков.\nАдмин скоро добавит новые.\n\n💰 Твой баланс: {user[3]} 🪙"
            
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=shop_keyboard())
        
        elif data in ['buy_1', 'buy_5']:
            quantity = 1 if data == 'buy_1' else 5
            
            success, error_msg, total_price, new_balance, purchased_cookies = buy_cookie(user_id, quantity)
            
            if success:
                # Создаем временный файл с куками
                if purchased_cookies:
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                        for cookie in purchased_cookies:
                            f.write(cookie + '\n')
                        temp_file = f.name
                    
                    try:
                        # Отправляем файл
                        with open(temp_file, 'rb') as file:
                            text = f"✅ *Успешная покупка!*\n\n🍪 Куплено куков: {quantity}\n💸 Списано: {total_price} 🪙\n💰 Новый баланс: {new_balance} 🪙\n\n⚠️ *Сохраните файл с куками в безопасном месте!*"
                            
                            await context.bot.send_document(
                                chat_id=user_id,
                                document=file,
                                caption=text,
                                parse_mode='Markdown'
                            )
                        
                        # Удаляем временный файл
                        os.unlink(temp_file)
                        
                        keyboard = [[InlineKeyboardButton('🛍️ В магазин', callback_data='shop')]]
                        await query.edit_message_text('📦 *Ваши куки отправлены в файле выше!*', 
                                                     parse_mode='Markdown', 
                                                     reply_markup=InlineKeyboardMarkup(keyboard))
                        
                    except Exception as e:
                        logger.error(f"Ошибка отправки файла: {e}")
                        text = f"✅ *Успешная покупка!*\n\n🍪 Куплено куков: {quantity}\n💸 Списано: {total_price} 🪙\n💰 Новый баланс: {new_balance} 🪙\n\n📦 *Ваши куки:*\n"
                        
                        for i, cookie in enumerate(purchased_cookies[:3], 1):
                            text += f"\n{i}. `{cookie[:50]}...`"
                        
                        if len(purchased_cookies) > 3:
                            text += f"\n\n... и еще {len(purchased_cookies) - 3} куков"
                        
                        text += "\n\n⚠️ *Сохраните куки в безопасном месте!*"
                        
                        keyboard = [[InlineKeyboardButton('🛍️ В магазин', callback_data='shop')]]
                        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    await query.edit_message_text('❌ Ошибка: куки не найдены', reply_markup=shop_keyboard())
            else:
                await query.edit_message_text(f'❌ {error_msg}', reply_markup=shop_keyboard())
        
        elif data == 'tasks':
            tasks = get_active_tasks()
            completed = get_completed_tasks(user_id)
            
            if not tasks:
                text = '🎯 *Доступные задания*\n\n😔 Нет доступных заданий.\nАдмин скоро добавит новые.'
                keyboard = [[InlineKeyboardButton('🔙 Назад', callback_data='main_menu')]]
                await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                text = '🎯 *Доступные задания:*\n\n'
                keyboard = []
                
                for task in tasks:
                    task_id, name, task_type, reward, target_username, target_id = task
                    if task_id in completed:
                        text += f'✅ {name} - {reward} 🪙 (выполнено)\n'
                    else:
                        text += f'🔄 {name} - {reward} 🪙\n'
                        keyboard.append([InlineKeyboardButton(f'🎯 {name} (+{reward} 🪙)', callback_data=f'task_{task_id}')])
                
                keyboard.append([InlineKeyboardButton('🔙 Назад', callback_data='main_menu')])
                await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data.startswith('task_'):
            task_id = int(data.split('_')[1])
            tasks = get_active_tasks()
            
            # Находим задание
            task_info = None
            for task in tasks:
                if task[0] == task_id:
                    task_info = task
                    break
            
            if not task_info:
                await query.edit_message_text('❌ Задание не найдено', reply_markup=main_keyboard(user_id))
                return
            
            task_id, name, task_type, reward, target_username, target_id = task_info
            
            if task_type == 'channel':
                if target_id:
                    # Показываем кнопку для проверки подписки
                    text = f"📢 *Задание: {name}*\n\n💰 Награда: {reward} 🪙\n\n👉 Перейдите в канал: @{target_username}\n👥 Подпишитесь на канал\n✅ Затем нажмите кнопку 'Я подписался' ниже"
                    
                    keyboard = [
                        [InlineKeyboardButton('✅ Я подписался', callback_data=f'verify_{task_id}')],
                        [InlineKeyboardButton('🔙 Назад', callback_data='tasks')]
                    ]
                    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    await query.edit_message_text(f'❌ Ошибка: ID канала не указан', reply_markup=main_keyboard(user_id))
            
            elif task_type == 'bot':
                text = f"🤖 *Задание: {name}*\n\n💰 Награда: {reward} 🪙\n\n👉 Перейдите в бота: @{target_username}\n🚀 Начните диалог с ботом\n✅ Затем нажмите кнопку ниже"

                keyboard = [[InlineKeyboardButton('✅ Я перешел в бота', callback_data=f'verify_{task_id}')],
                           [InlineKeyboardButton('🔙 Назад', callback_data='tasks')]]
                await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data.startswith('verify_'):
            task_id = int(data.split('_')[1])
            tasks = get_active_tasks()
            
            # Находим задание
            task_info = None
            for task in tasks:
                if task[0] == task_id:
                    task_info = task
                    break
            
            if not task_info:
                await query.edit_message_text('❌ Задание не найдено', reply_markup=main_keyboard(user_id))
                return
            
            task_id, name, task_type, reward, target_username, target_id = task_info
            
            # Проверяем подписку для каналов
            if task_type == 'channel' and target_id:
                try:
                    is_subscribed = await check_channel_subscription(context.bot, user_id, target_id)
                    if not is_subscribed:
                        await query.edit_message_text(
                            f'❌ Вы не подписаны на канал @{target_username}\n\nПожалуйста, подпишитесь и попробуйте снова.',
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton('✅ Я подписался', callback_data=f'verify_{task_id}')],
                                [InlineKeyboardButton('🔙 Назад', callback_data='tasks')]
                            ])
                        )
                        return
                except Exception as e:
                    logger.error(f"Ошибка проверки подписки: {e}")
                    # Если не удалось проверить, все равно даем награду
                    pass
            
            # Выполняем задание
            success, task_name, reward_earned, new_balance = complete_task(user_id, task_id)
            
            if success:
                text = f"✅ *Задание выполнено!*\n\n📝 {task_name}\n💰 Получено: +{reward_earned} 🪙\n💳 Новый баланс: {new_balance} 🪙\n\nПродолжайте в том же духе! 🚀"
            else:
                text = f'❌ {task_name}'
            
            keyboard = [[InlineKeyboardButton('🎯 Еще задания', callback_data='tasks')]]
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == 'top':
            users = get_all_users()
            sorted_users = sorted(users, key=lambda x: x[3], reverse=True)[:10]
            
            text = '🏆 *Топ 10 пользователей:*\n\n'
            for i, (uid, username, name, balance, admin, blocked) in enumerate(sorted_users, 1):
                status = '👑' if admin else '👤'
                status += ' 🚫' if blocked else ''
                display = name if name else (username if username else f'ID {uid}')
                text += f'{i}. {status} {display}: {balance} 🪙\n'
            
            keyboard = [[InlineKeyboardButton('🔙 Назад', callback_data='main_menu')]]
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == 'help':
            help_text = """*📚 Помощь по боту*

*Основные команды:*
/profile - ваш профиль
/balance - ваш баланс
/shop - магазин куков
/tasks - доступные задания
/top - топ пользователей

*Как работает бот:*
1. Выполняйте задания и получайте коины 🪙
2. Покупайте куки в магазине 🛍️
3. Используйте куки для входа в Roblox

*Поддержка:*
По вопросам пишите администратору."""
            await query.edit_message_text(help_text, parse_mode='Markdown', reply_markup=main_keyboard(user_id))
        
        elif data == 'admin_panel':
            if not is_admin(user_id):
                await query.edit_message_text('❌ Только для администраторов!', reply_markup=main_keyboard(user_id))
                return
            
            text = '👑 *Админ панель*\n\nВыбери действие:'
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=admin_keyboard())
        
        elif data == 'add_cookies':
            if not is_admin(user_id):
                await query.edit_message_text('❌ Только для администраторов!', reply_markup=main_keyboard(user_id))
                return
            
            text = '📤 *Добавление куков*\n\nОтправь TXT файл с куками (каждая строка - отдельный кук):'
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=cancel_keyboard())
            context.user_data['awaiting_cookies'] = True
        
        elif data == 'add_task':
            if not is_admin(user_id):
                await query.edit_message_text('❌ Только для администраторов!', reply_markup=main_keyboard(user_id))
                return
            
            keyboard = [
                [InlineKeyboardButton('🤖 Задание на бота', callback_data='add_bot_task')],
                [InlineKeyboardButton('📢 Задание на канал', callback_data='add_channel_task')],
                [InlineKeyboardButton('🔙 Назад', callback_data='admin_panel')]
            ]
            await query.edit_message_text('➕ *Добавление задания*\n\nВыбери тип задания:', 
                                         parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == 'add_bot_task':
            if not is_admin(user_id):
                await query.edit_message_text('❌ Только для администраторов!', reply_markup=main_keyboard(user_id))
                return
            
            text = '🤖 *Добавление задания на бота*\n\nОтправь юзернейм бота (например: @username):'
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=cancel_keyboard())
            context.user_data['adding_bot_task'] = True
        
        elif data == 'add_channel_task':
            if not is_admin(user_id):
                await query.edit_message_text('❌ Только для администраторов!', reply_markup=main_keyboard(user_id))
                return
            
            text = '📢 *Добавление задания на канал*\n\nОтправь юзернейм канала (например: @channelname):'
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=cancel_keyboard())
            context.user_data['adding_channel_task'] = True
        
        elif data == 'manage_channels':
            if not is_admin(user_id):
                await query.edit_message_text('❌ Только для администраторов!', reply_markup=main_keyboard(user_id))
                return
            
            channels = get_channels()
            text = '📢 *Управление каналами*\n\n'
            
            if channels:
                for channel_id, channel_username, bot_is_admin in channels:
                    admin_status = "✅ Бот-админ" if bot_is_admin else "❌ Бот не админ"
                    text += f'• @{channel_username} ({admin_status})\n'
            else:
                text += '❌ Нет добавленных каналов\n\n'
            
            text += '\n*Команды:*\n'
            text += '/add_channel @username - добавить канал\n'
            text += '/remove_channel @username - удалить канал\n'
            text += '/send @username текст - отправить в канал\n'
            text += '/check_channel @username - проверить статус бота'
            
            keyboard = [[InlineKeyboardButton('🔙 В админку', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == 'manage_tasks':
            if not is_admin(user_id):
                await query.edit_message_text('❌ Только для администраторов!', reply_markup=main_keyboard(user_id))
                return
            
            tasks = get_all_tasks()
            text = '🎯 *Управление заданиями*\n\n'
            
            if tasks:
                for task in tasks:
                    task_id, name, task_type, reward, target_username, is_active = task
                    status = "✅ Активно" if is_active == 1 else "❌ Неактивно"
                    text += f'• {name} ({reward} 🪙) - {status}\n'
                    text += f'  ID: {task_id} | Тип: {task_type} | Цель: @{target_username}\n\n'
            else:
                text += '❌ Нет заданий\n\n'
            
            text += '\n*Команды:*\n'
            text += '/delete_task ID - удалить задание\n'
            text += '/disable_task ID - деактивировать задание\n'
            text += '/enable_task ID - активировать задание'
            
            keyboard = [[InlineKeyboardButton('🔙 В админку', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == 'manage_users':
            if not is_admin(user_id):
                await query.edit_message_text('❌ Только для администраторов!', reply_markup=main_keyboard(user_id))
                return
            
            text = '👥 *Управление пользователями*\n\n'
            text += '*Команды:*\n'
            text += '/ban ID - заблокировать пользователя\n'
            text += '/unban ID - разблокировать пользователя\n'
            text += '/admin ID - назначить админа\n'
            text += '/deladmin ID - снять админа\n'
            text += '/user ID - информация о пользователе\n'
            text += '/users - список всех пользователей'
            
            keyboard = [[InlineKeyboardButton('🔙 В админку', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == 'stats':
            if not is_admin(user_id):
                await query.edit_message_text('❌ Только для администраторов!', reply_markup=main_keyboard(user_id))
                return
            
            users = get_all_users()
            cookies = get_available_cookies()
            tasks = get_active_tasks()
            
            user_count = len(users)
            blocked_count = sum(1 for u in users if u[5] == 1)
            admin_count = sum(1 for u in users if u[4] == 1)
            total_balance = sum(u[3] for u in users)
            
            text = f"""📊 *Статистика бота*

👥 Пользователи:
• Всего: {user_count}
• Админов: {admin_count}
• Заблокированных: {blocked_count}
• Активных: {user_count - blocked_count}

💰 Финансы:
• Общий баланс: {total_balance} 🪙
• Средний баланс: {total_balance // user_count if user_count > 0 else 0} 🪙

🍪 Куки:
• Доступно: {len(cookies)}

🎯 Задания:
• Активных: {len(tasks)}"""
            
            keyboard = [[InlineKeyboardButton('🔙 В админку', callback_data='admin_panel')]]
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == 'broadcast':
            if not is_admin(user_id):
                await query.edit_message_text('❌ Только для администраторов!', reply_markup=main_keyboard(user_id))
                return
            
            text = '📨 *Рассылка*\n\nОтправь сообщение для рассылки всем пользователям:'
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=cancel_keyboard())
            context.user_data['broadcasting'] = True
    
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.edit_message_text(f'❌ Ошибка: {str(e)}', reply_markup=main_keyboard(user_id))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    
    if is_blocked(user_id):
        return
    
    # Загрузка куков
    if context.user_data.get('awaiting_cookies') and is_admin(user_id):
        if message.document and message.document.file_name.endswith('.txt'):
            try:
                file = await message.document.get_file()
                file_content = await file.download_as_bytearray()
                cookies_text = file_content.decode('utf-8', errors='ignore')
                cookies = [c.strip() for c in cookies_text.split('\n') if c.strip()]
                context.user_data['cookies_to_add'] = cookies
                
                await message.reply_text(f'✅ Загружено {len(cookies)} куков!\n\nТеперь отправь цену для этих куков:')
                context.user_data['awaiting_cookies'] = False
                context.user_data['awaiting_price'] = True
            except Exception as e:
                logger.error(f"Ошибка при загрузке файла: {e}")
                await message.reply_text(f'❌ Ошибка: {e}')
        else:
            await message.reply_text('❌ Отправьте TXT файл с куками.', reply_markup=cancel_keyboard())
    
    # Установка цены
    elif context.user_data.get('awaiting_price') and is_admin(user_id):
        try:
            price = int(message.text)
            cookies = context.user_data.get('cookies_to_add', [])
            
            added = 0
            for cookie in cookies:
                if cookie:
                    add_cookie(cookie, price, user_id)
                    added += 1
            
            await message.reply_text(f'✅ Добавлено {added} куков по цене {price} 🪙 каждый!', reply_markup=admin_keyboard())
            context.user_data.pop('awaiting_price', None)
            context.user_data.pop('cookies_to_add', None)
        except ValueError:
            await message.reply_text('❌ Отправьте число (цену)', reply_markup=cancel_keyboard())
    
    # Задание на бота
    elif context.user_data.get('adding_bot_task') and is_admin(user_id):
        bot_username = message.text.strip().replace('@', '')
        context.user_data['bot_username'] = bot_username
        context.user_data['adding_bot_task'] = False
        context.user_data['awaiting_bot_reward'] = True
        await message.reply_text(f'🤖 Юзернейм бота: @{bot_username}\n\nТеперь отправь награду за задание:')
    
    # Награда за задание на бота
    elif context.user_data.get('awaiting_bot_reward') and is_admin(user_id):
        try:
            reward = int(message.text)
            bot_username = context.user_data.get('bot_username', '')
            task_name = f'Перейти в бота @{bot_username}'
            task_id = create_task(task_name, 'bot', reward, bot_username)
            
            if task_id:
                await message.reply_text(f'✅ Задание добавлено!\n🤖 Бот: @{bot_username}\n💰 Награда: {reward} 🪙', reply_markup=admin_keyboard())
            else:
                await message.reply_text('❌ Ошибка при создании задания.', reply_markup=admin_keyboard())
            
            context.user_data.pop('awaiting_bot_reward', None)
            context.user_data.pop('bot_username', None)
        except ValueError:
            await message.reply_text('❌ Отправьте число (награду)')
    
    # Задание на канал
    elif context.user_data.get('adding_channel_task') and is_admin(user_id):
        channel_username = message.text.strip().replace('@', '')
        context.user_data['channel_username'] = channel_username
        context.user_data['adding_channel_task'] = False
        context.user_data['awaiting_channel_reward'] = True
        
        # Пытаемся получить ID канала
        try:
            chat = await context.bot.get_chat(f'@{channel_username}')
            context.user_data['channel_id'] = str(chat.id)
            await message.reply_text(f'📢 Юзернейм канала: @{channel_username}\nID: {chat.id}\n\nТеперь отправь награду за подписку:')
        except Exception as e:
            logger.error(f"Ошибка получения канала: {e}")
            await message.reply_text(f'❌ Не удалось получить информацию о канале. Проверьте, что канал существует и юзернейм правильный.')
    
    # Награда за задание на канал
    elif context.user_data.get('awaiting_channel_reward') and is_admin(user_id):
        try:
            reward = int(message.text)
            channel_username = context.user_data.get('channel_username', '')
            channel_id = context.user_data.get('channel_id', '')
            
            task_name = f'Подписаться на канал @{channel_username}'
            task_id = create_task(task_name, 'channel', reward, channel_username, channel_id)
            
            if task_id:
                await message.reply_text(f'✅ Задание добавлено!\n📢 Канал: @{channel_username}\n💰 Награда: {reward} 🪙', reply_markup=admin_keyboard())
            else:
                await message.reply_text('❌ Ошибка при создании задания.', reply_markup=admin_keyboard())
            
            context.user_data.pop('awaiting_channel_reward', None)
            context.user_data.pop('channel_username', None)
            context.user_data.pop('channel_id', None)
        except ValueError:
            await message.reply_text('❌ Отправьте число (награду)')
    
    # Рассылка
    elif context.user_data.get('broadcasting') and is_admin(user_id):
        broadcast_text = message.text
        users = get_all_users()
        
        sent = 0
        failed = 0
        total = len(users)
        
        await message.reply_text(f'📨 Начинаю рассылку для {total} пользователей...')
        
        for user in users:
            try:
                if user[5] == 0:  # is_blocked = 0
                    await context.bot.send_message(chat_id=user[0], text=broadcast_text)
                    sent += 1
                    await asyncio.sleep(0.05)
            except Exception as e:
                failed += 1
                logger.warning(f"Не удалось отправить сообщение пользователю {user[0]}: {e}")
        
        await message.reply_text(f'✅ Рассылка завершена!\nОтправлено: {sent}/{total}\nНе удалось: {failed}', reply_markup=admin_keyboard())
        context.user_data.pop('broadcasting', None)
    
    # Обработка команд
    elif message.text and message.text.startswith('/'):
        await handle_command(update, context)
    
    # Простое сообщение
    else:
        await message.reply_text('Используй меню для навигации 👆', reply_markup=main_keyboard(user_id))

async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    text = message.text.strip() if message.text else ''
    
    if not text:
        return
    
    if is_blocked(user_id):
        return
    
    try:
        if text == '/start':
            await start(update, context)
            return
        
        elif text.startswith('/add_channel ') and is_admin(user_id):
            parts = text[13:].strip().split(' ', 1)
            if len(parts) >= 1:
                channel_username = parts[0].replace('@', '')
                try:
                    chat = await context.bot.get_chat(f'@{channel_username}')
                    
                    # Проверяем, является ли бот администратором
                    try:
                        bot_member = await context.bot.get_chat_member(chat_id=chat.id, user_id=context.bot.id)
                        bot_is_admin = bot_member.status in ['administrator', 'creator']
                        
                        add_channel_db(channel_username, chat.id, user_id, bot_is_admin)
                        
                        if bot_is_admin:
                            await message.reply_text(f'✅ Канал добавлен!\n📢 {chat.title}\n🆔 {chat.id}\n✅ Бот является администратором')
                        else:
                            await message.reply_text(f'⚠️ Канал добавлен, но бот НЕ администратор!\n📢 {chat.title}\n🆔 {chat.id}\n❌ Проверка подписок не будет работать')
                            
                    except Exception as e:
                        logger.error(f"Ошибка проверки прав бота: {e}")
                        add_channel_db(channel_username, chat.id, user_id, False)
                        await message.reply_text(f'⚠️ Канал добавлен, но не удалось проверить права бота!\n📢 {chat.title}\n🆔 {chat.id}')
                        
                except Exception as e:
                    await message.reply_text(f'❌ Ошибка: {str(e)}')
        
        elif text.startswith('/remove_channel ') and is_admin(user_id):
            parts = text[16:].strip().split(' ', 1)
            if len(parts) >= 1:
                channel_username = parts[0].replace('@', '')
                if remove_channel(channel_username):
                    await message.reply_text(f'✅ Канал @{channel_username} удален!')
                else:
                    await message.reply_text(f'❌ Канал @{channel_username} не найден.')
        
        elif text.startswith('/send ') and is_admin(user_id):
            parts = text[6:].split(' ', 1)
            if len(parts) == 2:
                channel_username = parts[0].replace('@', '')
                text_to_send = parts[1]
                try:
                    chat = await context.bot.get_chat(f'@{channel_username}')
                    await context.bot.send_message(chat_id=chat.id, text=text_to_send)
                    await message.reply_text(f'✅ Сообщение отправлено в канал @{channel_username}!')
                except Exception as e:
                    await message.reply_text(f'❌ Ошибка: {str(e)}')
        
        elif text.startswith('/check_channel ') and is_admin(user_id):
            parts = text[15:].strip().split(' ', 1)
            if len(parts) >= 1:
                channel_username = parts[0].replace('@', '')
                try:
                    chat = await context.bot.get_chat(f'@{channel_username}')
                    bot_member = await context.bot.get_chat_member(chat_id=chat.id, user_id=context.bot.id)
                    bot_is_admin = bot_member.status in ['administrator', 'creator']
                    
                    if bot_is_admin:
                        await message.reply_text(f'✅ Бот является администратором в канале @{channel_username}')
                    else:
                        await message.reply_text(f'❌ Бот НЕ является администратором в канале @{channel_username}\n\nДобавьте бота в канал как администратора для проверки подписок.')
                except Exception as e:
                    await message.reply_text(f'❌ Ошибка: {str(e)}')
        
        elif text.startswith('/ban ') and is_admin(user_id):
            try:
                target_id = int(text[5:])
                if target_id == ADMIN_ID:
                    await message.reply_text('❌ Нельзя заблокировать главного админа!')
                else:
                    set_user_blocked(target_id, True)
                    await message.reply_text(f'✅ Пользователь {target_id} заблокирован!')
            except ValueError:
                await message.reply_text('Использование: /ban ID_пользователя')
        
        elif text.startswith('/unban ') and is_admin(user_id):
            try:
                target_id = int(text[7:])
                set_user_blocked(target_id, False)
                await message.reply_text(f'✅ Пользователь {target_id} разблокирован!')
            except ValueError:
                await message.reply_text('Использование: /unban ID_пользователя')
        
        elif text.startswith('/admin ') and is_admin(user_id):
            try:
                target_id = int(text[7:])
                if target_id == ADMIN_ID:
                    await message.reply_text('❌ Этот пользователь уже главный админ!')
                else:
                    set_user_admin(target_id, True)
                    await message.reply_text(f'✅ Пользователь {target_id} назначен админом!')
            except ValueError:
                await message.reply_text('Использование: /admin ID_пользователя')
        
        elif text.startswith('/deladmin ') and is_admin(user_id):
            try:
                target_id = int(text[10:])
                if target_id == ADMIN_ID:
                    await message.reply_text('❌ Нельзя снять главного админа!')
                else:
                    set_user_admin(target_id, False)
                    await message.reply_text(f'✅ Пользователь {target_id} снят с админки!')
            except ValueError:
                await message.reply_text('Использование: /deladmin ID_пользователя')
        
        elif text.startswith('/user ') and is_admin(user_id):
            try:
                target_id = int(text[6:])
                user = get_user_info(target_id)
                if user:
                    admin_status = '👑 Админ' if user[6] == 1 else '👤 Пользователь'
                    blocked_status = '🚫 Заблокирован' if user[7] == 1 else '✅ Активен'
                    
                    text_msg = f"""👤 Информация о пользователе

{admin_status} | {blocked_status}

🆔 ID: {user[0]}
👤 Имя: {user[2] or 'Не указано'}
📛 Юзернейм: @{user[1] or 'Не указано'}

💰 Баланс: {user[3]} 🪙
💸 Всего заработано: {user[4]} 🪙

📅 Регистрация: {user[5]}"""
                    await message.reply_text(text_msg)
                else:
                    await message.reply_text(f'❌ Пользователь {target_id} не найден.')
            except ValueError:
                await message.reply_text('Использование: /user ID_пользователя')
        
        elif text == '/users' and is_admin(user_id):
            users = get_all_users()
            if users:
                text_msg = f'👥 Список пользователей ({len(users)})\n\n'
                for user in users[:20]:
                    status = '👑' if user[4] == 1 else '👤'
                    if user[5] == 1:
                        status += ' 🚫'
                    
                    display = user[2] or user[1] or f'ID {user[0]}'
                    text_msg += f'{status} {user[0]} - {display}: {user[3]} 🪙\n'
                
                if len(users) > 20:
                    text_msg += f'\n... и еще {len(users) - 20} пользователей'
                
                await message.reply_text(text_msg)
            else:
                await message.reply_text('❌ Нет пользователей.')
        
        elif text.startswith('/delete_task ') and is_admin(user_id):
            try:
                task_id = int(text[13:])
                if delete_task(task_id):
                    await message.reply_text(f'✅ Задание #{task_id} удалено!')
                else:
                    await message.reply_text(f'❌ Не удалось удалить задание #{task_id}')
            except ValueError:
                await message.reply_text('Использование: /delete_task ID_задания')
        
        elif text.startswith('/disable_task ') and is_admin(user_id):
            try:
                task_id = int(text[14:])
                if deactivate_task(task_id):
                    await message.reply_text(f'✅ Задание #{task_id} деактивировано!')
                else:
                    await message.reply_text(f'❌ Не удалось деактивировать задание #{task_id}')
            except ValueError:
                await message.reply_text('Использование: /disable_task ID_задания')
        
        elif text.startswith('/enable_task ') and is_admin(user_id):
            try:
                task_id = int(text[13:])
                if activate_task(task_id):
                    await message.reply_text(f'✅ Задание #{task_id} активировано!')
                else:
                    await message.reply_text(f'❌ Не удалось активировать задание #{task_id}')
            except ValueError:
                await message.reply_text('Использование: /enable_task ID_задания')
        
        elif text == '/admin':
            if is_admin(user_id):
                await message.reply_text('👑 Админ панель', reply_markup=admin_keyboard())
            else:
                await message.reply_text('❌ Только для администраторов!')
        
        elif text == '/help':
            help_text = """📚 Помощь по боту

Основные команды:
/profile - ваш профиль
/balance - ваш баланс
/shop - магазин куков
/tasks - доступные задания
/top - топ пользователей

Как работает бот:
1. Выполняйте задания и получайте коины 🪙
2. Покупайте куки в магазине 🛍️
3. Используйте куки для входа в Roblox

Поддержка:
По вопросам пишите администратору."""
            await message.reply_text(help_text, reply_markup=main_keyboard(user_id))
        
        elif text == '/profile':
            user = get_user(user_id)
            admin_status = '👑 Админ' if is_admin(user_id) else '👤 Пользователь'
            blocked_status = '🚫 Заблокирован' if user[7] == 1 else '✅ Активен'
            
            text_msg = f"👤 Твой профиль\n\n{admin_status}\n{blocked_status}\n🆔 ID: {user_id}\n💰 Баланс: {user[3]} 🪙\n💸 Всего заработано: {user[4]} 🪙\n📅 Регистрация: {user[5][:10]}"
            await message.reply_text(text_msg, reply_markup=main_keyboard(user_id))
        
        elif text == '/balance':
            user = get_user(user_id)
            text_msg = f'💰 Твой баланс: {user[3]} 🪙\n\nВыполняй задания чтобы заработать больше!'
            keyboard = [[InlineKeyboardButton('🎯 Задания', callback_data='tasks')],
                       [InlineKeyboardButton('🔙 Назад', callback_data='main_menu')]]
            await message.reply_text(text_msg, reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif text == '/shop':
            cookies = get_available_cookies()
            user = get_user(user_id)
            
            if cookies:
                prices = [c[2] for c in cookies]
                min_price = min(prices)
                max_price = max(prices)
                avg_price = sum(prices) // len(prices)
                
                text_msg = f"🛍️ Магазин куков\n\n🍪 Доступно куков: {len(cookies)}\n💰 Твой баланс: {user[3]} 🪙\n💵 Цены: от {min_price} до {max_price} 🪙 (в среднем {avg_price} 🪙)\n\nВыбери количество:"
            else:
                text_msg = f"🛍️ Магазин куков\n\n😔 Нет доступных куков.\nАдмин скоро добавит новые.\n\n💰 Твой баланс: {user[3]} 🪙"
            
            await message.reply_text(text_msg, reply_markup=shop_keyboard())
        
        elif text == '/tasks':
            tasks = get_active_tasks()
            completed = get_completed_tasks(user_id)
            
            text_msg = '🎯 Доступные задания:\n\n'
            keyboard = []
            
            for task in tasks:
                task_id, name, task_type, reward, target_username, target_id = task
                if task_id in completed:
                    text_msg += f'✅ {name} - {reward} 🪙 (выполнено)\n'
                else:
                    text_msg += f'🔄 {name} - {reward} 🪙\n'
                    keyboard.append([InlineKeyboardButton(f'🎯 {name} (+{reward} 🪙)', callback_data=f'task_{task_id}')])
            
            keyboard.append([InlineKeyboardButton('🔙 Назад', callback_data='main_menu')])
            await message.reply_text(text_msg, reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif text == '/top':
            users = get_all_users()
            sorted_users = sorted(users, key=lambda x: x[3], reverse=True)[:10]
            
            text_msg = '🏆 Топ 10 пользователей:\n\n'
            for i, (uid, username, name, balance, admin, blocked) in enumerate(sorted_users, 1):
                status = '👑' if admin else '👤'
                status += ' 🚫' if blocked else ''
                display = name if name else (username if username else f'ID {uid}')
                text_msg += f'{i}. {status} {display}: {balance} 🪙\n'
            
            keyboard = [[InlineKeyboardButton('🔙 Назад', callback_data='main_menu')]]
            await message.reply_text(text_msg, reply_markup=InlineKeyboardMarkup(keyboard))
        
        else:
            await message.reply_text('❌ Неизвестная команда. Используйте /help для списка команд.')
            
    except Exception as e:
        logger.error(f"Ошибка в handle_command: {e}")
        await message.reply_text('❌ Произошла ошибка. Попробуйте позже.', reply_markup=main_keyboard(user_id))

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    
    if is_blocked(user_id):
        return
    
    try:
        if is_admin(user_id) and context.user_data.get('awaiting_cookies'):
            if message.document and message.document.file_name.endswith('.txt'):
                file = await message.document.get_file()
                file_content = await file.download_as_bytearray()
                cookies_text = file_content.decode('utf-8', errors='ignore')
                cookies = [c.strip() for c in cookies_text.split('\n') if c.strip()]
                
                if not cookies:
                    await message.reply_text('❌ Файл не содержит куков.', reply_markup=cancel_keyboard())
                    return
                
                context.user_data['cookies_to_add'] = cookies
                context.user_data['awaiting_cookies'] = False
                context.user_data['awaiting_price'] = True
                
                await message.reply_text(f'✅ Загружено {len(cookies)} куков из файла!\n\nТеперь отправь цену:')
            else:
                await message.reply_text('❌ Отправьте TXT файл с куками.', reply_markup=cancel_keyboard())
        else:
            await message.reply_text('❌ Файлы принимаются только админами при добавлении куков.')
    except Exception as e:
        logger.error(f"Ошибка при обработке документа: {e}")
        await message.reply_text('❌ Ошибка при обработке файла.')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                '❌ Произошла ошибка. Попробуйте позже.',
                reply_markup=main_keyboard(update.effective_user.id)
            )
    except:
        pass

def main():
    print('=' * 60)
    print('🤖 EZCOOKIE BOT ЗАПУЩЕН!')
    print('=' * 60)
    print(f'👑 Главный админ: {ADMIN_ID}')
    print(f'🍪 Название: {BOT_NAME}')
    print('\n📱 КОМАНДЫ АДМИНА:')
    print('  /admin - админ-панель')
    print('  /add_channel @username - добавить канал')
    print('  /remove_channel @username - удалить канал')
    print('  /send @username текст - отправить в канал')
    print('  /check_channel @username - проверить статус бота')
    print('  /ban ID - заблокировать пользователя')
    print('  /unban ID - разблокировать пользователя')
    print('  /admin ID - назначить админа')
    print('  /deladmin ID - снять админа')
    print('  /user ID - информация о пользователе')
    print('  /users - список пользователей')
    print('  /delete_task ID - удалить задание')
    print('  /disable_task ID - деактивировать задание')
    print('  /enable_task ID - активировать задание')
    print('=' * 60)
    
    app = Application.builder().token(TOKEN).build()
    
    # Основные команды
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', handle_command))
    app.add_handler(CommandHandler('admin', handle_command))
    app.add_handler(CommandHandler('profile', handle_command))
    app.add_handler(CommandHandler('balance', handle_command))
    app.add_handler(CommandHandler('shop', handle_command))
    app.add_handler(CommandHandler('tasks', handle_command))
    app.add_handler(CommandHandler('top', handle_command))
    
    # Обработчик кнопок
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Обработчик документов
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Обработчик ошибок
    app.add_error_handler(error_handler)
    
    # Запускаем бота
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
EOF
python bot_perfect.py
