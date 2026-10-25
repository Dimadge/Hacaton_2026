import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { ApplicationSummary, Company } from "../api/types";
import { Card, EmptyState, ErrorState, Loader, StatusBadge } from "../components/ui";
import { newsFor } from "../features/news/catalog";
import { useAuth } from "../features/auth/session";
import { formatDate, formatMoney, industryLabel, productName } from "../lib/format";

export function DashboardPage() {
  const { session } = useAuth();
  const [company, setCompany] = useState<Company | null>(null);
  const [items, setItems] = useState<ApplicationSummary[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    setError("");
    Promise.all([
      api<Company>("/me/company", { token: session!.token }),
      api<ApplicationSummary[]>("/applications", { token: session!.token }),
    ])
      .then(([nextCompany, nextItems]) => {
        setCompany(nextCompany);
        setItems(nextItems);
      })
      .catch((reason) => setError(reason instanceof ApiError ? reason.message : "Не удалось загрузить кабинет"))
      .finally(() => setLoading(false));
  }

  useEffect(load, [session]);
  if (loading) return <Loader />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!company) return null;

  return (
    <div className="space-y-5">
      <section className="overflow-hidden rounded-2xl bg-[#121212] text-white shadow-[0_16px_40px_rgba(18,18,18,0.12)]">
        <div className="h-1.5 bg-[#ef3124]" />
        <div className="flex flex-wrap items-end justify-between gap-6 p-6 md:p-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/45">Компания</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">{company.name}</h1>
            <p className="mt-2 text-sm text-white/70">ИНН {company.inn} · {industryLabel(company.industry)}</p>
          </div>
          <Link className="inline-flex h-11 items-center rounded-lg bg-[#ef3124] px-4 text-sm font-semibold hover:bg-[#d61f14]" to="/client/applications/new">
            Новая заявка
          </Link>
        </div>
      </section>
      <div className="grid gap-5 lg:grid-cols-[1.4fr_0.8fr]">
        <Card title="Заявки">
          {items.length === 0 ? (
            <EmptyState>Заявок пока нет. <Link className="font-semibold text-[#ef3124]" to="/client/applications/new">Создать заявку</Link></EmptyState>
          ) : (
            <ul className="space-y-2">
              {items.map((item) => (
                <li key={item.id}>
                  <Link className="flex items-center justify-between gap-3 rounded-xl border border-black/5 px-4 py-3 transition hover:border-[#ef3124]/40 hover:bg-[#fff8f7]" to={`/client/applications/${item.id}`}>
                    <span>
                      <span className="block font-semibold">{productName(item.product_code)}</span>
                      <span className="text-sm text-neutral-500">{formatMoney(item.requested_amount)} · {item.term_months} мес. · {formatDate(item.created_at)}</span>
                    </span>
                    <StatusBadge status={item.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Новости отрасли">
          <ul className="space-y-3">
            {newsFor(company.industry).map((item) => (
              <li key={item.title} className="border-l-4 border-[#ef3124] pl-3">
                <p className="font-semibold">{item.title}</p>
                <p className="mt-1 text-sm text-neutral-600">{item.body}</p>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
