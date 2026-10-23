"""Кабинет сотрудника банка (только JWT роль BANK_EMPLOYEE)."""
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import Connection
from ...core.security import Actor, require_bank_employee
from ...database import get_connection
from ...schemas.decision import (BankQueueItem, BankApplicationOut,
                                 BankDecisionIn, EvaluateOut)
from ...services import decisions

router = APIRouter(prefix='/bank', tags=['Банк'])


@router.get('/applications', response_model=list[BankQueueItem],
            summary='Очередь CHECKING, UNDER_REVIEW и NEED_INFO')
def queue(_actor: Actor = Depends(require_bank_employee),
          conn: Connection = Depends(get_connection)):
    return decisions.bank_queue(conn)


@router.get('/applications/{application_id}', response_model=BankApplicationOut,
            summary='Карточка заявки для банковского сотрудника')
def application(application_id: UUID,
                _actor: Actor = Depends(require_bank_employee),
                conn: Connection = Depends(get_connection)):
    return decisions.bank_application(conn, application_id)


@router.post('/applications/{application_id}/evaluate', response_model=EvaluateOut,
             summary='Применить правила к ФНС/БКИ; не подменяет скоринг DS')
def evaluate(application_id: UUID,
             actor: Actor = Depends(require_bank_employee),
             conn: Connection = Depends(get_connection)):
    return decisions.bank_evaluate(conn, actor, application_id)


@router.post('/applications/{application_id}/decision', response_model=EvaluateOut,
             summary='Решение сотрудника по UNDER_REVIEW (с проверкой версии)')
def decision(application_id: UUID, data: BankDecisionIn,
             actor: Actor = Depends(require_bank_employee),
             conn: Connection = Depends(get_connection)):
    return decisions.manual_decision(conn, actor, application_id, data)
