from fastapi import APIRouter, HTTPException
from app.services import xfi_native

router = APIRouter(prefix='/api/native', tags=['native'])

@router.get('/health')
def native_health():
    try:
        return xfi_native.health()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'XFI_CONNECT database unavailable: {exc}')

@router.get('/account/{telegram_id}')
def native_account(telegram_id: int):
    data = xfi_native.account(telegram_id)
    if data['user'] is None:
        raise HTTPException(status_code=404, detail='Telegram account is not linked')
    return data
