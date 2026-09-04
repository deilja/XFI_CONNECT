from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.native import router as native_router

app = FastAPI(title='XFI CONNECT Web Cabinet v2', version='2.0.0')
app.include_router(native_router)

@app.get('/health')
def health():
    return {'ok': True, 'service': 'xfi-connect-web-cabinet', 'version': '2.0.0'}
