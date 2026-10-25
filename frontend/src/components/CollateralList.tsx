import type { Collateral } from "../api/types";
import { collateralStatusLabel, collateralTypeLabel, formatMoney, ownershipLabel } from "../lib/format";

export function CollateralList({ items }: { items: Collateral[] }) {
  if (!items.length) return <p className="text-sm">Залог не указан.</p>;
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.id} className="rounded-xl border border-black/5 px-4 py-3 text-sm">
          <p className="font-semibold">{collateralTypeLabel(item.collateral_type)}</p>
          <p className="mt-1">{item.description}</p>
          <p className="mt-1 text-neutral-600">{ownershipLabel(item.ownership_type)}: {item.owner_name}</p>
          <p className="mt-1">Заявленная стоимость {formatMoney(item.declared_value)}</p>
          <p className="mt-1 text-neutral-600">
            {item.has_encumbrance === null ? "Обременение не указано" : item.has_encumbrance ? "Есть обременение" : "Обременения нет"}
            {" · "}
            {collateralStatusLabel(item.status)}
          </p>
          {item.review_comment && <p className="mt-1">{item.review_comment}</p>}
        </li>
      ))}
    </ul>
  );
}
