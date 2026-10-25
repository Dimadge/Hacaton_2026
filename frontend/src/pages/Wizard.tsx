import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Application, Company, Product } from "../api/types";
import { Alert, Button, Card, Field, inputClass, Loader } from "../components/ui";
import { buildDraftSchema, type DraftValues } from "../features/applications/form/schema";
import { useAuth } from "../features/auth/session";
import { formatMoney, formatRate, toMoney } from "../lib/format";

const STEPS = ["Продукт", "Сумма и срок", "Компания", "Финансы", "Итог"];

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
    ]).then(([nextProducts, nextCompany, application]) => {
      setProducts(nextProducts);
      setCompany(nextCompany);
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

  async function save(data: DraftValues, send: boolean) {
    const limit = matchesProduct(data);
    if (limit) return setError(limit);
    setPending(true);
    setError("");
    try {
      const token = session!.token;
      const body = payload(data);
      const saved = id
        ? await api<Application>(`/applications/${id}`, { method: "PATCH", token, body: { version, ...body } })
        : await api<Application>("/applications", { method: "POST", token, body: { product_code: data.product_code, ...body } });
      if (send) {
        await api(`/applications/${saved.id}/submit`, {
          token,
          idempotencyKey: crypto.randomUUID(),
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
      <p className="mb-3 text-sm text-neutral-500">Шаг {step + 1} из 5 · {STEPS[step]}</p>
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
            <p>Отрасль {company.industry}</p>
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
          <ul className="space-y-1 text-sm">
            <li>Продукт: {product?.name}</li>
            <li>Цель: {values.purpose}</li>
            <li>Сумма: {values.requested_amount} на {values.term_months} мес.</li>
            <li>Выручка: {values.monthly_revenue}</li>
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
          {step < 4 && (
            <Button type="button" onClick={async () => {
              const fields = [
                ["product_code", "purpose"],
                ["requested_amount", "term_months"],
                [],
                ["monthly_revenue", "operating_expenses", "existing_debt_payments", "business_age_months"],
              ][step] as (keyof DraftValues)[];
              if (fields.length === 0 || await form.trigger(fields)) setStep(step + 1);
            }}>Дальше</Button>
          )}
          {step === 4 && <Button disabled={pending}>Сохранить черновик</Button>}
          {step === 4 && !id && <Button type="button" kind="ghost" disabled={pending} onClick={form.handleSubmit((data) => save(data, true))}>Отправить</Button>}
        </div>
      </form>
    </Card>
  );
}
