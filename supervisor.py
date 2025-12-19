# supervisor.py
import os
import sys
import time
import signal
import subprocess
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/unniholy/telegram-newyear-wheel-bot/supervisor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BotSupervisor:
    def __init__(self):
        self.bot_process = None
        self.bot_pid = None
        self.restart_count = 0
        self.max_restarts = 10  # Максимум перезапусков в день
        self.bot_script = '/home/unniholy/telegram-newyear-wheel-bot/bot.py'
        
    def is_bot_running(self):
        """Проверяет, запущен ли процесс бота"""
        try:
            if self.bot_process and self.bot_process.poll() is None:
                return True
                
            # Дополнительная проверка через ps
            result = subprocess.run(
                ['ps', 'aux'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Ищем процесс бота
            for line in result.stdout.split('\n'):
                if 'bot.py' in line and 'python' in line and 'supervisor' not in line:
                    return True
            return False
            
        except Exception as e:
            logger.error(f"Ошибка проверки процесса: {e}")
            return False
    
    def start_bot(self):
        """Запускает бота"""
        try:
            logger.info("Запуск бота...")
            
            # Убиваем старые процессы если есть
            self.kill_old_processes()
            time.sleep(2)
            
            # Запускаем бота в фоновом режиме с перенаправлением логов
            self.bot_process = subprocess.Popen(
                [sys.executable, self.bot_script],
                stdout=open('/home/unniholy/telegram-newyear-wheel-bot/bot_stdout.log', 'a'),
                stderr=open('/home/unniholy/telegram-newyear-wheel-bot/bot_stderr.log', 'a'),
                preexec_fn=os.setsid  # Создаем новую группу процессов
            )
            
            self.bot_pid = self.bot_process.pid
            self.restart_count += 1
            
            logger.info(f"Бот запущен. PID: {self.bot_pid}, Перезапуск #{self.restart_count}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска бота: {e}")
            return False
    
    def kill_old_processes(self):
        """Убивает старые процессы бота"""
        try:
            # Ищем все процессы bot.py
            result = subprocess.run(
                ['pgrep', '-f', 'bot.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.stdout:
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid and pid != str(os.getpid()):
                        try:
                            os.kill(int(pid), signal.SIGTERM)
                            logger.info(f"Убит старый процесс: {pid}")
                        except:
                            pass
                            
        except Exception as e:
            logger.error(f"Ошибка убийства процессов: {e}")
    
    def monitor(self):
        """Основной цикл мониторинга"""
        logger.info("=== ЗАПУСК СУПЕРВИЗОРА ===")
        logger.info(f"Время запуска: {datetime.now()}")
        
        # Запускаем бота первый раз
        self.start_bot()
        
        # Основной цикл мониторинга
        while self.restart_count <= self.max_restarts:
            try:
                time.sleep(60)  # Проверяем каждую минуту
                
                if not self.is_bot_running():
                    logger.warning("Бот упал! Перезапуск...")
                    
                    if self.restart_count < self.max_restarts:
                        self.start_bot()
                        logger.info(f"Ожидание 30 секунд после перезапуска...")
                        time.sleep(30)  # Ждем стабилизации
                    else:
                        logger.error(f"Достигнут лимит перезапусков ({self.max_restarts})")
                        break
                else:
                    # Бот работает, записываем heartbeat
                    if int(time.time()) % 300 == 0:  # Каждые 5 минут
                        logger.info(f"Бот работает. PID: {self.bot_pid}, uptime: {self.get_uptime()} сек")
                        
            except KeyboardInterrupt:
                logger.info("Остановка по запросу пользователя")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(30)
        
        logger.info("=== ЗАВЕРШЕНИЕ СУПЕРВИЗОРА ===")
    
    def get_uptime(self):
        """Получает время работы процесса"""
        if self.bot_pid:
            try:
                with open(f'/proc/{self.bot_pid}/stat', 'r') as f:
                    stats = f.read().split()
                    uptime_ticks = int(stats[21])  # Время в тиках
                    uptime_seconds = uptime_ticks / 100  # Конвертируем в секунды
                    return int(uptime_seconds)
            except:
                return 0
        return 0

def main():
    supervisor = BotSupervisor()
    supervisor.monitor()

if __name__ == '__main__':
    main()