#!/usr/bin/env python3
"""
Проверка чеков через Google Gemini.
Скачивает фото из Telegram по file_id и анализирует.
"""
import os
import json
import urllib.request
import tempfile

_MODELS = ["gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash"]


def _download_tg_file(bot_token, file_id):
    """Скачивает файл из Telegram. Возвращает путь к временному файлу или None."""
    try:
        # 1. getFile
        r = urllib.request.urlopen(
            f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}",
            timeout=15
        )
        data = json.loads(r.read().decode())
        if not data.get('ok'):
            return None
        file_path = data['result']['file_path']
        # 2. Скачиваем
        url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        suffix = os.path.splitext(file_path)[1] or '.jpg'
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        with urllib.request.urlopen(url, timeout=30) as resp:
            with os.fdopen(fd, 'wb') as f:
                f.write(resp.read())
        return tmp_path
    except Exception as e:
        return None


def check_receipt(cfg, file_id, expected_sum=None):
    """
    Проверяет чек через Gemini.
    Возвращает dict: {ok, is_receipt, suspicious, confidence, sum, date, notes}
    При любой ошибке: {'ok': False, 'error': '...'}
    """
    api_key = cfg.get('GEMINI_API_KEY', '')
    if not api_key:
        return {'ok': False, 'error': 'no_api_key'}

    bot_token = cfg.get('BOT_TOKEN', '')
    if not bot_token:
        return {'ok': False, 'error': 'no_bot_token'}

    tmp_path = _download_tg_file(bot_token, file_id)
    if not tmp_path:
        return {'ok': False, 'error': 'download_failed'}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        # Читаем фото
        with open(tmp_path, 'rb') as f:
            img_bytes = f.read()

        # Определяем mime
        ext = os.path.splitext(tmp_path)[1].lower()
        mime = 'image/jpeg'
        if ext == '.png': mime = 'image/png'
        elif ext == '.webp': mime = 'image/webp'

        expected_line = ""
        if expected_sum:
            try:
                expected_line = f"\nОжидаемая сумма: {float(expected_sum):.2f} USDT"
            except:
                pass

        prompt = f"""Ты проверяешь скриншот чека об оплате.
Верни СТРОГО JSON без markdown.

Задачи:
1. Это настоящий скриншот из банковского приложения / крипто-кошелька?
2. Есть ли признаки фотошопа? (несовпадение шрифтов, обрезанные края текста, наложение, неровные границы цифр, несоответствие цвета фона вокруг текста)
3. Извлеки сумму (только цифру) и дату (YYYY-MM-DD).
4. Если указана ожидаемая сумма — совпадает ли она.{expected_line}

Формат ответа (только JSON):
{{
  "is_receipt": true,
  "suspicious": false,
  "confidence": 0.95,
  "sum": "5.00",
  "date": "2026-10-01",
  "notes": "краткое объяснение до 100 символов"
}}"""

        response = None
        last_err = None
        for _m in _MODELS:
            try:
                response = client.models.generate_content(
                    model=_m,
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type=mime),
                        prompt
                    ]
                )
                break
            except Exception as _me:
                last_err = _me
                continue
        if response is None:
            return {'ok': False, 'error': f'all_models_failed: {str(last_err)[:80]}'}

        text = (response.text or '').strip()
        # Убираем возможные ```json ... ```
        if text.startswith('```'):
            text = text.strip('`')
            if text.startswith('json'):
                text = text[4:].strip()
        # Ищем первую { и последнюю }
        i1 = text.find('{')
        i2 = text.rfind('}')
        if i1 >= 0 and i2 > i1:
            text = text[i1:i2+1]

        result = json.loads(text)
        result['ok'] = True
        return result
    except Exception as e:
        return {'ok': False, 'error': f'gemini_error: {e}'}
    finally:
        try:
            os.remove(tmp_path)
        except: pass
