"""FastAPI: Альфа.Навигатор — банк, решения и mock-проверки (BE-07)."""
import os
import uuid
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .database import get_engine
from .core.errors import ApiProblem, install_error_handlers
from .api.v1 import auth, products, me, applications, bank

app = FastAPI(title='Альфа.Навигатор API', version='0.1.0',
              description='Учебный кредитный кабинет на синтетических данных. Не банковская методика.')
install_error_handlers(app)

origins = [v.strip() for v in os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',') if v.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                   allow_methods=['GET', 'POST', 'PATCH', 'OPTIONS'],
                   allow_headers=['Authorization', 'Content-Type', 'X-Request-ID', 'Idempotency-Key'])


@app.middleware('http')
async def request_id_header(request, call_next):
    request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers['X-Request-ID'] = request.state.request_id
    return response


@app.get('/health', tags=['Система'])
def health():
    return {'status': 'ok', 'service': 'alfa-navigator-api'}


@app.get('/ready', tags=['Система'])
def readiness():
    try:
        with get_engine().connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception:
        raise ApiProblem(503, 'DATABASE_UNAVAILABLE', 'База данных временно недоступна') from None
    return {'status': 'ready', 'database': 'ok'}


for router in (auth.router, products.router, me.router, applications.router, bank.router):
    app.include_router(router, prefix='/api/v1')
