import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "../components/Layout";
import { AuthProvider } from "../features/auth/session";
import { ApplicationPage } from "../pages/Application";
import { BankApplicationPage } from "../pages/BankApplication";
import { BankPage } from "../pages/Bank";
import { DashboardPage } from "../pages/Dashboard";
import { LoginPage } from "../pages/Login";
import { ProductsPage } from "../pages/Products";
import { WizardPage } from "../pages/Wizard";

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<Layout role="CLIENT" />}>
            <Route path="/client" element={<DashboardPage />} />
            <Route path="/client/products" element={<ProductsPage />} />
            <Route path="/client/applications/new" element={<WizardPage />} />
            <Route path="/client/applications/:id/edit" element={<WizardPage />} />
            <Route path="/client/applications/:id" element={<ApplicationPage />} />
          </Route>
          <Route element={<Layout role="BANK_EMPLOYEE" />}>
            <Route path="/bank" element={<BankPage />} />
            <Route path="/bank/applications/:id" element={<BankApplicationPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
