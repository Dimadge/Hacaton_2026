import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { BankQueueItem } from "../api/types";
import { Card, EmptyState, ErrorState, Loader, StatusBadge } from "../components/ui";
import { useAuth } from "../features/auth/session";
import { formatMoney } from "../lib/format";

export function BankPage() {
  const { session } = useAuth();
  const [items, setItems] = useState<BankQueueItem[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    api<BankQueueItem[]>("/bank/applications", { token: session!.token })
      .then(setItems)
      .catch((reason) => setError(reason instanceof ApiError ? reason.message : "Очередь недоступна"))
      .finally(() => setLoading(false));
  }

  useEffect(load, [session]);
  if (loading) return <Loader />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const visible = items.filter((item) => !status || item.status === status);
  return (
    <Card title="Очередь заявок">
      <select className="mb-4 rounded-lg border border-black/10 bg-white px-3 py-2.5" value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="">Все</option>
        <option value="CHECKING">Проверка</option>
        <option value="UNDER_REVIEW">На рассмотрении</option>
        <option value="NEED_INFO">Нужны сведения</option>
      </select>
      {visible.length === 0 ? <EmptyState>В очереди пусто.</EmptyState> : (
        <ul className="space-y-2">
          {visible.map((item) => (
            <li key={item.id}>
              <Link className="flex items-center justify-between gap-3 rounded-xl border border-black/5 px-4 py-3 transition hover:border-[#ef3124]/40 hover:bg-[#fff8f7]" to={`/bank/applications/${item.id}`}>
                <span>{item.company_name} · {formatMoney(item.requested_amount)} · {item.term_months} мес.</span>
                <StatusBadge status={item.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
