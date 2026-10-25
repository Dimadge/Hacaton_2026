from decimal import Decimal, ROUND_DOWN
from uuid import UUID

from sqlalchemy import Connection, text

from ..core.errors import ApiProblem


# Учебное правило MVP, не норматив банка.
COLLATERAL_LTV = Decimal("0.70")


def collateral_limit_for_offer(
    conn: Connection,
    app_id: UUID,
) -> Decimal | None:

    rows = conn.execute(
        text("""
            SELECT status, assessed_value, has_encumbrance
            FROM alfa.application_collateral
            WHERE application_id = :app
            FOR SHARE
        """),
        {"app": app_id},
    ).mappings().all()

    # Залог вообще не заявляли.
    if not rows:
        return None

    # Залог ещё не прошёл оценку.
    if any(
        r["status"] in ("DECLARED", "UNDER_REVIEW")
        for r in rows
    ):
        raise ApiProblem(
            409,
            "COLLATERAL_PENDING",
            "Не все заявленные залоги оценены банком",
        )

    accepted = [
        r for r in rows
        if r["status"] == "ACCEPTED"
    ]

    if not accepted:
        raise ApiProblem(
            409,
            "COLLATERAL_NOT_ACCEPTED",
            "Нет принятого банком залога",
        )

    for item in accepted:
        value = item["assessed_value"]

        if (
            item["has_encumbrance"] is not False
            or value is None
            or Decimal(str(value)) <= 0
        ):
            raise ApiProblem(
                409,
                "COLLATERAL_INVALID",
                "Принятый залог требует повторной проверки",
            )

    total = sum(
        (
            Decimal(str(item["assessed_value"]))
            for item in accepted
        ),
        Decimal("0.00"),
    )

    return (total * COLLATERAL_LTV).quantize(
        Decimal("0.01"),
        rounding=ROUND_DOWN,
    )
