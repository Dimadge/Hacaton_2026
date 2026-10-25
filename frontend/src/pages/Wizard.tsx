import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Application, Collateral, Company, Product } from "../api/types";
import { CollateralList } from "../components/CollateralList";
import { Alert, Button, Card, Field, inputClass, Loader } from "../components/ui";
import { buildDraftSchema, type DraftValues } from "../features/applications/form/schema";
import { useAuth } from "../features/auth/session";
import { formatMoney, formatPhone, formatRate, toMoney } from "../lib/format";
import { newIdempotencyKey } from "../lib/id";

const STEPS = ["Продукт", "Сумма и срок", "Компания", "Финансы", "Залог", "Итог"];

type CollateralDraft = {
  collateral_type: "LAND" | "REAL_ESTATE" | "VEHICLE";
  description: string;
  owner_name: string;
  ownership_type: "BORROWER" | "THIRD_PARTY";
  declared_value: string;
  has_encumbrance: "unknown" | "yes" | "no";
};

function emptyCollateral(): CollateralDraft {
  return {
    collateral_type: "REAL_ESTATE",
    description: "",
    owner_name: "",
    ownership_type: "BORROWER",
    declared_value: "",
    has_encumbrance: "unknown",
  };
}

export function WizardPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { session } = useAuth();
  const [step, setStep] = useState(0);
  const [products, setProducts] = useState<Product[]>([]);
  const [company, setCompany] = useState<Company | null>(null);
  const [version, setVersion] = useState(1);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [ready, setReady] = useState(false);
  const [savedCollateral, setSavedCollateral] = useState<Collateral[]>([]);
  const [collateral, setCollateral] = useState<CollateralDraft[]>([]);

  const form = useForm<DraftValues>({
    resolver: zodResolver(buildDraftSchema(products)),
    mode: "onChange",
    reValidateMode: "onChange",
    defaultValues: {
      product_code: params.get("product") ?? "",
      purpose: "",
      requested_amount: "",
      term_months: 12,
      monthly_revenue: "",
      operating_expenses: "",
      existing_debt_payments: "",
      business_age_months: 36,
      cash_reserve: "",
      document_confirmed: true,
    },
  });

  useEffect(() => {
    const token = session!.token;
    Promise.all([
      api<Product[]>("/products", { token }),
      api<Company>("/me/company", { token }),
      id ? api<Application>(`/applications/${id}`, { token }) : Promise.resolve(null),
      id ? api<Collateral[]>(`/applications/${id}/collateral`, { token }) : Promise.resolve([]),
    ]).then(([nextProducts, nextCompany, application, nextCollateral]) => {
      setProducts(nextProducts);
      setCompany(nextCompany);
      setSavedCollateral(nextCollateral);
      if (application) {
        if (application.status !== "DRAFT" && application.status !== "NEED_INFO") {
          navigate(`/client/applications/${application.id}`);
          return;
        }
        setVersion(application.version);
        form.reset({
          product_code: application.product_code,
          purpose: application.purpose,
          requested_amount: String(application.requested_amount),
          term_months: application.term_months,
          monthly_revenue: String(application.financials.monthly_revenue),
          operating_expenses: String(application.financials.operating_expenses),
          existing_debt_payments: String(application.financials.existing_debt_payments),
          business_age_months: application.financials.business_age_months,
          cash_reserve: application.financials.cash_reserve ? String(application.financials.cash_reserve) : "",
          document_confirmed: application.financials.document_confirmed,
        });
      }
      setReady(true);
    }).catch((reason) => setError(reason instanceof ApiError ? reason.message : "Не удалось открыть анкету"));
  }, [id, session]);

  const values = form.watch();
  const product = products.find((item) => item.code === values.product_code);

  function payload(data: DraftValues) {
    return {
      purpose: data.purpose.trim(),
      requested_amount: toMoney(data.requested_amount),
      term_months: Number(data.term_months),
      financials: {
        monthly_revenue: toMoney(data.monthly_revenue),
        operating_expenses: toMoney(data.operating_expenses),
        existing_debt_payments: toMoney(data.existing_debt_payments),
        business_age_months: Number(data.business_age_months),
        cash_reserve: data.cash_reserve.trim() ? toMoney(data.cash_reserve) : null,
        document_confirmed: data.document_confirmed,
      },
    };
  }

  function matchesProduct(data: DraftValues) {
    if (!product) return "Выберите продукт";
    const amount = Number(toMoney(data.requested_amount));
    const term = Number(data.term_months);
    if (amount < Number(product.min_amount) || amount > Number(product.max_amount) || term < product.min_term || term > product.max_term) {
      return `Для «${product.name}» сумма ${formatMoney(product.min_amount)}–${formatMoney(product.max_amount)}, срок ${product.min_term}–${product.max_term} мес.`;
    }
    return "";
  }

  function collateralError() {
    for (const item of collateral) {
      if (!item.description.trim()) return "Опишите предмет залога";
      if (!item.owner_name.trim()) return "Укажите собственника";
      if (!/^\d+([.,]\d{1,2})?$/.test(item.declared_value.trim())) return "Укажите стоимость залога";
    }
    return "";
  }

  function updateCollateral(index: number, patch: Partial<CollateralDraft>) {
    setCollateral((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  }

  async function save(data: DraftValues, send: boolean) {
    const limit = matchesProduct(data) || collateralError();
    if (limit) return setError(limit);
    setPending(true);
    setError("");
    try {
      const token = session!.token;
      const body = payload(data);
      const saved = id
        ? await api<Application>(`/applications/${id}`, { method: "PATCH", token, body: { version, ...body } })
        : await api<Application>("/applications", { method: "POST", token, body: { product_code: data.product_code, ...body } });
      for (const item of collateral) {
        await api(`/applications/${saved.id}/collateral`, {
          method: "POST",
          token,
          body: {
            collateral_type: item.collateral_type,
            description: item.description.trim(),
            owner_name: item.owner_name.trim(),
            ownership_type: item.ownership_type,
            declared_value: toMoney(item.declared_value),
            has_encumbrance: item.has_encumbrance === "unknown" ? null : item.has_encumbrance === "yes",
          },
        });
      }
      if (send) {
        await api(`/applications/${saved.id}/submit`, {
          token,
          idempotencyKey: newIdempotencyKey(),
          body: { version: saved.version },
        });
      }
      navigate(`/client/applications/${saved.id}`, {
        state: { notice: send ? "Заявка отправлена" : "Черновик сохранён" },
      });
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Не удалось сохранить заявку");
    } finally {
      setPending(false);
    }
  }

  if (!ready && !error) return <Loader />;

  return (
    <Card title="Анкета">
      <p className="mb-3 text-sm text-neutral-500">Шаг {step + 1} из {STEPS.length} · {STEPS[step]}</p>
      <ol className="mb-6 flex gap-2">
        {STEPS.map((label, index) => (
          <li key={label} className="flex-1">
            <span className={`block h-1.5 rounded-full ${index <= step ? "bg-[#ef3124]" : "bg-neutral-200"}`} />
            <span className="mt-1 hidden text-xs text-neutral-500 sm:block">{label}</span>
          </li>
        ))}
      </ol>
      <form className="space-y-4" onSubmit={form.handleSubmit((data) => save(data, false))}>
        {step === 0 && (
          <>
            <Field label="Продукт" error={form.formState.errors.product_code?.message}>
              <select className={inputClass} disabled={Boolean(id)} {...form.register("product_code")}>
                <option value="">Выберите</option>
                {products.map((item) => <option key={item.id} value={item.code}>{item.name}</option>)}
              </select>
            </Field>
            <Field label="Цель" error={form.formState.errors.purpose?.message}>
              <input className={inputClass} {...form.register("purpose")} />
            </Field>
          </>
        )}
        {step === 1 && (
          <>
            <Field label="Сумма, ₽" error={form.formState.errors.requested_amount?.message}>
              <input className={inputClass} {...form.register("requested_amount")} />
            </Field>
            <Field label="Срок, месяцев" error={form.formState.errors.term_months?.message}>
              <input className={inputClass} type="number" {...form.register("term_months")} />
            </Field>
            {product && <p className="text-sm text-neutral-600">{formatMoney(product.min_amount)}–{formatMoney(product.max_amount)}, {product.min_term}–{product.max_term} мес., {formatRate(product.demo_rate)}</p>}
          </>
        )}
        {step === 2 && company && (
          <div className="text-sm">
            <p>{company.name}</p>
            <p>ИНН {company.inn}</p>
            <p>Руководитель: {company.director_name || "не указан"}</p>
            <p>Телефон: {company.phone ? formatPhone(company.phone) : "не указан"}</p>
          </div>
        )}
        {step === 3 && (
          <>
            <Field label="Выручка в месяц" error={form.formState.errors.monthly_revenue?.message}>
              <input className={inputClass} {...form.register("monthly_revenue")} />
            </Field>
            <Field label="Операционные расходы" error={form.formState.errors.operating_expenses?.message}>
              <input className={inputClass} {...form.register("operating_expenses")} />
            </Field>
            <Field label="Текущие платежи по долгам" error={form.formState.errors.existing_debt_payments?.message}>
              <input className={inputClass} {...form.register("existing_debt_payments")} />
            </Field>
            <Field label="Возраст бизнеса, месяцев" error={form.formState.errors.business_age_months?.message}>
              <input className={inputClass} type="number" {...form.register("business_age_months")} />
            </Field>
            <Field label="Денежный резерв, необязательно">
              <input className={inputClass} {...form.register("cash_reserve")} />
            </Field>
            <label className="flex gap-2 text-sm">
              <input type="checkbox" {...form.register("document_confirmed")} />
              Подтверждаю достоверность указанных сведений
            </label>
          </>
        )}
        {step === 4 && (
          <div className="space-y-4">
            <p className="text-sm text-neutral-600">В залог можно передать земельный участок, недвижимость или транспорт. Это необязательно.</p>
            {savedCollateral.length > 0 && <CollateralList items={savedCollateral} />}
            {collateral.map((item, index) => (
              <div key={index} className="space-y-3 rounded-xl border border-black/5 p-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold">Объект {index + 1}</p>
                  <button
                    type="button"
                    className="grid h-8 w-8 cursor-pointer place-items-center rounded-lg text-neutral-500 hover:bg-neutral-100 hover:text-[#ef3124]"
                    aria-label="Убрать объект"
                    onClick={() => setCollateral((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <path d="M6 6l12 12M18 6L6 18" />
                    </svg>
                  </button>
                </div>
                <Field label="Объект">
                  <select className={inputClass} value={item.collateral_type} onChange={(event) => updateCollateral(index, { collateral_type: event.target.value as CollateralDraft["collateral_type"] })}>
                    <option value="LAND">Земельный участок</option>
                    <option value="REAL_ESTATE">Недвижимость</option>
                    <option value="VEHICLE">Транспорт</option>
                  </select>
                </Field>
                <Field label="Описание">
                  <textarea className={inputClass} value={item.description} onChange={(event) => updateCollateral(index, { description: event.target.value })} />
                </Field>
                <Field label="Собственник">
                  <input className={inputClass} value={item.owner_name} onChange={(event) => updateCollateral(index, { owner_name: event.target.value })} />
                </Field>
                <Field label="Кому принадлежит">
                  <select className={inputClass} value={item.ownership_type} onChange={(event) => updateCollateral(index, { ownership_type: event.target.value as CollateralDraft["ownership_type"] })}>
                    <option value="BORROWER">Заёмщику</option>
                    <option value="THIRD_PARTY">Третьему лицу</option>
                  </select>
                </Field>
                <Field label="Заявленная стоимость, ₽">
                  <input className={inputClass} value={item.declared_value} onChange={(event) => updateCollateral(index, { declared_value: event.target.value })} />
                </Field>
                <Field label="Обременение">
                  <select className={inputClass} value={item.has_encumbrance} onChange={(event) => updateCollateral(index, { has_encumbrance: event.target.value as CollateralDraft["has_encumbrance"] })}>
                    <option value="unknown">Не указано</option>
                    <option value="no">Нет</option>
                    <option value="yes">Есть</option>
                  </select>
                </Field>
              </div>
            ))}
            <Button type="button" kind="ghost" onClick={() => setCollateral((current) => [...current, emptyCollateral()])}>Добавить объект</Button>
          </div>
        )}
        {step === 5 && (
          <ul className="space-y-1 text-sm">
            <li>Продукт: {product?.name}</li>
            <li>Цель: {values.purpose}</li>
            <li>Сумма: {values.requested_amount} на {values.term_months} мес.</li>
            <li>Выручка: {values.monthly_revenue}</li>
            <li>Залог: {savedCollateral.length + collateral.length ? `${savedCollateral.length + collateral.length} объект(ов)` : "не указан"}</li>
          </ul>
        )}
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          {step > 0 && (
            <Button type="button" kind="ghost" onClick={() => {
              setError("");
              form.clearErrors();
              setStep((current) => current - 1);
            }}>Назад</Button>
          )}
          {step < 5 && (
            <Button type="button" onClick={async () => {
              if (step === 4) {
                const message = collateralError();
                if (message) setError(message);
                else {
                  setError("");
                  setStep(5);
                }
                return;
              }
              const fields = [
                ["product_code", "purpose"],
                ["requested_amount", "term_months"],
                [],
                ["monthly_revenue", "operating_expenses", "existing_debt_payments", "business_age_months"],
              ][step] as (keyof DraftValues)[];
              if (fields.length === 0 || await form.trigger(fields)) setStep(step + 1);
            }}>Дальше</Button>
          )}
          {step === 5 && <Button disabled={pending}>Сохранить черновик</Button>}
          {step === 5 && !id && <Button type="button" kind="ghost" disabled={pending} onClick={form.handleSubmit((data) => save(data, true))}>Отправить</Button>}
        </div>
      </form>
    </Card>
  );
}
