import asyncio
import getpass
import json
import re
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

API_ID = 30714241
API_HASH = "d1c69b7042828fced1edadc0cc7189c0"

CONFIG_FILE = "config.json"
PHONE_REGEX = re.compile(r"^\+[1-9]\d{7,14}$")


def load_config() -> dict:
    if Path(CONFIG_FILE).exists():
        try:
            with open(CONFIG_FILE, "r") as file_handle:
                return json.load(file_handle)
        except Exception:
            return {}
    return {}


def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w") as file_handle:
        json.dump(config, file_handle, indent=2)


def prompt_phone_number() -> str:
    while True:
        phone = input("Enter phone number in international format (example: +79123456789): ").strip()
        if not phone:
            print("Phone number is required.")
            continue
        if not PHONE_REGEX.match(phone):
            print("Invalid format. Use +<countrycode><number> with 8-15 digits.")
            continue
        return phone


async def create_session() -> bool:
    if not sys.stdin.isatty():
        print("Interactive terminal is required to create a session.")
        return False

    config = load_config()
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()

    try:
        while True:
            phone = prompt_phone_number()
            try:
                await client.send_code_request(phone)
                break
            except PhoneNumberInvalidError:
                print("Phone number is invalid. Try again.")

        attempts = 0
        while True:
            code = input("Enter the code from Telegram: ").strip()
            if not code:
                print("Code is required.")
                continue
            try:
                await client.sign_in(phone=phone, code=code)
                break
            except PhoneCodeInvalidError:
                attempts += 1
                if attempts >= 3:
                    print("Too many invalid attempts.")
                    return False
                print("Invalid code. Try again.")
            except PhoneCodeExpiredError:
                print("Code expired. Sending a new one...")
                await client.send_code_request(phone)
                attempts = 0
            except SessionPasswordNeededError:
                password = getpass.getpass("Enter 2FA password: ")
                try:
                    await client.sign_in(password=password)
                    break
                except Exception as exc:
                    print(f"2FA password error: {exc}")
                    return False

        string_session = client.session.save()
        config["string_session"] = string_session
        save_config(config)
        print("Session saved to config.json")
        return True
    finally:
        await client.disconnect()


def main() -> int:
    try:
        success = asyncio.run(create_session())
    except KeyboardInterrupt:
        print("\nSession creation cancelled.")
        return 1
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
