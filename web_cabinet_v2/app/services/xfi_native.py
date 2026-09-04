from app.core.database import connect_native


def health() -> dict:
    with connect_native() as db:
        db.execute('SELECT 1').fetchone()
    return {'ok': True, 'source': 'XFI_CONNECT'}


def account(telegram_id: int) -> dict:
    with connect_native() as db:
        user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
        if not user:
            return {'user': None, 'tariffs': [], 'keys': []}
        tariffs = db.execute('SELECT id,name,duration_days,price_rub,price_minor,traffic_limit_gb,max_ips,is_active FROM tariffs WHERE is_active=1 ORDER BY display_order,id').fetchall()
        keys = db.execute('''SELECT vk.id,vk.custom_name,vk.client_uuid,vk.expires_at,vk.created_at,vk.traffic_limit,vk.traffic_used,vk.panel_email,vk.sub_id,t.name tariff_name,s.name server_name
                             FROM vpn_keys vk LEFT JOIN tariffs t ON t.id=vk.tariff_id LEFT JOIN servers s ON s.id=vk.server_id
                             WHERE vk.user_id=? ORDER BY vk.expires_at DESC''', (user['id'],)).fetchall()
        return {'user': dict(user), 'tariffs': [dict(x) for x in tariffs], 'keys': [dict(x) for x in keys]}
