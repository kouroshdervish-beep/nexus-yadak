import os
import re
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
import requests

app = Flask(__name__, static_folder=None)
BASE_DIR = Path(__file__).resolve().parent
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://pobxjrmphgiyqrlmvbyx.supabase.co').rstrip('/')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
SUPABASE_TABLE = os.getenv('SUPABASE_TABLE', 'yadakyar_orders')
KAVENEGAR_API_KEY = os.getenv('KAVENEGAR_API_KEY', '')
KAVENEGAR_SENDER = os.getenv('KAVENEGAR_SENDER', '')
ADMIN_PHONE = os.getenv('ADMIN_PHONE', '')


def send_sms(receptor: str, message: str) -> bool:
    """Send via Kavenegar only when credentials are configured."""
    if not KAVENEGAR_API_KEY or not receptor:
        return False
    url = f'https://api.kavenegar.com/v1/{KAVENEGAR_API_KEY}/sms/send.json'
    payload = {'receptor': receptor, 'message': message}
    if KAVENEGAR_SENDER:
        payload['sender'] = KAVENEGAR_SENDER
    response = requests.post(url, data=payload, timeout=15)
    response.raise_for_status()
    body = response.json()
    entries = body.get('entries') or []
    return bool(entries and entries[0].get('status') in (1, 4, 5, 6, 10, 11))

@app.get('/')
def home():
    return send_from_directory(BASE_DIR, 'index.html')

@app.get('/health')
def health():
    return jsonify({'ok': True, 'database_configured': bool(SUPABASE_SERVICE_ROLE_KEY), 'sms_configured': bool(KAVENEGAR_API_KEY)})

@app.post('/api/orders')
def create_order():
    data = request.get_json(silent=True) or {}
    required = ['id', 'name', 'phone', 'car', 'part', 'qty']
    if any(not str(data.get(k, '')).strip() for k in required):
        return jsonify({'error': 'لطفاً نام، موبایل، خودرو، قطعه و تعداد را کامل وارد کنید.'}), 400
    phone = re.sub(r'[\s()-]', '', str(data['phone']))
    if not re.fullmatch(r'\+?[0-9۰-۹]{8,16}', phone):
        return jsonify({'error': 'شماره موبایل معتبر نیست.'}), 400
    if not SUPABASE_SERVICE_ROLE_KEY:
        return jsonify({'error': 'اتصال پایگاه داده هنوز روی سرور تنظیم نشده است. سفارش ثبت نشد.'}), 503

    row = {
        'order_code': str(data['id'])[:40], 'customer_name': str(data['name'])[:120],
        'customer_phone': phone[:24], 'customer_type': str(data.get('type', 'مشتری شخصی'))[:80],
        'car_model': str(data['car'])[:100], 'part_name': str(data['part'])[:160],
        'brand_preference': str(data.get('brand', ''))[:120], 'quantity': max(1, min(int(data.get('qty', 1)), 10000)),
        'part_code': str(data.get('code', ''))[:100] or None, 'details': str(data.get('details', ''))[:2000] or None,
        'delivery_method': str(data.get('delivery', ''))[:100], 'address': str(data.get('address', ''))[:500] or None,
        'status': 'new'
    }
    try:
        db_response = requests.post(
            f'{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}', json=row, timeout=20,
            headers={'apikey': SUPABASE_SERVICE_ROLE_KEY, 'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
                     'Content-Type': 'application/json', 'Prefer': 'return=minimal'}
        )
        if not db_response.ok:
            app.logger.error('Supabase insert failed: %s %s', db_response.status_code, db_response.text[:500])
            return jsonify({'error': 'ثبت در پایگاه داده انجام نشد؛ ساختار جدول و تنظیمات سرور بررسی شود.'}), 502
    except requests.RequestException:
        app.logger.exception('Supabase request failed')
        return jsonify({'error': 'ارتباط با پایگاه داده برقرار نشد.'}), 502

    sms_sent = False
    if KAVENEGAR_API_KEY and ADMIN_PHONE:
        message = f"درخواست جدید نکسوس یدک {row['order_code']} | {row['customer_name']} | {row['car_model']} | {row['part_name']} × {row['quantity']} | {phone}"
        try:
            sms_sent = send_sms(ADMIN_PHONE, message)
        except (requests.RequestException, ValueError, KeyError):
            app.logger.exception('SMS notification failed')
    return jsonify({'ok': True, 'order_code': row['order_code'], 'sms_sent': sms_sent, 'sms_configured': bool(KAVENEGAR_API_KEY and ADMIN_PHONE)}), 201

@app.get('/<path:path>')
def static_files(path):
    target = (BASE_DIR / path).resolve()
    if BASE_DIR.resolve() not in target.parents:
        return ('Not found', 404)
    if target.is_file():
        return send_from_directory(BASE_DIR, path)
    return ('Not found', 404)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')))
