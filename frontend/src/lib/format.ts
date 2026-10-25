import type { Money } from "../api/types";

export function toMoney(raw: string): string {
  const cleaned = raw.trim().replace(/\s/g, "").replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) {
    throw new Error("Сумма должна быть в виде 1500000.00");
  }
  const [whole, frac = ""] = cleaned.split(".");
  return `${whole}.${frac.padEnd(2, "0")}`;
}

export function formatMoney(value: Money): string {
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  return new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 2 }).format(number);
}

export function productName(code: string): string {
  if (code === "WORKING_CAPITAL") return "Оборотный";
  if (code === "INVESTMENT") return "Инвестиционный";
  return code;
}

export function industryLabel(code: string): string {
  const labels: Record<string, string> = {
    MANUFACTURING: "Производство",
    TRADE: "Торговля",
    FOOD: "Общепит",
    SERVICES: "Услуги",
  };
  return labels[code] ?? code;
}

export function formatRate(value: Money): string {
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(Number(value) * 100)}% годовых`;
}

export function formatPhone(value: string): string {
  const match = value.match(/^\+7(\d{3})(\d{3})(\d{2})(\d{2})$/);
  return match ? `+7 ${match[1]} ${match[2]}-${match[3]}-${match[4]}` : value;
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export const STATUS_LABEL: Record<string, string> = {
  DRAFT: "Черновик",
  SUBMITTED: "Отправлена",
  CHECKING: "Проверка",
  NEED_INFO: "Нужны сведения",
  UNDER_REVIEW: "На рассмотрении",
  OFFERED: "Есть предложение",
  ACCEPTED: "Условия приняты",
  SIGNED: "Договор подписан",
  DISBURSED: "Средства выданы",
  REJECTED: "Отказ",
  CANCELLED: "Отказ от предложения",
};

export const REASONS: Record<string, string> = {
  PAYMENT_OVER_LIMIT: "Запрошенные условия создают слишком высокую нагрузку.",
  CASHFLOW_NONPOSITIVE: "Недостаточно операционного денежного потока.",
  CREDIT_HISTORY_DELAY: "Нужна дополнительная проверка кредитной истории.",
  CREDIT_HISTORY_CRITICAL: "Критический фактор кредитной истории.",
  REGISTRY_INACTIVE: "Организация неактивна по данным ФНС.",
  REGISTRY_MISMATCH: "Требуется ручная проверка сведений организации.",
  MISSING_FINANCIAL_DATA: "Заполните обязательные финансовые сведения.",
  PRODUCT_LIMIT: "Сумма или срок не соответствуют продукту.",
  ALTERNATIVE_AVAILABLE: "Рассчитаны альтернативные условия.",
  DOCS_MISSING: "Добавьте подтверждающий документ или сведения.",
  RISK_HIGH: "Высокий риск по результатам оценки.",
  RISK_MEDIUM: "Требуется ручная оценка риска.",
  UNKNOWN_VERIFICATION: "Результат проверки: нужна ручная обработка.",
  COLLATERAL_LIMIT: "Недостаточно принятого залогового обеспечения.",
};

export function reasonText(code: string): string {
  return REASONS[code] ?? code;
}

export function collateralTypeLabel(code: string): string {
  if (code === "LAND") return "Земельный участок";
  if (code === "REAL_ESTATE") return "Недвижимость";
  if (code === "VEHICLE") return "Транспорт";
  return code;
}

export function ownershipLabel(code: string): string {
  if (code === "BORROWER") return "Собственник — заёмщик";
  if (code === "THIRD_PARTY") return "Собственник — третье лицо";
  return code;
}

export function collateralStatusLabel(code: string): string {
  if (code === "DECLARED") return "Заявлен";
  if (code === "UNDER_REVIEW") return "На проверке";
  if (code === "ACCEPTED") return "Принят";
  if (code === "REJECTED") return "Не принят";
  return code;
}
