export const NEWS = [
  { title: "Оборотное финансирование", body: "Короткое финансирование оборота для торговых компаний.", tags: ["TRADE"] },
  { title: "Обновление оборудования", body: "Условия на обновление оборудования для производственных компаний.", tags: ["MANUFACTURING"] },
  { title: "Как читать условия кредита", body: "Сравните срок, ставку и ежемесячный платёж перед выбором предложения.", tags: [] },
];

export function newsFor(industry: string) {
  return NEWS.filter((item) => item.tags.length === 0 || item.tags.includes(industry));
}
