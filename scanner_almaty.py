import os
import json
import gspread
from flask import Flask, request, jsonify
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# Подключение к Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

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

@app.route("/")
def home():
    return "QR Check-in System is running!", 200

@app.route("/check-in", methods=["POST"])
def check_in():
    try:
        data = request.json
        qr_data = data.get("qr_data")

        if not qr_data:
            return jsonify({"message": "❌ Ошибка: пустые данные QR-кода!"}), 400

        # Разбираем данные QR-кода (ожидается формат с Email)
        lines = qr_data.split("\n")
        email = None
        for line in lines:
            if "Email:" in line:
                email = line.replace("Email:", "").strip()
                break

        if not email:
            return jsonify({"message": "❌ Ошибка: не удалось извлечь Email из QR-кода!"}), 400

        # Читаем все строки из таблицы
        all_values = sheet.get_all_values()
        found = False

        for i, row in enumerate(all_values):
            if len(row) > 0 and row[0].strip() == email:  # Проверяем Email в 1-й колонке
                sheet.update_cell(i + 1, 9, "Пришёл")  # Колонка CheckIn (J = 9)
                found = True
                break

        if found:
            return jsonify({"message": f"✅ Гость {email} отмечен как 'Пришёл'"}), 200
        else:
            return jsonify({"message": "❌ Гость не найден в системе!"}), 404

    except Exception as e:
        return jsonify({"message": f"❌ Ошибка обработки: {e}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
