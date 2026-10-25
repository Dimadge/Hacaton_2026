import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { Alert, BrandMark, Button, Field, inputClass } from "../components/ui";
import { useAuth } from "../features/auth/session";
import { emailError } from "../lib/email";

function phoneError(value: string): string {
  const digits = value.replace(/\D/g, "");
  const normalized = digits.length === 11 && (digits[0] === "7" || digits[0] === "8")
    ? `7${digits.slice(1)}`
    : digits.length === 10
      ? `7${digits}`
      : "";
  return /^7\d{10}$/.test(normalized) ? "" : "Укажите телефон: 10 цифр или номер с +7";
}

function passwordError(value: string): string {
  if (value.length < 12) return "Пароль должен содержать минимум 12 символов";
  if (!/[A-ZА-ЯЁ]/.test(value) || !/[a-zа-яё]/.test(value)) return "В пароле нужны заглавная и строчная буквы";
  if (!/\d/.test(value)) return "В пароле нужна цифра";
  if (!/[^A-Za-zА-Яа-яЁё0-9]/.test(value)) return "В пароле нужен спецсимвол, например ! или @";
  return "";
}

function directorError(value: string): string {
  const name = value.trim().replace(/\s+/g, " ");
  const parts = name.split(" ");
  const word = /^[A-Za-zА-Яа-яЁё]{2,}(?:-[A-Za-zА-Яа-яЁё]{2,})*$/;
  if (parts.length !== 3 || parts.some((part) => !word.test(part)) || name.length > 200) {
    return "Укажите фамилию, имя и отчество: ровно три слова";
  }
  return "";
}

export function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [repeatPassword, setRepeatPassword] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [inn, setInn] = useState("");
  const [phone, setPhone] = useState("");
  const [directorName, setDirectorName] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showRepeatPassword, setShowRepeatPassword] = useState(false);

  const emailMessage = email.trim() ? emailError(email) : "";
  const passwordMessage = mode === "register" && password ? passwordError(password) : "";
  const repeatMessage = mode === "register" && repeatPassword && repeatPassword !== password ? "Пароли не совпадают" : "";
  const innMessage = inn && !/^\d{10}$|^\d{12}$/.test(inn.trim()) ? "ИНН должен содержать 10 или 12 цифр" : "";
  const phoneMessage = phone ? phoneError(phone) : "";
  const directorMessage = directorName ? directorError(directorName) : "";

  function switchMode(next: "login" | "register") {
    setMode(next);
    setError("");
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const mail = emailError(email);
    if (mail) return setError(mail);
    if (mode === "register") {
      const passwordText = passwordError(password);
      if (passwordText) return setError(passwordText);
      if (repeatPassword !== password) return setError("Пароли не совпадают");
      if (!companyName.trim()) return setError("Укажите название компании");
      if (innMessage || !/^\d{10}$|^\d{12}$/.test(inn.trim())) return setError(innMessage || "ИНН должен содержать 10 или 12 цифр");
      const phoneText = phoneError(phone);
      if (phoneText) return setError(phoneText);
      const directorText = directorError(directorName);
      if (directorText) return setError(directorText);
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
          phone: phone.trim(),
          director_name: directorName.trim(),
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
        <p className="max-w-sm text-sm text-white/60">Оборотный и инвестиционный кредит. Оформите заявку и следите за решением банка в личном кабинете.</p>
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
              <span className="relative block">
                <input className={`${inputClass} pr-12`} type={showPassword ? "text" : "password"} value={password} autoComplete={mode === "login" ? "current-password" : "new-password"} onChange={(event) => setPassword(event.target.value)} />
                <button
                  className="absolute top-1/2 right-3 -translate-y-1/2 text-neutral-500"
                  type="button"
                  aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
                  onClick={() => setShowPassword((current) => !current)}
                >
                  {showPassword ? (
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                      <path d="M3 3l18 18" />
                      <path d="M10.6 10.6a2 2 0 002.8 2.8" />
                      <path d="M9.9 5.2A10.8 10.8 0 0112 5c5 0 9.3 3.1 11 7-.6 1.4-1.5 2.7-2.6 3.8M6.1 6.1C4.2 7.4 2.8 9.1 2 12c1.7 3.9 6 7 10 7 1.5 0 3-.3 4.3-.9" />
                    </svg>
                  ) : (
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </span>
              {mode === "register" && <span className="mt-1 block text-xs text-neutral-500">Не меньше 12 символов, заглавная и строчная буква, цифра и спецсимвол.</span>}
            </Field>
            {mode === "register" && (
              <>
                <Field label="Повторите пароль" error={repeatMessage}>
                  <span className="relative block">
                    <input className={`${inputClass} pr-12`} type={showRepeatPassword ? "text" : "password"} value={repeatPassword} autoComplete="new-password" onChange={(event) => setRepeatPassword(event.target.value)} />
                    <button
                      className="absolute top-1/2 right-3 -translate-y-1/2 text-neutral-500"
                      type="button"
                      aria-label={showRepeatPassword ? "Скрыть пароль" : "Показать пароль"}
                      onClick={() => setShowRepeatPassword((current) => !current)}
                    >
                      {showRepeatPassword ? (
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                          <path d="M3 3l18 18" />
                          <path d="M10.6 10.6a2 2 0 002.8 2.8" />
                          <path d="M9.9 5.2A10.8 10.8 0 0112 5c5 0 9.3 3.1 11 7-.6 1.4-1.5 2.7-2.6 3.8M6.1 6.1C4.2 7.4 2.8 9.1 2 12c1.7 3.9 6 7 10 7 1.5 0 3-.3 4.3-.9" />
                        </svg>
                      ) : (
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                          <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
                          <circle cx="12" cy="12" r="3" />
                        </svg>
                      )}
                    </button>
                  </span>
                </Field>
                <Field label="Название компании" error={companyName && !companyName.trim() ? "Укажите название компании" : ""}>
                  <input className={inputClass} value={companyName} onChange={(event) => setCompanyName(event.target.value)} />
                </Field>
                <Field label="ИНН" error={innMessage}>
                  <input className={inputClass} inputMode="numeric" value={inn} onChange={(event) => setInn(event.target.value)} />
                </Field>
                <Field label="Телефон" error={phoneMessage}>
                  <input className={inputClass} inputMode="tel" autoComplete="tel" value={phone} onChange={(event) => setPhone(event.target.value)} />
                </Field>
                <Field label="ФИО руководителя" error={directorMessage}>
                  <input className={inputClass} autoComplete="name" value={directorName} onChange={(event) => setDirectorName(event.target.value)} />
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
