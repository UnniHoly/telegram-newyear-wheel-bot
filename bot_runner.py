# runner.py
import sys
import os
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_runner.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def main():
    """Запуск бота с обработкой ошибок"""
    try:
        logger.info(f"Запуск бота: {datetime.now()}")
        
        # Импортируем и запускаем бота
        sys.path.insert(0, os.path.dirname(__file__))
        
        # Проверяем наличие файла bot.py
        if not os.path.exists('bot.py'):
            logger.error("Файл bot.py не найден!")
            return
            
        # Динамический импорт
        from bot import main as run_bot
        
        # Запускаем бота
        run_bot()
        
    except ImportError as e:
        logger.error(f"Ошибка импорта: {e}")
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        # Пытаемся перезапуститься через некоторое время
        import time
        time.sleep(10)
        # Перезапускаем
        main()

if __name__ == '__main__':
    main()