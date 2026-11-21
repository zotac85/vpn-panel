import urllib.request
import os
import tempfile
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TOKEN_FILE = "/root/vpn-subscription/token.json"
FOLDER_ID = "1fFY8-dXCPsQ3DLkpRZ2sokvCWBfA5n5c"
API_KEY = "AIzaSyB7EktR2iPUkecLUhB89ir97Zhg2YhjQGI"
LOCAL_SERVER = "http://127.0.0.1:8444"

def get_drive_link(key_name, sub_type="sub_dark"):
    filename = f"{sub_type}_{key_name}.txt"
    local_url = f"{LOCAL_SERVER}/{sub_type}/{key_name}"
    
    # 1. Скачиваем конфиг с локального сервера (с авто-рестартом службы при 404/сбое)
    content = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(local_url)
            with urllib.request.urlopen(req, timeout=25) as response:
                content = response.read()
            break
        except Exception as e:
            print(f"[GDrive] Попытка {attempt+1} скачивания {local_url} не удалась: {e}")
            if attempt == 0:
                import subprocess, time
                subprocess.run(["systemctl", "restart", "npvt-sub-server.service"], capture_output=True)
                time.sleep(1.5)
            else:
                return None

    # Сохраняем во временный файл
    fd, tmp_path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, 'wb') as f:
        f.write(content)

    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE)
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        
        # Ищем, есть ли уже такой файл на Диске
        query = f"name='{filename}' and '{FOLDER_ID}' in parents and trashed=false"
        res = drive.files().list(q=query, fields="files(id)").execute()
        files = res.get('files', [])
        
        media = MediaFileUpload(tmp_path, mimetype="text/plain")
        
        if files:
            # Файл есть - обновляем содержимое (ID и ссылка не меняются)
            file_id = files[0]['id']
            drive.files().update(fileId=file_id, media_body=media).execute()
        else:
            # Файла нет - создаем новый
            file_metadata = {'name': filename, 'parents': [FOLDER_ID]}
            file = drive.files().create(body=file_metadata, media_body=media, fields="id").execute()
            file_id = file.get("id")
            # Открываем доступ
            drive.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
            
        return f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={API_KEY}"
    except Exception as e:
        print(f"[GDrive] Ошибка API: {e}")
        return None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
