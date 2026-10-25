import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { BankApplication, Collateral, EvaluateResult, ScoreResult } from "../api/types";
import { CollateralList } from "../components/CollateralList";
import { Alert, Button, Card, ErrorState, Field, inputClass, Loader, StatusBadge } from "../components/ui";
import { useAuth } from "../features/auth/session";
import { REASONS, formatMoney, productName, reasonText, toMoney } from "../lib/format";

const HIDDEN_BANK_REASONS = new Set([
  "RISK_MEDIUM",
  "CREDIT_HISTORY_CRITICAL",
  "REGISTRY_INACTIVE",
  "UNKNOWN_VERIFICATION",
]);

export function BankApplicationPage() {
  const { id } = useParams();
  const { session } = useAuth();
  const [item, setItem] = useState<BankApplication | null>(null);
  const [collateral, setCollateral] = useState<Collateral[]>([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [action, setAction] = useState<"REQUEST_INFO" | "REJECT" | "APPROVE">("REQUEST_INFO");
  const [reasons, setReasons] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const [amount, setAmount] = useState("");
  const [term, setTerm] = useState("36");

  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [reviewValue, setReviewValue] = useState("");
  const [reviewComment, setReviewComment] = useState("");
  const [reviewEncumbrance, setReviewEncumbrance] = useState(false);

  async function saveCollateralReview(status: "ACCEPTED" | "REJECTED") {
    if (!reviewingId) return;
    if (!reviewComment.trim()) {
      setError("Введите комментарий к оценке залога");
      return;
    }
    let assessedValue: string | null = null;
    if (status === "ACCEPTED") {
      try {
        assessedValue = toMoney(reviewValue);
        if (Number(assessedValue) <= 0) throw new Error("Стоимость должна быть положительной");
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Неверная стоимость");
        return;
      }
      if (reviewEncumbrance) {
        setError("Залог с обременением нельзя принять по упрощённой процедуре");
        return;
      }
    }
    setPending(true);
    setError("");
    try {
      await api<Collateral>(`/bank/applications/${id}/collateral/${reviewingId}`, {
        method: "PATCH",
        token: session!.token,
        body: {
          status,
          assessed_value: assessedValue,
          has_encumbrance: reviewEncumbrance,
          review_comment: reviewComment.trim(),
        },
      });
      setReviewingId(null);
      setReviewValue("");
      setReviewComment("");
      setNote(status === "ACCEPTED" ? "Залог принят банком" : "Залог отклонён");
      load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Ошибка оценки залога");
    } finally {
      setPending(false);
    }
  }

  function load() {
    const token = session!.token;
    Promise.all([
      api<BankApplication>(`/bank/applications/${id}`, { token }),
      api<Collateral[]>(`/bank/applications/${id}/collateral`, { token }),
    ])
      .then(([nextItem, nextCollateral]) => {
        setItem(nextItem);
        setCollateral(nextCollateral);
      })
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

  const back = (
    <Link className="inline-flex items-center gap-1 text-sm font-semibold hover:text-[#ef3124]" to="/bank">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>
      К списку заявок
    </Link>
  );

  if (error && !item) return <div className="space-y-4">{back}<ErrorState message={error} onRetry={load} /></div>;
  if (!item) return <div className="space-y-4">{back}<Loader /></div>;

  return (
    <div className="space-y-4">
      {back}
      <Card title={item.company_name}>
        <StatusBadge status={item.status} />
        <p className="mt-3 text-lg font-semibold tracking-tight">{productName(item.product_code)}</p>
        <p className="mt-1 text-sm">Сумма {formatMoney(item.requested_amount)} · срок {item.term_months} мес.</p>
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

      <Card title="Кредитные ограничения">
        <div className="grid gap-4 md:grid-cols-2">

          <div className="rounded-xl bg-[#f7f7f8] p-4">
            <p className="text-sm text-neutral-500">
              Максимальный ежемесячный платёж (DS)
            </p>

            <p className="mt-2 text-xl font-semibold">
              {item.max_new_payment !== null
                ? formatMoney(item.max_new_payment)
                : "Не рассчитан"}
            </p>

            <p className="mt-2 text-xs text-neutral-500">
              Рассчитывается по финансовым данным
              предприятия и действующим обязательствам.
            </p>
          </div>

          <div className="rounded-xl bg-[#f7f7f8] p-4">
            <p className="text-sm text-neutral-500">
              Максимальная сумма по залогу
            </p>

            <p className="mt-2 text-xl font-semibold">
              {item.collateral_limit !== null
                ? formatMoney(item.collateral_limit)
                : ({
                    NOT_DECLARED:
                      "Залог не заявлен",
                    COLLATERAL_PENDING:
                      "Ожидается оценка банка",
                    COLLATERAL_NOT_ACCEPTED:
                      "Нет принятого залога",
                    COLLATERAL_INVALID:
                      "Требуется повторная проверка"
                  }[item.collateral_status] ??
                  "Не определена")}
            </p>

            <p className="mt-2 text-xs text-neutral-500">
              Учебный коэффициент обеспечения — 70%.
              Если залог не заявлен, лимит не применяется.
            </p>
          </div>
        </div>

        <p className="mt-4 text-sm text-neutral-600">
          Для одобрения необходимо соблюдать лимит
          ежемесячного платежа DS и лимит по залогу,
          если последний применяется.
        </p>
      </Card>

      <Card title="Залог">
        <CollateralList items={collateral} />
        {["CHECKING", "UNDER_REVIEW"].includes(item.status) && collateral
          .filter((object) => ["DECLARED", "UNDER_REVIEW"].includes(object.status))
          .map((object) => (
            <div key={object.id} className="mt-4 rounded-xl border border-black/10 p-4">
              <p className="font-semibold">{object.description}</p>
              <p className="mt-2 text-sm">Клиент заявил: {formatMoney(object.declared_value)}</p>
              {reviewingId !== object.id ? (
                <Button className="mt-3" disabled={pending} onClick={() => {
                  setReviewingId(object.id);
                  setReviewValue(String(object.assessed_value ?? object.declared_value));
                  setReviewEncumbrance(object.has_encumbrance ?? false);
                  setReviewComment("");
                }}>Оценить залог</Button>
              ) : (
                <div className="mt-4 space-y-3">
                  <Field label="Оценочная стоимость, ₽">
                    <input className={inputClass} value={reviewValue}
                      onChange={(event) => setReviewValue(event.target.value)} />
                  </Field>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={reviewEncumbrance}
                      onChange={(event) => setReviewEncumbrance(event.target.checked)} />
                    Есть обременение
                  </label>
                  <Field label="Комментарий сотрудника">
                    <textarea className={inputClass} value={reviewComment}
                      onChange={(event) => setReviewComment(event.target.value)} />
                  </Field>
                  <div className="flex flex-wrap gap-2">
                    <Button disabled={pending} onClick={() => saveCollateralReview("ACCEPTED")}>
                      Принять залог
                    </Button>
                    <Button kind="danger" disabled={pending}
                      onClick={() => saveCollateralReview("REJECTED")}>
                      Отклонить залог
                    </Button>
                    <Button kind="ghost" disabled={pending} onClick={() => setReviewingId(null)}>
                      Отмена
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ))}
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
            {Object.entries(REASONS).filter(([code]) => !HIDDEN_BANK_REASONS.has(code)).map(([code, label]) => (
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
          <div className="mt-3 flex flex-wrap gap-2">
            <Button disabled={pending} onClick={() => {
              if (!window.confirm("Зафиксировать решение?")) return;
              const offers = action === "APPROVE" ? [{ amount: amount.trim(), term_months: Number(term) }] : [];
              run("decision", { version: item.version, action, reason_codes: reasons, comment: comment || null, offers })
                .then(() => setNote(reasons.map(reasonText).join(" ")))
                .catch(() => undefined);
            }}>Сохранить решение</Button>
            <Button kind="danger" disabled={pending} onClick={() => {
              if (!reasons.length) {
                setError("Укажите причину отказа");
                return;
              }
              if (!window.confirm("Отказать по этой заявке?")) return;
              run("decision", { version: item.version, action: "REJECT", reason_codes: reasons, comment: comment || null, offers: [] })
                .then(() => setNote("Заявка отклонена"))
                .catch(() => undefined);
            }}>Отказать</Button>
          </div>
        </Card>
      )}
      {error && <Alert>{error}</Alert>}
    </div>
  );
}
