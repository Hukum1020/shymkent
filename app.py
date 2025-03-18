import os
import time
import qrcode
import smtplib
import ssl
import gspread
import json
import traceback
from email.message import EmailMessage
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask

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

def send_email(email, name, qr_filename, language):
    try:
        msg = EmailMessage()
        msg["From"] = SMTP_USER
        msg["To"] = email
        msg["Subject"] = "Ваш QR-код" if language == "ru" else "QR-код билеті"

        if language == "ru":
            body = f"""Спасибо за регистрацию на BI Ecosystem!  

Это ваш входной билет, пожалуйста, не удаляйте это письмо. QR-код нужно предъявить на входе для участия в розыгрыше ценных призов!  

Ждём вас 15 апреля в 9:30 по адресу: мкр. Шымсити 101/1, Tulip Hall"""
        else:  # "kz"
            body = """BI Ecosystem жүйесіне тіркелгеніңізге рахмет! 

Бұл сіздің кіруге арналған билетіңіз, өтініш осы хатты өшірмеңіз. Ұтыс ойындарында қатысу үшін осы QR кодты кіру есігі алдында көрсету қажет.

СІзді 15 сәуір күні сағат 09:30 Шымкент қаласы,  "Шымсити" ықшам ауданы, 101/1 Tulip Hall, мекен жайы бойынша күтеміз."""

        msg.set_content(body)

        with open(qr_filename, "rb") as qr_file:
            msg.add_attachment(
                qr_file.read(),
                maintype="image",
                subtype="png",
                filename="qrcode.png"
            )

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"[OK] Письмо отправлено на {email}")
        return True
    except Exception as e:
        print(f"[Ошибка] Не удалось отправить письмо на {email}: {e}")
        traceback.print_exc()
        return False

def process_new_guests():
    try:
        all_values = sheet.get_all_values()

        for i in range(1, len(all_values)):
            row = all_values[i]
            if len(row) < 11:  # Теперь проверяем, что есть хотя бы 11 колонок (до language)
                continue

            email, name, phone, status, language = row[0], row[1], row[2], row[7], row[10].strip().lower()

            if not name or not phone or not email or status.strip().lower() == "done":
                continue

            qr_data = f"Name: {name}\nPhone: {phone}\nEmail: {email}"
            os.makedirs("qrcodes", exist_ok=True)
            qr_filename = f"qrcodes/{email.replace('@', '_')}.png"

            qr = qrcode.make(qr_data)
            qr.save(qr_filename)

            if send_email(email, name, qr_filename, language):
                sheet.update_cell(i+1, 8, "Done")
    except Exception as e:
        print(f"[Ошибка] при обработке гостей: {e}")
        traceback.print_exc()

# Фоновый процесс (для обработки Google Sheets)
def background_task():
    while True:
        try:
            process_new_guests()
        except Exception as e:
            print(f"[Ошибка] {e}")
            traceback.print_exc()
        time.sleep(30)

# Запуск фонового процесса при старте
import threading
threading.Thread(target=background_task, daemon=True).start()

@app.route("/")
def home():
    return "QR Code Generator is running!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
