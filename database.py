import sqlite3
from datetime import datetime, timedelta
import random
import config
from contextlib import contextmanager
# В начале файла database.py добавить:
from datetime import datetime, timedelta, timezone
import pytz

# Часовой пояс Беларуси (UTC+3)
BELARUS_TZ = pytz.timezone('Europe/Minsk')

class Database:
    def __init__(self, db_path='coupons.db'):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        """Создает соединение с базой данных"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Для доступа к колонкам по имени
        return conn
    
    def init_db(self):
        """Инициализация таблиц"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица купонов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS coupons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    coupon TEXT NOT NULL,
                    code_word TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    valid_until TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT 0
                )
            ''')
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_spins INTEGER DEFAULT 0
                )
            ''')
            
            # Индексы
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_user_date 
                ON coupons(telegram_id, date(created_at))
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_valid_until 
                ON coupons(valid_until)
            ''')
            
            conn.commit()
    
    def has_user_played_today(self, telegram_id):
        """Проверяет, получал ли пользователь купон сегодня (без учета времени)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Текущая дата в белорусском часовом поясе
            today = datetime.now(BELARUS_TZ).date()
            
            cursor.execute('''
                SELECT id FROM coupons 
                WHERE telegram_id = ? 
                AND DATE(created_at, 'localtime') = DATE(?, 'localtime')
                LIMIT 1
            ''', (telegram_id, today))
            
            return cursor.fetchone() is not None
    
    def get_active_coupons(self, telegram_id):
        """Получает активные купоны пользователя (не истекшие и не использованные)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Используем текущее время в белорусском часовом поясе
            now = datetime.now(BELARUS_TZ).replace(tzinfo=None)
            
            cursor.execute('''
                SELECT * FROM coupons 
                WHERE telegram_id = ? 
                AND valid_until >= ?
                AND used = 0
                ORDER BY created_at DESC
            ''', (telegram_id, now))
            
            return cursor.fetchall()
    
    def get_user_stats(self, telegram_id):
        """Получает статистику пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Общее количество купонов
            cursor.execute('SELECT COUNT(*) FROM coupons WHERE telegram_id = ?', (telegram_id,))
            total = cursor.fetchone()[0]
            
            # Использованные купоны
            cursor.execute('SELECT COUNT(*) FROM coupons WHERE telegram_id = ? AND used = 1', (telegram_id,))
            used = cursor.fetchone()[0]
            
            # Активные купоны
            cursor.execute('''
                SELECT COUNT(*) FROM coupons 
                WHERE telegram_id = ? 
                AND valid_until >= datetime('now')
                AND used = 0
            ''', (telegram_id,))
            active = cursor.fetchone()[0]
            
            # Первый спин
            cursor.execute('''
                SELECT MIN(created_at) FROM coupons WHERE telegram_id = ?
            ''', (telegram_id,))
            first_spin = cursor.fetchone()[0]
            
            return {
                'total': total,
                'used': used,
                'active': active,
                'first_spin': first_spin
            }
    
    def generate_coupon(self):
        """Генерация купона с учетом вероятностей и кодовых слов"""
        coupons = []
        weights = []
        code_words = []
        
        for coupon, data in config.COUPON_CONFIG.items():
            coupons.append(coupon)
            weights.append(data['chance'])
            code_words.append(data['code_word'])
        
        random_index = random.choices(range(len(coupons)), weights=weights, k=1)[0]
        
        return {
            'coupon': coupons[random_index],
            'code_word': code_words[random_index],
            'emoji': config.COUPON_CONFIG[coupons[random_index]]['emoji']
        }
    
def save_coupon(self, telegram_id, username, coupon_data):
    """Сохранение купона в базу данных"""
    # Используем текущее время в часовом поясе Беларуси
    created_at = datetime.now(BELARUS_TZ)
    valid_until = created_at + timedelta(days=3)
    
    # Конвертируем в naive datetime для SQLite
    created_at_naive = created_at.replace(tzinfo=None)
    valid_until_naive = valid_until.replace(tzinfo=None)
    
    with self.get_connection() as conn:
        cursor = conn.cursor()
        
        # Сохраняем купон
        cursor.execute('''
            INSERT INTO coupons 
            (telegram_id, username, coupon, code_word, created_at, valid_until)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            telegram_id, 
            username, 
            coupon_data['coupon'], 
            coupon_data['code_word'],
            created_at_naive, 
            valid_until_naive
        ))
        
        # Обновляем статистику пользователя
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (telegram_id, username, total_spins)
            VALUES (?, ?, COALESCE(
                (SELECT total_spins FROM users WHERE telegram_id = ?), 
                0
            ) + 1)
        ''', (telegram_id, username, telegram_id))
        
        conn.commit()
        
        return {
            'id': cursor.lastrowid,
            'created_at': created_at,
            'valid_until': valid_until
        }
    
    def mark_coupon_used_by_instagram(self, instagram, coupon_value):
        """Пометить один активный купон пользователя как использованный"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Ищем активный купон пользователя с указанной скидкой
            cursor.execute('''
                SELECT id, code_word, created_at 
                FROM coupons 
                WHERE username = ? 
                AND coupon = ? 
                AND used = 0 
                AND valid_until >= datetime('now')
                ORDER BY created_at ASC
                LIMIT 1
            ''', (instagram, coupon_value))
            
            coupon = cursor.fetchone()
            
            if coupon:
                # Помечаем купон как использованный
                cursor.execute('UPDATE coupons SET used = 1 WHERE id = ?', (coupon['id'],))
                conn.commit()
                
                return {
                    'success': True,
                    'coupon_id': coupon['id'],
                    'code_word': coupon['code_word'],
                    'created_at': coupon['created_at']
                }
            else:
                # Проверяем, есть ли вообще пользователь с таким инстаграмом
                cursor.execute('SELECT COUNT(*) FROM coupons WHERE username = ?', (instagram,))
                user_exists = cursor.fetchone()[0] > 0
                
                if user_exists:
                    # Проверяем, есть ли купоны с такой скидкой (даже использованные)
                    cursor.execute('''
                        SELECT COUNT(*) FROM coupons 
                        WHERE username = ? AND coupon = ?
                    ''', (instagram, coupon_value))
                    coupon_exists = cursor.fetchone()[0] > 0
                    
                    if coupon_exists:
                        return {
                            'success': False,
                            'reason': 'Все купоны с этой скидкой уже использованы или истекли'
                        }
                    else:
                        return {
                            'success': False,
                            'reason': 'У пользователя нет купонов с такой скидкой'
                        }
                else:
                    return {
                        'success': False,
                        'reason': 'Пользователь с таким Instagram не найден'
                    }
    
    # АДМИН МЕТОДЫ
    def get_admin_stats(self):
        """Статистика для админ-панели"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Общая статистика
            cursor.execute('SELECT COUNT(*) FROM coupons')
            total_coupons = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(DISTINCT telegram_id) FROM coupons')
            unique_users = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM coupons WHERE date(created_at) = date("now")')
            today_coupons = cursor.fetchone()[0]
            
            # Распределение купонов
            cursor.execute('''
                SELECT coupon, COUNT(*) as count 
                FROM coupons 
                GROUP BY coupon 
                ORDER BY count DESC
            ''')
            coupon_distribution = cursor.fetchall()
            
            # Последние 10 купонов
            cursor.execute('''
                SELECT c.*, u.first_name, u.last_name 
                FROM coupons c
                LEFT JOIN users u ON c.telegram_id = u.telegram_id
                ORDER BY c.created_at DESC 
                LIMIT 10
            ''')
            recent_coupons = cursor.fetchall()
            
            # Активные пользователи
            cursor.execute('''
                SELECT telegram_id, username, total_spins 
                FROM users 
                ORDER BY total_spins DESC 
                LIMIT 10
            ''')
            top_users = cursor.fetchall()
            
            return {
                'total_coupons': total_coupons,
                'unique_users': unique_users,
                'today_coupons': today_coupons,
                'coupon_distribution': coupon_distribution,
                'recent_coupons': recent_coupons,
                'top_users': top_users
            }
    
    def get_all_users(self):
        """Получить список всех пользователей"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.*, COUNT(c.id) as total_coupons
                FROM users u
                LEFT JOIN coupons c ON u.telegram_id = c.telegram_id
                GROUP BY u.telegram_id
                ORDER BY u.joined_at DESC
            ''')
            return cursor.fetchall()
    
    def search_coupons(self, query):
        """Поиск купонов по username или купону"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.*, u.first_name, u.last_name 
                FROM coupons c
                LEFT JOIN users u ON c.telegram_id = u.telegram_id
                WHERE c.username LIKE ? OR c.coupon LIKE ? OR c.code_word LIKE ?
                ORDER BY c.created_at DESC
                LIMIT 50
            ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
            return cursor.fetchall()
    
    def export_data(self):
        """Экспорт данных для админа"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Все купоны
            cursor.execute('''
                SELECT 
                    c.created_at,
                    u.first_name || ' ' || COALESCE(u.last_name, '') as user_name,
                    c.username as instagram,
                    c.coupon,
                    c.code_word,
                    c.valid_until,
                    CASE WHEN c.used = 1 THEN 'Да' ELSE 'Нет' END as used
                FROM coupons c
                LEFT JOIN users u ON c.telegram_id = u.telegram_id
                ORDER BY c.created_at DESC
            ''')
            
            coupons = cursor.fetchall()
            
            # Все пользователи
            cursor.execute('''
                SELECT 
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    joined_at,
                    total_spins
                FROM users
                ORDER BY joined_at DESC
            ''')
            
            users = cursor.fetchall()
            
            return {
                'coupons': coupons,
                'users': users
            }

    def user_exists(self, telegram_id):
        """Проверяет, есть ли пользователь в базе"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM coupons 
                WHERE telegram_id = ? 
                LIMIT 1
            ''', (telegram_id,))
            
            return cursor.fetchone()[0] > 0
    
    def get_last_instagram(self, telegram_id):
        """Получить последний использованный Instagram пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT username FROM coupons 
                WHERE telegram_id = ? 
                ORDER BY created_at DESC 
                LIMIT 1
            ''', (telegram_id,))
            
            result = cursor.fetchone()
            return result[0] if result else "не указан"
        
# Глобальный экземпляр базы данных
db = Database()