import { z } from "zod";
import type { Product } from "../../../api/types";
import { formatMoney, toMoney } from "../../../lib/format";

const money = z.string().trim().regex(/^\d+([.,]\d{1,2})?$/, "Укажите сумму, например 1500000.00");

const months = (empty: string, min: number, max: number, range: string) =>
  z.preprocess(
    (value) => (value === "" || value === null || value === undefined ? undefined : value),
    z.coerce.number({ invalid_type_error: empty, required_error: empty }).int(empty).min(min, range).max(max, range),
  );

export function buildDraftSchema(products: Product[]) {
  return z.object({
    product_code: z.string().min(1, "Выберите продукт"),
    purpose: z.string().trim().min(1, "Укажите цель кредита").max(500, "Не длиннее 500 символов"),
    requested_amount: money,
    term_months: months("Укажите срок в месяцах", 1, 600, "Срок от 1 до 600 месяцев"),
    monthly_revenue: money,
    operating_expenses: money,
    existing_debt_payments: money,
    business_age_months: months("Укажите возраст бизнеса в месяцах", 0, 1200, "Возраст от 0 до 1200 месяцев"),
    cash_reserve: z.string().trim().refine((value) => value === "" || /^\d+([.,]\d{1,2})?$/.test(value), "Укажите сумму, например 800000.00"),
    document_confirmed: z.boolean(),
  }).superRefine((data, ctx) => {
    const product = products.find((item) => item.code === data.product_code);
    if (!product) return;
    const normalized = data.requested_amount.trim().replace(/\s/g, "").replace(",", ".");
    if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return;
    const amount = Number(toMoney(data.requested_amount));
    const term = Number(data.term_months);
    if (Number.isNaN(term)) return;
    if (amount < Number(product.min_amount) || amount > Number(product.max_amount)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["requested_amount"],
        message: `Сумма для «${product.name}»: ${formatMoney(product.min_amount)}–${formatMoney(product.max_amount)}`,
      });
    }
    if (term < product.min_term || term > product.max_term) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["term_months"],
        message: `Срок для «${product.name}»: ${product.min_term}–${product.max_term} мес.`,
      });
    }
  });
}

export type DraftValues = z.infer<ReturnType<typeof buildDraftSchema>>;
