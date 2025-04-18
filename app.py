import os
import time
import qrcode
import smtplib
import ssl
import gspread
import json
import traceback
import random
import re
from email.message import EmailMessage
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask
import threading

app = Flask(__name__)

# ------------------------------
# Настройка Google Sheets API
# ------------------------------
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
if not SPREADSHEET_ID:
    raise ValueError("❌ Ошибка: SPREADSHEET_ID не найдено!")

CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
if not CREDENTIALS_JSON:
    raise ValueError("❌ Ошибка: GOOGLE_CREDENTIALS_JSON не найдено!")

try:
    creds_dict = json.loads(CREDENTIALS_JSON)
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n").strip()
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1
except Exception as e:
    raise ValueError(f"❌ Ошибка подключения к Google Sheets: {e}")

# ------------------------------
# Настройка SMTP (Brevo)
# ------------------------------
SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

if not SMTP_USER or not SMTP_PASSWORD:
    raise ValueError("❌ Ошибка: SMTP_USER или SMTP_PASSWORD не найдены!")

# ------------------------------
# Проверка ASCII-символов в email
# ------------------------------
def is_ascii_email(email):
    try:
        email.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False

# ------------------------------
# Отправка письма
# ------------------------------
def send_email(email, qr_filename, language, name=None, row_index=None, sheet=None):
    try:
        random_code = random.randint(1000, 9999)
        subject_ru = "Выигрывайте призы на BI Ecosystem в Шымкенте - уже сегодня!"
        subject_kz = "Бүгін Шымкентте өтетін BI Ecosystem шарасында жүлде ұтып алыңыз!"

        msg = EmailMessage()
        msg["From"] = "noreply@biecosystem.kz"
        msg["To"] = email
        msg["Subject"] = subject_ru if language == "ru" else subject_kz
        msg.set_type("multipart/related")

        template_filename = f"shym{language}.html"
        if os.path.exists(template_filename):
            with open(template_filename, "r", encoding="utf-8") as template_file:
                html_content = template_file.read()
        else:
            print(f"❌ Файл шаблона {template_filename} не найден.")
            return False

        unique_id = random.randint(100000, 999999)
        html_content = html_content.replace("<!--UNIQUE_PLACEHOLDER-->", str(unique_id))

        logo_path = "logo.png"
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as logo_file:
                msg.add_related(logo_file.read(), maintype="image", subtype="png", filename="logo.png", cid="logo")
            html_content = html_content.replace('src="logo.png"', 'src="cid:logo"')

        with open(qr_filename, "rb") as qr_file:
            msg.add_related(qr_file.read(), maintype="image", subtype="png", filename="qrcode.png", cid="qr")

        html_content = html_content.replace('src="qrcode.png"', 'src="cid:qr"')
        msg.add_alternative(html_content, subtype="html")

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"✅ Письмо отправлено на {email}")
        return True

    except smtplib.SMTPNotSupportedError as smtp_err:
        print(f"❌ SMTP ошибка: {smtp_err}")
        traceback.print_exc()
        if sheet and row_index is not None:
            sheet.update_cell(row_index, 9, "Error")
        return False

    except UnicodeEncodeError as unicode_err:
        print(f"❌ Unicode ошибка: {unicode_err}")
        traceback.print_exc()
        if sheet and row_index is not None:
            sheet.update_cell(row_index, 9, "Error")
        return False

    except Exception as e:
        print(f"❌ Другая ошибка при отправке письма: {e}")
        traceback.print_exc()
        if sheet and row_index is not None:
            sheet.update_cell(row_index, 9, "Error")
        return False

# ------------------------------
# Обработка новых гостей
# ------------------------------
def process_new_guests():
    try:
        all_values = sheet.get_all_values()

        for i in range(1, len(all_values)):
            row = all_values[i]
            if len(row) < 10:
                continue

            name = row[0].strip()
            email = row[1].strip()
            phone = row[2].strip()
            language = row[3].strip().lower()
            status = row[8].strip().lower()

            if not name or not phone or not email or status == "done" or status == "error":
                continue

            if not is_ascii_email(email):
                print(f"❌ Email содержит не-ASCII символы: {email}")
                sheet.update_cell(i + 1, 9, "Error")
                continue

            qr_data = f"Name: {name}\nPhone: {phone}\nEmail: {email}"
            os.makedirs("qrcodes", exist_ok=True)
            qr_filename = f"qrcodes/{email.replace('@', '_')}.png"

            qr = qrcode.make(qr_data)
            qr.save(qr_filename)

            if send_email(email, qr_filename, language, name=name, row_index=i+1, sheet=sheet):
                sheet.update_cell(i+1, 9, "Done")

            time.sleep(1)

    except Exception as e:
        print(f"[Ошибка] при обработке гостей: {e}")
        traceback.print_exc()

# ------------------------------
# Фоновая задача
# ------------------------------
def background_task():
    while True:
        try:
            process_new_guests()
        except Exception as e:
            print(f"[Ошибка в фоновом процессе] {e}")
            traceback.print_exc()
        time.sleep(15)

threading.Thread(target=background_task, daemon=True).start()

# ------------------------------
# Flask-приложение
# ------------------------------
@app.route("/")
def home():
    return "QR Code Generator is running!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
