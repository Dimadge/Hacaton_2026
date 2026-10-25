import { createContext, useContext, useEffect, useState } from "react";
import { api, setUnauthorizedHandler } from "../../api/client";
import type { LoginResponse, Role } from "../../api/types";

type Session = { token: string; role: Role };
const KEY = "alfa-navigator-session";

const AuthContext = createContext<{
  session: Session | null;
  login: (email: string, password: string) => Promise<Role>;
  register: (body: { email: string; password: string; company_name: string; inn: string; industry: string }) => Promise<Role>;
  logout: () => void;
} | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  });

  function logout() {
    sessionStorage.removeItem(KEY);
    setSession(null);
  }

  useEffect(() => setUnauthorizedHandler(logout), []);

  function store(data: LoginResponse) {
    const next = { token: data.access_token, role: data.role };
    sessionStorage.setItem(KEY, JSON.stringify(next));
    setSession(next);
    return data.role;
  }

  async function login(email: string, password: string) {
    return store(await api<LoginResponse>("/auth/login", { body: { email, password } }));
  }

  async function register(body: { email: string; password: string; company_name: string; inn: string; industry: string }) {
    return store(await api<LoginResponse>("/auth/register", { body }));
  }

  return <AuthContext.Provider value={{ session, login, register, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider отсутствует");
  return value;
}
