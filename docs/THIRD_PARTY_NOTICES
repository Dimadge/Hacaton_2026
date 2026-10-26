# THIRD_PARTY_NOTICES — Альфа.Навигатор

Этот документ перечисляет ключевые сторонние компоненты, их назначение, а также **все смоделированные внешние интеграции**. Точные версии и применимые тексты лицензий нужно сверять с файлами `frontend/package-lock.json`, Python-зависимостями и содержимым Docker-образов для выбранного commit SHA. Список не заменяет юридическую проверку лицензий полного дерева транзитивных зависимостей.

## Компоненты

| Компонент | Использование | Источник / замечание |
| --- | --- | --- |
| Python 3.12 | Backend | https://www.python.org/ |
| FastAPI / Starlette / Pydantic | REST API, маршрутизация, валидация | https://fastapi.tiangolo.com/ · https://www.starlette.io/ · https://docs.pydantic.dev/ |
| Uvicorn | ASGI-сервер | https://www.uvicorn.org/ |
| SQLAlchemy, psycopg | Работа с PostgreSQL | https://www.sqlalchemy.org/ · https://www.psycopg.org/ |
| PostgreSQL 16 | Основная БД | https://www.postgresql.org/ |
| React 19, React DOM | Веб-интерфейс | https://react.dev/ |
| TypeScript, Vite | Типизация и сборка клиента | https://www.typescriptlang.org/ · https://vite.dev/ |
| React Router, React Hook Form, Zod | Навигация, формы, валидация | https://reactrouter.com/ · https://react-hook-form.com/ · https://zod.dev/ |
| Tailwind CSS | Стили | https://tailwindcss.com/ |
| Nginx | Сервинг фронтенда и обратное проксирование | https://nginx.org/ |
| Docker, Docker Compose | Запуск компонентов | https://docs.docker.com/ |
| Argon2 / argon2-cffi, PyJWT | Хеширование паролей, JWT | https://argon2-cffi.readthedocs.io/ · https://pyjwt.readthedocs.io/ |
| pytest, httpx | Автотесты и тестирование HTTP | https://docs.pytest.org/ · https://www.python-httpx.org/ |
| Ollama (опционально) | Локальные языковые объяснения | https://ollama.com/ |
| Qwen2.5 (опционально) | Модель открытых весов при её локальном подключении | https://huggingface.co/Qwen ; лицензия выбранной версии модели проверяется отдельно |

## Данные и интеграции

| Наименование | Статус в MVP |
| --- | --- |
| ФНС, ЕГРЮЛ / «Прозрачный бизнес» | **Mock**, результаты `active/inactive/mismatch/unknown` из синтетических профилей; запросов к ФНС нет |
| БКИ | **Mock**, `good/minor_delay/critical/unknown`; реальных запросов к БКИ нет |
| Банковские счета и транзакции | Синтетические `alfa.bank_accounts` / `alfa.bank_operations` |
| Кредитные продукты, ставки и лимиты | Демо-данные в БД, не оферта банка |
| Залог, оценка, обременения | Демонстрационные ввод и решение банковского сотрудника, без обращения к реестрам |
| OTP-подпись | Код генерируется локально, в деморежиме показывается в интерфейсе; SMS/email не используются |
| Выдача кредита | **Симуляция**, никаких переводов средств |
| Новостная лента | Небольшой статический каталог с фильтрацией по отрасли, без внешней новостной подписки |

Только синтетические компании и учётные записи предназначены для демонстрации. Персональные и финансовые данные реальных клиентов загружать нельзя.
