export function emailError(value: string): string {
  const email = value.trim();
  if (!email) return "Укажите почту";
  if (/\s/.test(email) || email.split("@").length !== 2) {
    return "В почте должен быть один символ @ и не должно быть пробелов";
  }
  const [local, domain] = email.split("@");
  if (!local) return "Укажите имя почты до символа @";
  const labels = domain.split(".");
  if (labels.length < 2 || labels.some((part) => part.length === 0)) {
    return "После @ укажите домен с точкой, например company.ru";
  }
  if (!/^[A-Za-zА-Яа-яЁё]{2,}$/.test(labels[labels.length - 1])) {
    return "После последней точки укажите зону домена, например ru";
  }
  return "";
}
