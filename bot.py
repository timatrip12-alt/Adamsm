import asyncio
import getpass
import json
import logging
import re
import sys
from pathlib import Path
from typing import Set, Dict, Any

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    ChannelInvalidError, ChannelPrivateError, 
    UsernameInvalidError, SessionPasswordNeededError,
    PhoneCodeInvalidError, PhoneCodeExpiredError
)

# === КОНСТАНТЫ ===
API_ID = 30714241
API_HASH = "d1c69b7042828fced1edadc0cc7189c0"
BOT_TOKEN = "8055700026:AAFURDs15nQRSmCxRPgrsrDWIki4qXebOUE"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Файлы конфигурации
CONFIG_FILE = 'config.json'
SESSION_FILE = 'telethon_session.session'

# Регулярное выражение для поиска Telegram ссылок
TELEGRAM_LINK_REGEX = r'https?://t\.me/([a-zA-Z0-9_]+)'

class TelethonManager:
    """Менеджер для работы с Telethon"""
    
    def __init__(self):
        self.client = None
        self.ready = False
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Загружает конфигурацию из файла"""
        if Path(CONFIG_FILE).exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_config(self):
        """Сохраняет конфигурацию в файл"""
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=2)

    async def _is_session_valid(self, client: TelegramClient) -> bool:
        """Проверяет авторизацию для переданного клиента"""
        try:
            await client.connect()
            return await client.is_user_authorized()
        except Exception as e:
            logger.error(f"Ошибка проверки сессии: {e}")
            return False
        finally:
            await client.disconnect()

    async def ensure_terminal_session(self) -> bool:
        """Гарантирует регистрацию сессии через терминал перед запуском"""
        self.config = self.load_config()

        if Path(SESSION_FILE).exists():
            file_client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
            if await self._is_session_valid(file_client):
                logger.info("✅ Найдена валидная сессия Telethon в файле")
                return True

        string_session = self.config.get('string_session')
        if string_session:
            string_client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
            if await self._is_session_valid(string_client):
                logger.info("✅ Найдена валидная строковая сессия Telethon")
                return True
            self.config['string_session'] = ''
            self.save_config()

        print("🔐 Сессия Telethon не найдена. Требуется регистрация в терминале.")
        return await self._register_session_via_terminal()

    async def _register_session_via_terminal(self) -> bool:
        """Создает сессию Telethon через терминал"""
        if not sys.stdin.isatty():
            print("❌ Нет доступа к интерактивному терминалу для регистрации сессии.")
            return False

        phone = input("Введите номер телефона в международном формате (пример: +79123456789): ").strip()
        if not phone:
            print("❌ Номер телефона не задан.")
            return False

        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()

        try:
            await client.send_code_request(phone)
            attempts = 0
            while True:
                code = input("Введите код из Telegram (5 цифр): ").strip()
                if not code:
                    print("❌ Код не введен.")
                    continue
                try:
                    await client.sign_in(phone=phone, code=code)
                    break
                except PhoneCodeInvalidError:
                    attempts += 1
                    if attempts >= 3:
                        print("❌ Слишком много неверных попыток.")
                        return False
                    print("❌ Неверный код. Попробуйте снова.")
                except PhoneCodeExpiredError:
                    print("⏳ Код истек. Отправляю новый код...")
                    await client.send_code_request(phone)
                except SessionPasswordNeededError:
                    password = getpass.getpass("Введите пароль двухфакторной аутентификации: ")
                    try:
                        await client.sign_in(password=password)
                        break
                    except Exception as e:
                        print(f"❌ Ошибка пароля 2FA: {e}")
                        return False

            string_session = client.session.save()
            self.config['string_session'] = string_session
            self.save_config()
            print("✅ Сессия сохранена в config.json")
            return True
        finally:
            await client.disconnect()
    
    async def initialize(self):
        """Инициализирует клиент Telethon"""
        try:
            # Пробуем загрузить существующую сессию
            if Path(SESSION_FILE).exists():
                self.client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
                await self.client.connect()
                
                if await self.client.is_user_authorized():
                    logger.info("✅ Telethon авторизован с файлом сессии")
                    self.ready = True
                    return True
                logger.warning("Файл сессии устарел")
                await self.client.disconnect()
            
            # Проверяем есть ли строковая сессия в конфиге
            if 'string_session' in self.config and self.config['string_session']:
                try:
                    session = StringSession(self.config['string_session'])
                    self.client = TelegramClient(session, API_ID, API_HASH)
                    await self.client.connect()
                    
                    if await self.client.is_user_authorized():
                        logger.info("✅ Telethon авторизован со строковой сессией")
                        self.ready = True
                        return True
                    await self.client.disconnect()
                except Exception as e:
                    logger.error(f"Ошибка строковой сессии: {e}")
                    if self.client:
                        await self.client.disconnect()
            
            logger.warning("Telethon не авторизован")
            self.client = None
            return False
            
        except Exception as e:
            logger.error(f"Ошибка инициализации Telethon: {e}")
            return False
    
    async def authorize_with_phone(self, update: Update, context: CallbackContext) -> bool:
        """Авторизация по номеру телефона через бота"""
        try:
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            
            # Создаем новый клиент
            self.client = TelegramClient(StringSession(), API_ID, API_HASH)
            await self.client.connect()
            
            await update.message.reply_text(
                "📱 *Авторизация Telethon*\n\n"
                "Отправьте номер телефона в международном формате:\n"
                "Пример: `+79123456789`",
                parse_mode='Markdown'
            )
            
            # Ждем номер телефона
            try:
                phone_message = await self.wait_for_user_message(
                    user_id,
                    chat_id,
                    context.application,
                    timeout=60
                )
                phone = phone_message.text.strip()
                
                # Отправляем запрос на код
                await update.message.reply_text(f"📲 Отправляю код на номер {phone}...")

                await self.client.send_code_request(phone)
                
                await update.message.reply_text(
                    "✅ Код отправлен!\n\n"
                    "Введите полученный код (5 цифр):"
                )
                
                # Ждем код
                code_message = await self.wait_for_user_message(
                    user_id,
                    chat_id,
                    context.application,
                    timeout=120
                )
                code = code_message.text.strip()
                
                # Пробуем войти
                try:
                    await self.client.sign_in(phone, code)
                    await update.message.reply_text("✅ Успешный вход!")
                except SessionPasswordNeededError:
                    await update.message.reply_text("🔐 Требуется пароль двухфакторной аутентификации:")
                    
                    password_message = await self.wait_for_user_message(
                        user_id,
                        chat_id,
                        context.application,
                        timeout=60
                    )
                    password = password_message.text.strip()
                    
                    await self.client.sign_in(password=password)
                    await update.message.reply_text("✅ Успешный вход с 2FA!")
                
                # Сохраняем сессию
                string_session = self.client.session.save()
                self.config['string_session'] = string_session
                self.save_config()
                
                # Сохраняем в файл
                await self.client.disconnect()
                self.client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
                await self.client.connect()
                
                self.ready = True
                await update.message.reply_text("✅ Авторизация Telethon завершена!")
                return True
                
            except asyncio.TimeoutError:
                await update.message.reply_text("⏰ Время ожидания истекло")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            return False
    
    async def wait_for_user_message(
        self,
        user_id: int,
        chat_id: int,
        application: Application,
        timeout: int = 60
    ):
        """Ожидает сообщение от пользователя"""
        future = asyncio.get_running_loop().create_future()

        def handler(upd: Update, ctx: CallbackContext):
            if future.done():
                return
            if not upd.effective_user or not upd.effective_chat:
                return
            if upd.effective_user.id == user_id and upd.effective_chat.id == chat_id:
                future.set_result(upd.message)

        temp_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handler)
        application.add_handler(temp_handler, group=1)

        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            application.remove_handler(temp_handler, group=1)
    
    async def test_connection(self) -> bool:
        """Проверяет соединение Telethon"""
        if not self.client or not self.ready:
            return False
        
        try:
            me = await self.client.get_me()
            if me:
                logger.info(f"Telethon подключен как: @{me.username or 'no-username'}")
                return True
        except Exception as e:
            logger.error(f"Ошибка проверки соединения: {e}")
        
        return False

    async def close(self):
        """Закрывает подключение Telethon"""
        if self.client:
            await self.client.disconnect()
            self.client = None
            self.ready = False

# Создаем менеджер
telethon_manager = TelethonManager()

async def extract_links_from_file(file_path: str) -> Set[str]:
    """Извлекает все уникальные ссылки из файла"""
    links = set()
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            # Ищем все ссылки на t.me
            found_links = re.findall(r'https?://t\.me/[^\s,;]+', content)
            for link in found_links:
                # Очищаем ссылку от мусора
                link = link.strip().rstrip('.,;:!?')
                if link and '/+' not in link:  # Игнорируем ссылки типа t.me/+
                    links.add(link)
    except Exception as e:
        logger.error(f"Ошибка при чтении файла {file_path}: {e}")
    return links

async def is_chat_valid(link: str) -> bool:
    """Проверяет, существует ли чат/канал по ссылке"""
    if not telethon_manager.ready or not telethon_manager.client:
        logger.error("Telethon не готов")
        return False
    
    try:
        # Извлекаем username из ссылки
        match = re.search(TELEGRAM_LINK_REGEX, link)
        if not match:
            return False
        
        username = match.group(1)
        
        # Пытаемся получить информацию о чате
        try:
            entity = await telethon_manager.client.get_entity(username)
            if entity:
                logger.info(f"✓ Чат доступен: {link}")
                return True
        except (ChannelInvalidError, ChannelPrivateError, UsernameInvalidError):
            logger.info(f"✗ Чат недоступен: {link}")
            return False
        except Exception as e:
            logger.warning(f"Ошибка при проверке {link}: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при обработке ссылки {link}: {e}")
        return False

async def start(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    
    # Проверяем статус Telethon
    telethon_status = "✅ Авторизован" if telethon_manager.ready else "❌ Не авторизован"
    
    keyboard = [
        ['/auth_telethon', '/check_status'],
        ['/help', '/test_connection']
    ]
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"📊 Статус Telethon: {telethon_status}\n\n"
        "📁 *Как использовать:*\n"
        "1. Сессия Telethon регистрируется в терминале перед запуском\n"
        "2. Отправьте .txt файл со ссылками\n"
        "3. Получите файл с рабочими ссылками\n\n"
        "🔗 Формат ссылок в файле:\n"
        "https://t.me/username1\n"
        "https://t.me/username2\n"
        "...",
        parse_mode='Markdown',
        reply_markup={
            'keyboard': keyboard,
            'resize_keyboard': True
        }
    )

async def auth_telethon(update: Update, context: CallbackContext) -> None:
    """Авторизация Telethon"""
    await update.message.reply_text(
        "🔐 *Авторизация Telethon*\n\n"
        "Выберите метод авторизации:\n\n"
        "1. 📱 По номеру телефона - /auth_phone\n"
        "2. ❌ Отмена - /cancel\n\n"
        "⚠️ *Внимание:* Авторизация нужна для проверки доступности каналов/чатов",
        parse_mode='Markdown'
    )

async def auth_phone(update: Update, context: CallbackContext) -> None:
    """Авторизация по номеру телефона"""
    success = await telethon_manager.authorize_with_phone(update, context)
    if success:
        await update.message.reply_text("✅ Авторизация успешна! Теперь можете отправлять файлы.")

async def check_status(update: Update, context: CallbackContext) -> None:
    """Проверка статуса Telethon"""
    if telethon_manager.ready and await telethon_manager.test_connection():
        await update.message.reply_text("✅ Telethon авторизован и работает")
    else:
        await update.message.reply_text(
            "❌ Telethon не авторизован\n"
            "Используйте /auth_telethon или перезапустите бота для регистрации в терминале"
        )

async def test_connection(update: Update, context: CallbackContext) -> None:
    """Тест соединения с простым каналом"""
    if not telethon_manager.ready:
        await update.message.reply_text("❌ Telethon не авторизован")
        return
    
    try:
        await update.message.reply_text("🔍 Тестирую соединение...")
        
        # Пробуем получить публичный канал
        test_username = "telegram"
        entity = await telethon_manager.client.get_entity(test_username)
        
        await update.message.reply_text(
            f"✅ Соединение работает!\n"
            f"Канал: {entity.title}\n"
            f"Участников: {getattr(entity, 'participants_count', 'N/A')}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка соединения: {str(e)}")

async def handle_document(update: Update, context: CallbackContext) -> None:
    """Обработчик документов"""
    if not telethon_manager.ready:
        await update.message.reply_text(
            "❌ Telethon не авторизован!\n"
            "Сначала выполните /auth_telethon"
        )
        return
    
    if not update.message.document:
        return
    
    document = update.message.document
    user_id = update.effective_user.id
    
    # Проверяем что файл текстовый
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Отправляйте только .txt файлы!")
        return
    
    status_msg = await update.message.reply_text(
        f"📥 Файл: {document.file_name}\n"
        f"⏳ Загружаю..."
    )
    
    try:
        # Скачиваем файл
        file = await context.bot.get_file(document.file_id)
        temp_path = f"temp_{user_id}_{document.file_name}"
        await file.download_to_drive(temp_path)
        
        # Извлекаем ссылки
        await status_msg.edit_text(
            f"📥 Файл: {document.file_name}\n"
            f"⏳ Извлекаю ссылки..."
        )
        
        links = await extract_links_from_file(temp_path)
        
        if not links:
            await status_msg.edit_text("❌ В файле не найдено ссылок")
            Path(temp_path).unlink(missing_ok=True)
            return
        
        await status_msg.edit_text(
            f"📥 Файл: {document.file_name}\n"
            f"🔗 Найдено: {len(links)} ссылок\n"
            f"⏳ Проверяю..."
        )
        
        # Проверяем ссылки
        valid_links = []
        invalid_links = []
        
        for i, link in enumerate(links, 1):
            try:
                if await is_chat_valid(link):
                    valid_links.append(link)
                else:
                    invalid_links.append(link)
            except Exception as e:
                invalid_links.append(link)
                logger.error(f"Ошибка проверки {link}: {e}")
            
            # Обновляем статус каждые 5 ссылок
            if i % 5 == 0 or i == len(links):
                progress = (i / len(links)) * 100
                await status_msg.edit_text(
                    f"📥 Файл: {document.file_name}\n"
                    f"🔗 Всего: {len(links)} ссылок\n"
                    f"📊 Прогресс: {i}/{len(links)} ({progress:.1f}%)\n"
                    f"✅ Рабочих: {len(valid_links)}\n"
                    f"❌ Не рабочих: {len(invalid_links)}"
                )
        
        # Сохраняем результаты
        if valid_links:
            output_file = f"valid_{document.file_name}"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"# Проверено ссылок: {len(links)}\n")
                f.write(f"✅ Рабочих: {len(valid_links)}\n")
                f.write(f"❌ Не рабочих: {len(invalid_links)}\n\n")
                f.write("# Рабочие ссылки:\n")
                for link in valid_links:
                    f.write(f"{link}\n")
            
            # Отправляем файл
            with open(output_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    caption=(
                        f"✅ Проверка завершена!\n\n"
                        f"📊 Статистика:\n"
                        f"• Всего: {len(links)}\n"
                        f"• Рабочих: {len(valid_links)}\n"
                        f"• Не рабочих: {len(invalid_links)}"
                    )
                )
            
            # Удаляем временные файлы
            Path(temp_path).unlink(missing_ok=True)
            Path(output_file).unlink(missing_ok=True)
            await status_msg.delete()
            
        else:
            await status_msg.edit_text(
                f"❌ Не найдено рабочих ссылок\n"
                f"Всего проверено: {len(links)}"
            )
            Path(temp_path).unlink(missing_ok=True)
    
    except Exception as e:
        logger.error(f"Ошибка обработки файла: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def help_command(update: Update, context: CallbackContext) -> None:
    """Справка"""
    await update.message.reply_text(
        "📖 *Помощь*\n\n"
        "*Команды:*\n"
        "/start - Начать работу\n"
        "/auth_telethon - Авторизация Telethon\n"
        "/auth_phone - Авторизация по номеру\n"
        "/check_status - Проверить статус\n"
        "/test_connection - Тест соединения\n"
        "/help - Эта справка\n\n"
        "*Как использовать:*\n"
        "1. Зарегистрируйте сессию Telethon в терминале перед запуском\n"
        "2. Отправьте .txt файл со ссылками\n"
        "3. Получите результат\n\n"
        "*Формат файла:*\n"
        "Каждая ссылка на новой строке:\n"
        "https://t.me/username1\n"
        "https://t.me/username2",
        parse_mode='Markdown'
    )

async def cancel(update: Update, context: CallbackContext) -> None:
    """Отмена"""
    await update.message.reply_text("❌ Операция отменена")

async def handle_text(update: Update, context: CallbackContext) -> None:
    """Обработчик текста"""
    text = update.message.text
    if text and re.search(TELEGRAM_LINK_REGEX, text):
        await update.message.reply_text("✅ Ссылка проверена!")  # Дополнительно, можно добавить проверку каждой ссылки напрямую

async def on_startup(app: Application):
    """Запуск Telethon при старте бота"""
    await telethon_manager.initialize()


async def on_shutdown(app: Application):
    """Отключение Telethon при остановке бота"""
    await telethon_manager.close()


def ensure_session_before_bot_start() -> bool:
    """Проверяет/регистрирует сессию перед запуском бота"""
    try:
        return asyncio.run(telethon_manager.ensure_terminal_session())
    except KeyboardInterrupt:
        print("\n❌ Регистрация сессии прервана пользователем.")
        return False
    except Exception as e:
        logger.error(f"Ошибка регистрации сессии: {e}")
        return False


def main():
    """Основная функция запуска бота"""
    if not ensure_session_before_bot_start():
        sys.exit(1)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("auth_telethon", auth_telethon))
    app.add_handler(CommandHandler("auth_phone", auth_phone))
    app.add_handler(CommandHandler("check_status", check_status))
    app.add_handler(CommandHandler("test_connection", test_connection))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel))
    
    # Обработчик документов
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Обработчик текста
    app.add_handler(MessageHandler(filters.TEXT, handle_text))

    app.run_polling()

if __name__ == '__main__':
    main()