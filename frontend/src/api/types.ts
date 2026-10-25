export type Role = "CLIENT" | "BANK_EMPLOYEE";
export type Money = string | number;

export type LoginResponse = {
  access_token: string;
  token_type: string;
  role: Role;
  company_id: string | null;
};

export type Product = {
  id: string;
  code: string;
  name: string;
  min_amount: Money;
  max_amount: Money;
  min_term: number;
  max_term: number;
  demo_rate: Money;
};

export type Company = {
  id: string;
  name: string;
  inn: string;
  industry: string;
  registered_at: string;
};

export type Financials = {
  monthly_revenue: Money;
  operating_expenses: Money;
  existing_debt_payments: Money;
  business_age_months: number;
  cash_reserve: Money | null;
  document_confirmed: boolean;
};

export type Application = {
  id: string;
  company_id: string;
  product_code: string;
  purpose: string;
  requested_amount: Money;
  term_months: number;
  status: string;
  version: number;
  created_at: string;
  financials: Financials;
};

export type ApplicationSummary = {
  id: string;
  status: string;
  product_code: string;
  requested_amount: Money;
  term_months: number;
  version: number;
  created_at: string;
};

export type AppEvent = {
  id: number;
  action: string;
  from_status: string | null;
  to_status: string;
  application_version: number;
  at: string;
};

export type Checks = {
  application_id: string;
  evaluation_run_id: string | null;
  application_status: string;
  completed: boolean;
  checks: { source: "FNS" | "BKI"; result: string; checked_at: string }[];
  reason_codes: string[];
};

export type Offer = {
  id: string;
  amount: Money;
  term_months: number;
  rate: Money;
  monthly_payment: Money;
  rank: number;
  accepted: boolean;
};

export type Offers = {
  application_id: string;
  application_status: string;
  decision_type: string | null;
  reason_codes: string[];
  offers: Offer[];
};

export type Explanation = {
  decision_type: string;
  explanation: string;
  offers_available: number;
};

export type Fulfillment = {
  id: string;
  status: string;
  version: number;
  accepted_offer_id: string | null;
  simulated: boolean;
};

export type BankQueueItem = {
  id: string;
  company_name: string;
  status: string;
  product_code: string;
  requested_amount: Money;
  term_months: number;
  version: number;
  created_at: string;
};

export type BankApplication = BankQueueItem & {
  document_confirmed: boolean;
  verification_results: Record<string, string>;
  scoring_ready: boolean;
  client_clarification: string | null;
};

export type EvaluateResult = {
  status: string;
  version: number;
  decision_type: string | null;
  reason_codes: string[];
  next_step: string;
};

export type ScoreResult = {
  score: number;
  risk: string;
  decision_hint?: string;
  offers_count?: number;
  status: string;
};
