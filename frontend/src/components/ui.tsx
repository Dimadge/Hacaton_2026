import type { ButtonHTMLAttributes, ReactNode } from "react";
import { STATUS_LABEL } from "../lib/format";

const STATUS_TONE: Record<string, string> = {
  DRAFT: "bg-neutral-100 text-neutral-700",
  SUBMITTED: "bg-neutral-200 text-black",
  CHECKING: "bg-amber-100 text-amber-950",
  NEED_INFO: "bg-orange-100 text-orange-950",
  UNDER_REVIEW: "bg-sky-100 text-sky-950",
  OFFERED: "bg-emerald-100 text-emerald-950",
  ACCEPTED: "bg-emerald-200 text-emerald-950",
  SIGNED: "bg-black text-white",
  DISBURSED: "bg-[#ef3124] text-white",
  REJECTED: "bg-red-100 text-red-800",
  CANCELLED: "bg-neutral-200 text-neutral-600",
};

export function BrandMark({ light = false }: { light?: boolean }) {
  return (
    <span className="flex items-center gap-3">
      <span className="relative grid h-10 w-10 shrink-0 place-items-center bg-[#ef3124] text-[22px] font-black leading-none text-white">
        A
        <span className="absolute bottom-1.5 left-2 right-2 h-[3px] bg-white" />
      </span>
      <span className={light ? "text-white" : "text-[#121212]"}>
        <span className="block text-[15px] font-semibold leading-tight tracking-tight">Альфа</span>
        <span className={`block text-xs ${light ? "text-white/60" : "text-neutral-500"}`}>Навигатор</span>
      </span>
    </span>
  );
}

export function Button(props: ButtonHTMLAttributes<HTMLButtonElement> & { kind?: "primary" | "ghost" | "danger" }) {
  const kind = props.kind ?? "primary";
  const look = {
    primary: "bg-[#ef3124] text-white hover:bg-[#d61f14]",
    ghost: "bg-white text-[#121212] border border-black/10 hover:bg-neutral-50",
    danger: "bg-white text-[#ef3124] border border-[#ef3124] hover:bg-red-50",
  }[kind];
  return (
    <button
      {...props}
      className={`inline-flex h-11 cursor-pointer items-center justify-center rounded-lg px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${look} ${props.className ?? ""}`}
    />
  );
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-black/5 bg-white p-6 shadow-[0_10px_30px_rgba(18,18,18,0.04)]">
      {title && <h2 className="mb-4 text-xl font-semibold tracking-tight">{title}</h2>}
      {children}
    </section>
  );
}

export function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1.5 block font-medium text-neutral-700">{label}</span>
      {children}
      {error && <span className="mt-1 block text-[#ef3124]">{error}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg border border-black/10 bg-white px-3 py-2.5 outline-none transition focus:border-[#ef3124] focus:ring-2 focus:ring-[#ef3124]/15";

export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="fixed bottom-6 right-6 z-30 flex items-center gap-2 rounded-xl bg-[#121212] px-4 py-3 text-sm font-medium text-white shadow-lg">
      <span className="h-2 w-2 rounded-full bg-[#ef3124]" />
      {children}
    </div>
  );
}

export function Alert({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-[#ef3124]/20 bg-red-50 px-3 py-2 text-sm text-red-800">{children}</div>;
}

export function Loader() {
  return (
    <div className="flex items-center gap-3 text-sm text-neutral-500">
      <span className="h-2 w-2 animate-pulse rounded-full bg-[#ef3124]" />
      Загрузка…
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="rounded-xl bg-[#f7f7f8] px-4 py-8 text-center text-sm text-neutral-600">{children}</p>;
}

export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? "bg-neutral-100 text-neutral-700";
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${tone}`}>{STATUS_LABEL[status] ?? status}</span>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="space-y-3">
      <Alert>{message}</Alert>
      {onRetry && <Button kind="ghost" onClick={onRetry}>Повторить</Button>}
    </div>
  );
}
