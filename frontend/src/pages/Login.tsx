import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { Alert, BrandMark, Button, Field, inputClass } from "../components/ui";
import { useAuth } from "../features/auth/session";
import { emailError } from "../lib/email";

const INDUSTRIES = [
  ["MANUFACTURING", "Производство"],
  ["TRADE", "Торговля"],
  ["FOOD", "Общепит"],
  ["SERVICES", "Услуги"],
];

export function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [inn, setInn] = useState("");
  const [industry, setIndustry] = useState("TRADE");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  const emailMessage = email.trim() ? emailError(email) : "";
  const passwordMessage = password && password.length < 12 ? "Пароль должен содержать минимум 12 символов" : "";
  const innMessage = inn && !/^\d{10}$|^\d{12}$/.test(inn.trim()) ? "ИНН должен содержать 10 или 12 цифр" : "";

  function switchMode(next: "login" | "register") {
    setMode(next);
    setError("");
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const mail = emailError(email);
    if (mail) return setError(mail);
    if (mode === "register") {
      if (passwordMessage) return setError(passwordMessage);
      if (!companyName.trim()) return setError("Укажите название компании");
      if (innMessage || !/^\d{10}$|^\d{12}$/.test(inn.trim())) return setError(innMessage || "ИНН должен содержать 10 или 12 цифр");
    }
    setPending(true);
    setError("");
    try {
      const role = mode === "login"
        ? await login(email, password)
        : await register({
          email: email.trim(),
          password,
          company_name: companyName.trim(),
          inn: inn.trim(),
          industry,
        });
      navigate(role === "CLIENT" ? "/client" : "/bank");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Не удалось выполнить запрос");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-[0.78fr_1.22fr]">
      <section className="relative hidden overflow-hidden bg-[#121212] p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <BrandMark light />
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#ef3124]">Кредиты для бизнеса</p>
          <h1 className="mt-4 max-w-md text-5xl font-semibold leading-[1.05] tracking-tight">
            Понятные условия и решение по заявке
          </h1>
        </div>
        <p className="max-w-sm text-sm text-white/60">Оборотный и инвестиционный кредит. Сравнение предложений и статус заявки в одном кабинете.</p>
        <span className="absolute inset-y-0 right-0 w-3 bg-[#ef3124]" />
      </section>
      <section className="flex items-center justify-center bg-[#f2f3f5] px-6 py-12">
        <div className="w-full max-w-xl rounded-2xl border border-black/5 bg-white p-8 shadow-[0_16px_40px_rgba(18,18,18,0.06)] md:p-10">
          <div className="mb-6 lg:hidden"><BrandMark /></div>
          <h2 className="text-3xl font-semibold tracking-tight">{mode === "login" ? "Вход в кабинет" : "Новый кабинет"}</h2>
          <form className="mt-6 space-y-4" onSubmit={onSubmit}>
            <Field label="Почта" error={emailMessage}>
              <input className={inputClass} value={email} autoComplete="email" onChange={(event) => setEmail(event.target.value)} />
            </Field>
            <Field label="Пароль" error={mode === "register" ? passwordMessage : ""}>
              <input className={inputClass} type="password" value={password} autoComplete={mode === "login" ? "current-password" : "new-password"} onChange={(event) => setPassword(event.target.value)} />
            </Field>
            {mode === "register" && (
              <>
                <Field label="Название компании" error={companyName && !companyName.trim() ? "Укажите название компании" : ""}>
                  <input className={inputClass} value={companyName} onChange={(event) => setCompanyName(event.target.value)} />
                </Field>
                <Field label="ИНН" error={innMessage}>
                  <input className={inputClass} inputMode="numeric" value={inn} onChange={(event) => setInn(event.target.value)} />
                </Field>
                <Field label="Отрасль">
                  <select className={inputClass} value={industry} onChange={(event) => setIndustry(event.target.value)}>
                    {INDUSTRIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </Field>
              </>
            )}
            {error && <Alert>{error}</Alert>}
            <Button className="w-full" disabled={pending}>
              {pending ? "Подождите…" : mode === "login" ? "Войти" : "Зарегистрироваться"}
            </Button>
          </form>
          <button className="mt-5 cursor-pointer text-sm font-semibold text-[#ef3124]" type="button" onClick={() => switchMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "Создать кабинет" : "Уже есть кабинет"}
          </button>
        </div>
      </section>
    </main>
  );
}
