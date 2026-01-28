from telethon.sync import TelegramClient
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.types import InputPhoneContact
from telethon.errors import (
    PhoneNumberBannedError,
    PhoneNumberInvalidError,
    FloodWaitError,
    SessionPasswordNeededError,
    UserPrivacyRestrictedError,
    ChatAdminRequiredError,
    UserAlreadyParticipantError
)
import time
import os
from tqdm import tqdm

# Файлы конфигурации и результатов
CONFIG_FILE = "config.txt"
INPUT_FILE = "numbers.txt"
SESSION_FILE = 'user_session.session'
EXISTING_FILE = "existing_results.csv"  # CSV для Excel
NON_EXISTING_FILE = "non_existing_results.csv"


def load_config():
    """Загружает API_ID и API_HASH"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
            if len(lines) >= 2:
                try:
                    api_id = int(lines[0].strip())
                    api_hash = lines[1].strip()
                    return api_id, api_hash
                except ValueError:
                    pass

    print("⚙️ Не найдена конфигурация API.")
    api_id = int(input("Введите API_ID: ").strip())
    api_hash = input("Введите API_HASH: ").strip()

    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        f.write(f"{api_id}\n{api_hash}\n")

    return api_id, api_hash


def ask_for_channel():
    """Спрашивает про канал с простым выбором y/n"""
    while True:
        ans = input("Хотите добавлять найденных пользователей в чат? (y/n): ").strip().lower()

        if ans in ['y', 'yes']:
            print("\n💡 Рекомендация: вы должны быть администратором этого чата.")
            link = input("Введите ссылку или @имя чата: ").strip()
            return link
        elif ans in ['n', 'no']:
            return None
        else:
            print("❌ Пожалуйста, введите только y или n.")


def init_result_files():
    """Создает CSV файлы с заголовками (разделитель ;) для Excel"""

    # Заголовки для найденных пользователей
    headers_found = [
        "Номер телефона",
        "Имя пользователя",
        "№ (в списке)",
        "В Telegram",
        "Добавлен в чат",
        "Статус / Ошибка"
    ]

    with open(EXISTING_FILE, 'w', encoding='utf-8-sig') as f:  # utf-8-sig для Excel
        f.write(";".join(headers_found) + "\n")

    # Заголовки для ненайденных
    headers_not_found = [
        "Номер телефона",
        "В Telegram",
        "Статус / Ошибка"
    ]

    with open(NON_EXISTING_FILE, 'w', encoding='utf-8-sig') as f:
        f.write(";".join(headers_not_found) + "\n")


def check_numbers():
    init_result_files()

    if not os.path.exists(INPUT_FILE):
        print(f"❌ Файл {INPUT_FILE} не найден!")
        return

    # 1. Загрузка API
    API_ID, API_HASH = load_config()

    # 2. Вопрос про чат
    chat_link = ask_for_channel()

    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)

    # Статистика
    stats = {
        'found': 0,
        'added_true': 0,
        'added_false': 0,  # Общий счетчик ошибок добавления
        'chat_closed': 0,
        'admin_error': 0,
        'not_registered': 0
    }

    try:
        print("🔒 Авторизация в Telegram...")
        client.start()

        channel_entity = None
        if chat_link:
            try:
                print(f"🔗 Проверка доступа к чату: {chat_link}...")
                channel_entity = client.get_entity(chat_link)
                print(f"✅ Чат найден. Режим добавления включен.")
            except Exception as e:
                print(f"⚠️ Ошибка поиска чата: {str(e)}. Режим добавления отключен.")
                channel_entity = None

        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            phones = [line.strip() for line in f if line.strip()]

        total = len(phones)
        if total == 0:
            print("❌ В файле нет номеров для проверки")
            return

        print(f"📋 Найдено номеров для проверки: {total}")
        print("⏳ Начинаем обработку...\n")

        progress_bar = tqdm(phones, desc="Обработка", unit="номер")

        for i, phone in enumerate(progress_bar, start=1):
            try:
                progress_bar.set_postfix_str(f"Текущий: {phone[:10]}...")

                contact = InputPhoneContact(
                    client_id=0,
                    phone=phone,
                    first_name=f"{i}",
                    last_name=""
                )

                result = client(ImportContactsRequest([contact]))

                # Переменные для CSV
                in_tg = "No"
                added = "N/A"
                status = "Не зарегистрирован"
                username = "Нет"

                if result.users:
                    user = result.users[0]
                    stats['found'] += 1
                    in_tg = "Yes"
                    username = f"@{user.username}" if user.username else "Нет"

                    # Логика добавления
                    if channel_entity:
                        try:
                            client(InviteToChannelRequest(channel_entity, [user]))
                            added = "True"
                            status = "Успешно добавлен"
                            stats['added_true'] += 1
                        except UserAlreadyParticipantError:
                            added = "True"
                            status = "Уже был участником чата"
                            stats['added_true'] += 1
                        except UserPrivacyRestrictedError:
                            added = "False"
                            status = "Закрытый чат"
                            stats['added_false'] += 1
                            stats['chat_closed'] += 1
                        except ChatAdminRequiredError:
                            added = "False"
                            status = "Ошибка: Нет прав администратора"
                            stats['added_false'] += 1
                            stats['admin_error'] += 1
                            if stats['admin_error'] == 1:
                                print("\n⚠️ У аккаунта нет прав для добавления людей!")
                        except FloodWaitError as e:
                            added = "False"
                            status = f"FloodWait (Лимит на {e.seconds}с)"
                            stats['added_false'] += 1  # Считаем как неудачу в этом цикле
                            progress_bar.write(f"⏳ Лимит добавлений. Ждем {e.seconds} сек...")
                            time.sleep(e.seconds)
                        except Exception as e:
                            added = "False"
                            status = f"Ошибка добавления: {str(e)}"
                            stats['added_false'] += 1
                    else:
                        added = "N/A"  # Чат не выбран
                        status = "Пользователь найден (без попытки добавления)"

                    # Запись в CSV (найденные)
                    row = [
                        phone,
                        username,
                        str(i),
                        in_tg,
                        added,
                        status
                    ]
                    with open(EXISTING_FILE, 'a', encoding='utf-8-sig') as f:
                        f.write(";".join(row) + "\n")

                else:
                    # Если юзер не найден
                    stats['not_registered'] += 1
                    in_tg = "No"
                    status = "Не зарегистрирован в Telegram"

                    row = [
                        phone,
                        in_tg,
                        status
                    ]
                    with open(NON_EXISTING_FILE, 'a', encoding='utf-8-sig') as f:
                        f.write(";".join(row) + "\n")

            except PhoneNumberInvalidError:
                with open(NON_EXISTING_FILE, 'a', encoding='utf-8-sig') as f:
                    f.write(f"{phone};No;Неверный формат номера\n")

            except PhoneNumberBannedError:
                # Записываем в файл найденных, но с пометкой
                stats['found'] += 1
                row = [phone, "Забанен", str(i), "Yes", "False", "Аккаунт заблокирован"]
                with open(EXISTING_FILE, 'a', encoding='utf-8-sig') as f:
                    f.write(";".join(row) + "\n")

            except FloodWaitError as e:
                wait_time = e.seconds
                progress_bar.write(f"⏳ Лимит запросов. Ждем {wait_time} сек...")
                time.sleep(wait_time)
                continue

            except Exception as e:
                with open(NON_EXISTING_FILE, 'a', encoding='utf-8-sig') as f:
                    f.write(f"{phone};No;Ошибка проверки: {str(e)[:30]}\n")

            time.sleep(7)

    except SessionPasswordNeededError:
        print("\n🔐 Требуется двухфакторная аутентификация!")
        password = input("Введите пароль: ")
        client.start(password=password)
        return check_numbers()

    except Exception as e:
        print(f"\n⚠️ Критическая ошибка: {str(e)}")

    finally:
        client.disconnect()

        # Красивая сводка с условным отображением
        print("\n" + "=" * 40)
        print("          📊 СВОДКА РЕЗУЛЬТАТОВ")
        print("=" * 40)
        print(f"📑 Всего проверено:          {total}")
        print("-" * 40)
        print(f"👤 В Telegram (найдено):     {stats['found']}")
        print(f"✅ Успешно добавлено:        {stats['added_true']}")

        # Выводим общее количество неудач, только если оно есть
        if stats['added_false'] > 0:
            print(f"❌ Не добавлено (ошибки):    {stats['added_false']}")

            # Выводим детали только если они > 0
            if stats['chat_closed'] > 0:
                print(f"   🔒 Закрытый чат:       {stats['chat_closed']}")
            if stats['admin_error'] > 0:
                print(f"   ⛔ Нет прав админа:     {stats['admin_error']}")

        print(f"❌ Не в Telegram:            {stats['not_registered']}")
        print("=" * 40)
        print(f"📂 Результат (Excel): {os.path.abspath(EXISTING_FILE)}")
        print("=" * 40 + "\n")


if __name__ == '__main__':
    check_numbers()
