from fastapi import APIRouter, Depends
from sqlalchemy import Connection, text
from ...core.security import Actor, require_client
from ...core.errors import ApiProblem
from ...database import get_connection
from ...schemas.application import CompanyOut

router = APIRouter(prefix='/me', tags=['Профиль компании'])


@router.get('/company', response_model=CompanyOut)
def my_company(actor: Actor = Depends(require_client), conn: Connection = Depends(get_connection)):
    row = conn.execute(text("""SELECT id,name,inn,industry,registered_at
                              FROM alfa.companies WHERE id=:id"""), {'id': actor.company_id}).mappings().first()
    if row is None:
        raise ApiProblem(404, 'NOT_FOUND', 'Компания не найдена')
    return {**row, 'registered_at': row['registered_at'].isoformat()}
