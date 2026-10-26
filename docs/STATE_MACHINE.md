# Машина состояний кредитной заявки

Диаграмма соответствует переходам `alfa.allowed_transitions` из `db/init/001_shema.sql`. Промежуточный `SUBMITTED` может быстро сменяться `CHECKING` внутри процесса подачи.

```mermaid
stateDiagram-v2
  [*] --> DRAFT
  DRAFT --> SUBMITTED: отправка клиентом
  SUBMITTED --> CHECKING: старт проверок
  CHECKING --> NEED_INFO: уточнить данные
  CHECKING --> UNDER_REVIEW: банк / риск
  CHECKING --> OFFERED: предложения
  CHECKING --> REJECTED: отказ
  NEED_INFO --> CHECKING: повторная подача
  UNDER_REVIEW --> NEED_INFO: запрос сведений
  UNDER_REVIEW --> OFFERED: банк одобрил
  UNDER_REVIEW --> REJECTED: банк отказал
  OFFERED --> ACCEPTED: клиент выбрал оффер
  OFFERED --> CANCELLED: клиент отказался
  ACCEPTED --> SIGNED: демонстрационный OTP
  SIGNED --> DISBURSED: симуляция выдачи
  REJECTED --> [*]
  CANCELLED --> [*]
  DISBURSED --> [*]
```

**Контроль на стороне сервера:** роль, владелец, текущий статус, версия записи, порядок операций, ограничения продукта/DS/залога. Нельзя непосредственно перевести отказанную заявку обратно в `OFFERED`; для нового сценария создаётся новая заявка.

События доступны клиенту через `GET /api/v1/applications/{id}/events`, а в БД — через `alfa.application_events`.

**Прочие исходы:** высокий риск и критическая кредитная история могут приводить к `REJECTED`; неизвестные проверки или просрочки — к ручному рассмотрению; недостаток документов — к `NEED_INFO`; успешное решение может содержать альтернативные предложения. Решение не сводится к простому «да/нет».
