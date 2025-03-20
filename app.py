import os
import time
import qrcode
import smtplib
import ssl
import gspread
import json
import traceback
import random
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
# Настройка SMTP (Gmail)
# ------------------------------
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

if not SMTP_USER or not SMTP_PASSWORD:
    raise ValueError("❌ Ошибка: SMTP_USER или SMTP_PASSWORD не найдены!")

def send_email(email, qr_filename, language):
    try:
        subject_ru = f"Ваш персональный QR-код #{random.randint(1000, 9999)}"
        subject_kz = f"Сіздің жеке QR-кодыңыз #{random.randint(1000, 9999)}"
        msg = EmailMessage()
        msg["From"] = SMTP_USER
        msg["To"] = email
        msg["Subject"] = subject_ru if language == "ru" else subject_kz
        msg.set_type("multipart/related")  # Оставляем для встраивания QR-кода

        # Загружаем HTML-шаблон
        template_filename = f"shym{language}.html"
        if os.path.exists(template_filename):
            with open(template_filename, "r", encoding="utf-8") as template_file:
                html_content = template_file.read()
        else:
            print(f"❌ Файл шаблона {template_filename} не найден.")
            return False

        # ✅ Добавляем уникальный идентификатор в письмо
        unique_id = random.randint(100000, 999999)
        html_content = html_content.replace("<!--UNIQUE_PLACEHOLDER-->", str(unique_id))

        # ✅ Встраиваем логотип как вложение
        logo_path = "logo.png"
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as logo_file:
                msg.add_related(logo_file.read(), maintype="image", subtype="png", filename="logo.png", cid="logo")
            html_content = html_content.replace('src="logo.png"', 'src="cid:logo"')
        else:
            print("⚠️ Логотип не найден, письмо отправляется без него.")

        # ✅ Встраиваем QR-код
        with open(qr_filename, "rb") as qr_file:
            msg.add_related(qr_file.read(), maintype="image", subtype="png", filename="qrcode.png", cid="qr")

        # Подставляем QR-код в HTML
        html_content = html_content.replace('src="qrcode.png"', 'src="cid:qr"')

        # Добавляем HTML-контент
        msg.add_alternative(html_content, subtype="html")

        # Отправка письма
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"✅ Письмо отправлено на {email}")
        return True
    except Exception as e:
        print(f"❌ Ошибка при отправке письма: {e}")
        traceback.print_exc()
        return False

def process_new_guests():
    try:
        all_values = sheet.get_all_values()
        
        for i in range(1, len(all_values)):
            row = all_values[i]
            if len(row) < 10:
                continue
            
            email, name, phone, status, language = row[1], row[0], row[2], row[8], row[3].strip().lower()
            
            if not name or not phone or not email or status.strip().lower() == "done":
                continue
            
            qr_data = f"Name: {name}\nPhone: {phone}\nEmail: {email}"
            os.makedirs("qrcodes", exist_ok=True)
            qr_filename = f"qrcodes/{email.replace('@', '_')}.png"
            
            qr = qrcode.make(qr_data)
            qr.save(qr_filename)
            
            if send_email(email, qr_filename, language):
                sheet.update_cell(i+1, 9, "Done")
    except Exception as e:
        print(f"[Ошибка] при обработке гостей: {e}")
        traceback.print_exc()

# Фоновый процесс с бесконечным циклом проверки новых пользователей
def background_task():
    while True:
        try:
            process_new_guests()
        except Exception as e:
            print(f"[Ошибка] {e}")
            traceback.print_exc()
        time.sleep(30)  # Проверять каждые 30 секунд

# Запуск фонового процесса
threading.Thread(target=background_task, daemon=True).start()

@app.route("/")
def home():
    return "QR Code Generator is running!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
