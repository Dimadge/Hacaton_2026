import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Product } from "../api/types";
import { ErrorState, Loader } from "../components/ui";
import { useAuth } from "../features/auth/session";
import { formatMoney, formatRate } from "../lib/format";

export function ProductsPage() {
  const { session } = useAuth();
  const [items, setItems] = useState<Product[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Product[]>("/products", { token: session!.token })
      .then(setItems)
      .catch((reason) => setError(reason instanceof ApiError ? reason.message : "Не удалось загрузить продукты"));
  }, [session]);

  if (error) return <ErrorState message={error} />;
  if (!items.length && !error) return <Loader />;

  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#ef3124]">Каталог</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Кредитные продукты</h1>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {items.map((item, index) => (
          <article key={item.id} className="flex flex-col justify-between overflow-hidden rounded-2xl border border-black/5 bg-white shadow-[0_10px_30px_rgba(18,18,18,0.04)]">
            <div className={`h-1.5 ${index === 0 ? "bg-[#ef3124]" : "bg-[#121212]"}`} />
            <div className="p-6">
              <h2 className="text-2xl font-semibold tracking-tight">{item.name}</h2>
              <p className="mt-4 text-3xl font-semibold tracking-tight">{formatRate(item.demo_rate)}</p>
              <p className="mt-3 text-sm text-neutral-600">{formatMoney(item.min_amount)} — {formatMoney(item.max_amount)}</p>
              <p className="text-sm text-neutral-600">{item.min_term}–{item.max_term} месяцев</p>
              <Link className="mt-6 inline-flex h-11 items-center rounded-lg bg-[#ef3124] px-4 text-sm font-semibold text-white hover:bg-[#d61f14]" to={`/client/applications/new?product=${item.code}`}>
                Оформить
              </Link>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
