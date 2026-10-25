from fastapi import APIRouter, Depends
from sqlalchemy import Connection, text
from ...database import get_connection
from ...schemas.application import ProductOut

router = APIRouter(prefix='/products', tags=['Кредитные продукты'])


@router.get('', response_model=list[ProductOut])
def list_products(conn: Connection = Depends(get_connection)):
    rows = conn.execute(text("""SELECT id,code,name,min_amount,max_amount,min_term,max_term,demo_rate
                               FROM alfa.credit_products WHERE active=true ORDER BY code""")).mappings().all()
    return [dict(row) for row in rows]
