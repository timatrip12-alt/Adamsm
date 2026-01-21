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
    FloodWaitError,
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


def describe_delivery(sent_code) -> str:
    if not sent_code or not getattr(sent_code, "type", None):
        return "Code was sent. Delivery type is unknown."
    type_name = sent_code.type.__class__.__name__
    if type_name == "SentCodeTypeApp":
        return "Code was sent to Telegram app (chat from Telegram)."
    if type_name == "SentCodeTypeSms":
        return "Code was sent via SMS."
    if type_name == "SentCodeTypeCall":
        return "Code will arrive via a phone call."
    if type_name == "SentCodeTypeFlashCall":
        return "Code will arrive via flash call."
    if type_name == "SentCodeTypeFragmentSms":
        return "Code was sent via fragment SMS."
    return f"Code was sent. Delivery type: {type_name}."


async def send_code(client: TelegramClient, phone: str, force_sms: bool = False):
    try:
        return await client.send_code_request(phone, force_sms=force_sms)
    except TypeError:
        return await client.send_code_request(phone)


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
                sent_code = await send_code(client, phone, force_sms=False)
                print(describe_delivery(sent_code))
                timeout = getattr(sent_code, "timeout", None)
                if timeout:
                    print(f"If the code did not arrive, wait {timeout} seconds before retrying.")
                break
            except PhoneNumberInvalidError:
                print("Phone number is invalid. Try again.")
            except FloodWaitError as exc:
                print(f"Too many requests. Wait {exc.seconds} seconds and retry.")
                return False

        attempts = 0
        while True:
            code = input("Enter the code from Telegram (or type 'resend'/'sms'): ").strip()
            if not code:
                print("Code is required.")
                continue
            if code.lower() in ("resend", "r", "sms"):
                force_sms = code.lower() == "sms"
                try:
                    sent_code = await send_code(client, phone, force_sms=force_sms)
                    print(describe_delivery(sent_code))
                    timeout = getattr(sent_code, "timeout", None)
                    if timeout:
                        print(f"Wait {timeout} seconds before retrying.")
                except FloodWaitError as exc:
                    print(f"Too many requests. Wait {exc.seconds} seconds and retry.")
                    return False
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
