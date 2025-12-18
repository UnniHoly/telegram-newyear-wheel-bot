import sys
import os
# Добавляем путь к проекту в sys.path
sys.path.insert(0, os.path.dirname(__file__))

from bot import main  # Импортируйте главную функцию запуска бота из вашего основного файла

if __name__ == '__main__':
    main()