import { NavLink, Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../features/auth/session";
import { BrandMark, Button } from "./ui";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-2 text-sm font-medium transition ${isActive ? "bg-[#121212] text-white" : "text-[#121212] hover:bg-neutral-100"}`;

export function Layout({ role }: { role: "CLIENT" | "BANK_EMPLOYEE" }) {
  const { session, logout } = useAuth();
  if (!session) return <Navigate to="/login" replace />;
  if (session.role !== role) return <Navigate to={session.role === "CLIENT" ? "/client" : "/bank"} replace />;

  return (
    <div className="min-h-screen bg-[#f2f3f5]">
      <header className="sticky top-0 z-20 border-b border-black/5 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <NavLink to={role === "CLIENT" ? "/client" : "/bank"} className="shrink-0">
            <BrandMark />
          </NavLink>
          <nav className="flex flex-wrap items-center justify-end gap-1">
            {role === "CLIENT" && (
              <>
                <NavLink to="/client" end className={linkClass}>Кабинет</NavLink>
                <NavLink to="/client/products" className={linkClass}>Продукты</NavLink>
                <NavLink to="/client/applications/new" className={linkClass}>Новая заявка</NavLink>
              </>
            )}
            {role === "BANK_EMPLOYEE" && <NavLink to="/bank" className={linkClass}>Очередь</NavLink>}
            <Button kind="ghost" className="ml-1" onClick={logout}>Выйти</Button>
          </nav>
        </div>
        <div className="h-1 bg-[#ef3124]" />
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
