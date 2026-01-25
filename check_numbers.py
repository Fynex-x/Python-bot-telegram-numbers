from telethon.sync import TelegramClient
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact
from telethon.errors import (
    PhoneNumberBannedError,
    PhoneNumberInvalidError,
    FloodWaitError,
    SessionPasswordNeededError
)
import time
import os
from tqdm import tqdm


CONFIG_FILE = 'config.txt'
INPUT_FILE = "numbers.txt"
SESSION_FILE = "user_session.session"
EXISTING_FILE = "existing_numbers.txt"
NON_EXISTING_FILE = "non_existing_numbers.txt"


def load_or_request_api():
    api_id = None
    api_hash = None

    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f if l.strip()]
            for l in lines:
                if l.startswith("API_ID="):
                    api_id = int(l.split("=", 1)[1])
                if l.startswith("API_HASH="):
                    api_hash = l.split("=", 1)[1]

    if api_id and api_hash:
        return api_id, api_hash

    print("API конфигурация не найдена.")
    api_id = int(input("Введите API ID: "))
    api_hash = input("Введите API HASH: ")

    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        f.write(f"API_ID={api_id}\n")
        f.write(f"API_HASH={api_hash}\n")

    return api_id, api_hash


def ensure_files():
    if not os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("")
        print(f"Создан пустой файл {INPUT_FILE}. Заполни его номерами.")

    if not os.path.exists(EXISTING_FILE):
        with open(EXISTING_FILE, 'w', encoding='utf-8') as f:
            f.write("Номер | Имя пользователя | Имя/Фамилия | Статус\n")
            f.write("-" * 70 + "\n")

    if not os.path.exists(NON_EXISTING_FILE):
        with open(NON_EXISTING_FILE, 'w', encoding='utf-8') as f:
            f.write("Номер | Причина\n")
            f.write("-" * 50 + "\n")


def check_numbers():
    ensure_files()
    api_id, api_hash = load_or_request_api()

    client = TelegramClient(SESSION_FILE, api_id, api_hash)

    try:
        client.start()

        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            phones = [line.strip() for line in f if line.strip()]

        if not phones:
            print("Нет номеров для проверки в numbers.txt")
            return

        progress_bar = tqdm(phones, desc="Проверка номеров", unit="номер")

        for i, phone in enumerate(progress_bar, start=1):
            try:
                progress_bar.set_postfix_str(f"{phone[:10]}...")
                contact = InputPhoneContact(client_id=0, phone=phone, first_name=str(i), last_name="")
                result = client(ImportContactsRequest([contact]))

                if result.users:
                    user = result.users[0]
                    username = f"@{user.username}" if user.username else "Нет"
                    first_name = user.first_name or ""
                    last_name = user.last_name or ""
                    full_name = f"{first_name} {last_name}".strip()
                    status = "Активен"
                    with open(EXISTING_FILE, 'a', encoding='utf-8') as f:
                        f.write(f"{phone} | {username} | {full_name} | {status}\n")
                else:
                    with open(NON_EXISTING_FILE, 'a', encoding='utf-8') as f:
                        f.write(f"{phone} | Не зарегистрирован в Telegram\n")

            except PhoneNumberInvalidError:
                with open(NON_EXISTING_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{phone} | Неверный формат номера\n")

            except PhoneNumberBannedError:
                with open(EXISTING_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{phone} | Забанен | Забанен | Заблокирован\n")

            except FloodWaitError as e:
                time.sleep(e.seconds)
                continue

            except Exception as e:
                with open(NON_EXISTING_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{phone} | Ошибка: {str(e)[:50]}\n")

            time.sleep(7)

    except SessionPasswordNeededError:
        pwd = input("Введите пароль двухфакторной аутентификации: ")
        client.start(password=pwd)
        return check_numbers()

    finally:
        client.disconnect()
        print("Готово")
        print(f"Результат: {EXISTING_FILE}")
        print(f"Проблемные: {NON_EXISTING_FILE}")


if __name__ == '__main__':
    check_numbers()
