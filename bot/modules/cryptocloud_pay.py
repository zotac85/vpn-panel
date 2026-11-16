import requests
import time

API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1dWlkIjoiTVRNd016SXkiLCJ0eXBlIjoicHJvamVjdCIsInYiOiIyMDY4Yzc4ZmFlZTdiNmE5NjY3MWRiOWJiYmRiODE4YmZhMWVlOWMyZWNjY2NlMDhiNDk2YTBiYjI2Yzk0YmY3IiwiZXhwIjo4ODE5NDcwNDczNX0.WnKEzZoRbR65-g4wt7YyCbvpdyKDCAILAhewuaAAprk"
SHOP_ID = "3tWSAihdw2fFyh45"

def create_cryptocloud_invoice(amount_usd, order_id):
    url = "https://api.trybit.com/v2/invoice/create"
    headers = {
        "Authorization": f"Token {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "shop_id": SHOP_ID,
        "amount": float(amount_usd),
        "currency": "USD",
        "order_id": str(order_id),
        "add_fields": {
            "time_to_pay": {"hours": 1, "minutes": 0},
            "available_currencies": ["USDT_BSC"]
        }
    }
    try:
        res = requests.post(url, json=data, headers=headers, timeout=15)
        
        with open("/var/log/postback.log", "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] API Запрос: {data}\n")
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] API Ответ: {res.text}\n")

        res.raise_for_status()
        result = res.json()
        if result.get("status") == "success":
            return result["result"]["link"]
        else:
            return None
    except Exception as e:
        with open("/var/log/postback.log", "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Исключение API: {e}\n")
        return None
