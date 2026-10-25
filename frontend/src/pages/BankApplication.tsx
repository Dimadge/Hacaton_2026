import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { BankApplication, EvaluateResult, ScoreResult } from "../api/types";
import { Alert, Button, Card, ErrorState, Field, inputClass, Loader, StatusBadge } from "../components/ui";
import { useAuth } from "../features/auth/session";
import { REASONS, reasonText } from "../lib/format";

export function BankApplicationPage() {
  const { id } = useParams();
  const { session } = useAuth();
  const [item, setItem] = useState<BankApplication | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [action, setAction] = useState<"REQUEST_INFO" | "REJECT" | "APPROVE">("REQUEST_INFO");
  const [reasons, setReasons] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const [amount, setAmount] = useState("");
  const [term, setTerm] = useState("36");

  function load() {
    api<BankApplication>(`/bank/applications/${id}`, { token: session!.token })
      .then(setItem)
      .catch((reason) => setError(reason instanceof ApiError ? reason.message : "Карточка недоступна"));
  }

  useEffect(load, [id, session]);

  async function run<T>(path: string, body?: unknown): Promise<T> {
    setPending(true);
    setError("");
    try {
      const result = await api<T>(`/bank/applications/${id}/${path}`, {
        method: "POST",
        token: session!.token,
        body,
      });
      load();
      return result;
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Действие не выполнено");
      throw reason;
    } finally {
      setPending(false);
    }
  }

  if (error && !item) return <ErrorState message={error} onRetry={load} />;
  if (!item) return <Loader />;

  return (
    <div className="space-y-4">
      <Card title={item.company_name}>
        <StatusBadge status={item.status} />
        <p className="mt-2 text-sm">Версия {item.version}. Подтверждение сведений: {item.document_confirmed ? "да" : "нет"}. Скоринг: {item.scoring_ready ? "есть" : "ещё нет"}.</p>
        {Object.entries(item.verification_results).map(([source, result]) => <p key={source} className="text-sm">{source}: {result}</p>)}
        {item.client_clarification && <p className="mt-2 text-sm">Пояснение клиента: {item.client_clarification}</p>}
        {item.status === "CHECKING" && (
          <div className="mt-3 flex gap-2">
            <Button disabled={pending} onClick={() => run<EvaluateResult>("evaluate").then((result) => {
              const text: Record<string, string> = {
                SCORING_PENDING: "Проверки в порядке. Сначала рассчитайте скоринг, затем снова нажмите «Проверка».",
                CLIENT_OFFER: "Проверка завершена: клиенту доступны предложения.",
                FINAL: "Проверка завершена: решение окончательное.",
                BANK_REVIEW: "Проверка завершена: заявка на ручном рассмотрении.",
                ADD_DOCUMENTS: "Проверка завершена: клиенту нужно дополнить сведения.",
                CLIENT_INFO: "Проверка завершена: клиенту нужно дополнить сведения.",
              };
              setNote(text[result.next_step] ?? `Проверка завершена. Статус: ${result.status}`);
            }).catch(() => undefined)}>Проверка</Button>
            <Button kind="ghost" disabled={pending} onClick={() => run<ScoreResult>("score").then((result) => setNote(`Оценка ${result.score}, риск ${result.risk}.`)).catch(() => undefined)}>Рассчитать скоринг</Button>
          </div>
        )}
        {note && <p className="mt-2 text-sm">{note}</p>}
      </Card>

      {item.status === "UNDER_REVIEW" && (
        <Card title="Решение сотрудника">
          <Field label="Действие">
            <select className={inputClass} value={action} onChange={(event) => setAction(event.target.value as typeof action)}>
              <option value="REQUEST_INFO">Запросить сведения</option>
              <option value="REJECT">Отказать</option>
              <option value="APPROVE">Одобрить условия</option>
            </select>
          </Field>
          <div className="my-3 space-y-1 text-sm">
            {Object.entries(REASONS).map(([code, label]) => (
              <label key={code} className="flex gap-2">
                <input type="checkbox" checked={reasons.includes(code)} onChange={(event) => {
                  setReasons(event.target.checked ? [...reasons, code] : reasons.filter((item) => item !== code));
                }} />
                {label}
              </label>
            ))}
          </div>
          <Field label="Комментарий">
            <textarea className={inputClass} value={comment} onChange={(event) => setComment(event.target.value)} />
          </Field>
          {action === "APPROVE" && (
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <Field label="Сумма предложения"><input className={inputClass} value={amount} onChange={(event) => setAmount(event.target.value)} /></Field>
              <Field label="Срок, месяцев"><input className={inputClass} value={term} onChange={(event) => setTerm(event.target.value)} /></Field>
            </div>
          )}
          <Button className="mt-3" disabled={pending} onClick={() => {
            if (!window.confirm("Зафиксировать решение?")) return;
            const offers = action === "APPROVE" ? [{ amount: amount.trim(), term_months: Number(term) }] : [];
            run("decision", { version: item.version, action, reason_codes: reasons, comment: comment || null, offers })
              .then(() => setNote(reasons.map(reasonText).join(" ")));
          }}>Сохранить решение</Button>
        </Card>
      )}
      {error && <Alert>{error}</Alert>}
    </div>
  );
}
