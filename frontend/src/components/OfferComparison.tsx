import type { Application, Offer } from "../api/types";
import { formatMoney, formatRate } from "../lib/format";
import { Button } from "./ui";

export function OfferComparison({
  application,
  offers,
  pending,
  onAccept,
}: {
  application: Application;
  offers: Offer[];
  pending: boolean;
  onAccept: (offerId: string) => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-neutral-600">
        Запрошено {formatMoney(application.requested_amount)} на {application.term_months} мес.
      </p>
      {offers.map((offer) => (
        <article key={offer.id} className={`overflow-hidden rounded-xl border ${offer.accepted ? "border-[#121212]" : "border-black/10"}`}>
          <div className={`h-1 ${offer.accepted ? "bg-[#ef3124]" : "bg-transparent"}`} />
          <div className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Вариант {offer.rank}{offer.accepted ? " · выбран" : ""}</p>
              <p className="mt-1 text-xl font-semibold tracking-tight">{formatMoney(offer.amount)}</p>
              <p className="text-sm text-neutral-600">{offer.term_months} мес. · {formatRate(offer.rate)}</p>
              <p className="mt-1 text-sm">Платёж {formatMoney(offer.monthly_payment)} в месяц</p>
            </div>
            {application.status === "OFFERED" && (
              <Button disabled={pending} onClick={() => onAccept(offer.id)}>Выбрать</Button>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
