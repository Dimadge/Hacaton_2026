import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Application, AppEvent, Checks, Explanation, Fulfillment, Offers } from "../api/types";
import { OfferComparison } from "../components/OfferComparison";
import { StatusTimeline } from "../components/StatusTimeline";
import { Alert, Button, Card, ErrorState, Field, inputClass, Loader, Notice, StatusBadge } from "../components/ui";
import { useAuth } from "../features/auth/session";
import { productName, reasonText } from "../lib/format";

export function ApplicationPage() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { session } = useAuth();
  const [application, setApplication] = useState<Application | null>(null);
  const [events, setEvents] = useState<AppEvent[]>([]);
  const [checks, setChecks] = useState<Checks | null>(null);
  const [offers, setOffers] = useState<Offers | null>(null);
  const [explanation, setExplanation] = useState("");
  const [clarification, setClarification] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(false);

  function load() {
    const token = session!.token;
    setError("");
    return Promise.all([
      api<Application>(`/applications/${id}`, { token }),
      api<AppEvent[]>(`/applications/${id}/events`, { token }),
      api<Checks>(`/applications/${id}/checks`, { token }),
      api<Offers>(`/applications/${id}/offers`, { token }),
    ]).then(async ([nextApplication, nextEvents, nextChecks, nextOffers]) => {
      setApplication(nextApplication);
      setEvents(nextEvents);
      setChecks(nextChecks);
      setOffers(nextOffers);
      api<Explanation>(`/applications/${id}/explanation`, { token })
        .then((text) => setExplanation(text.explanation))
        .catch(() => setExplanation(""));
    }).catch((reason) => {
      setError(reason instanceof ApiError ? reason.message : "Не удалось открыть заявку");
      throw reason;
    });
  }

  useEffect(() => { load().catch(() => undefined); }, [id, session]);

  useEffect(() => {
    const text = (location.state as { notice?: string } | null)?.notice;
    if (!text) return;
    setNotice(text);
    navigate(".", { replace: true, state: null });
  }, [location.state, navigate]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  async function act(path: string, body: unknown) {
    setPending(true);
    setError("");
    try {
      const result = await api<Fulfillment>(`/applications/${id}/${path}`, {
        token: session!.token,
        idempotencyKey: path === "submit" ? crypto.randomUUID() : undefined,
        body,
      });
      setApplication((current) => current ? { ...current, status: result.status, version: result.version } : current);
      if (path === "submit") setNotice("Заявка отправлена");
      load().catch(() => undefined);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Действие не выполнено");
    } finally {
      setPending(false);
    }
  }

  if (error && !application) return <ErrorState message={error} onRetry={load} />;
  if (!application || !offers || !checks) return <Loader />;

  const editable = application.status === "DRAFT" || application.status === "NEED_INFO";

  return (
    <div className="space-y-4">
      <Card title="Заявка">
        <div className="mb-2 flex items-center gap-2">
          <StatusBadge status={application.status} />
          <span className="text-sm text-neutral-500">версия {application.version}</span>
        </div>
        <p className="text-lg font-semibold tracking-tight">{productName(application.product_code)}</p>
        <p className="text-sm text-neutral-600">{application.purpose}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button kind="ghost" onClick={() => { load().then(() => setNotice("Заявка обновлена")).catch(() => undefined); }}>Обновить</Button>
          {editable && <Link className="inline-flex h-11 items-center rounded-lg border border-black/10 bg-white px-4 text-sm font-semibold" to={`/client/applications/${id}/edit`}>Изменить анкету</Link>}
          {application.status === "DRAFT" && (
            <Button disabled={pending} onClick={() => act("submit", { version: application.version })}>Отправить</Button>
          )}
        </div>
      </Card>

      {application.status === "NEED_INFO" && (
        <Card title="Пояснение для повторной проверки">
          <Field label="Не короче 10 символов">
            <textarea className={inputClass} value={clarification} onChange={(event) => setClarification(event.target.value)} />
          </Field>
          <Button className="mt-3" disabled={pending || clarification.trim().length < 10} onClick={() => act("submit", { version: application.version, clarification: clarification.trim() })}>
            Отправить снова
          </Button>
        </Card>
      )}

      <Card title="Проверки">
        {checks.checks.length === 0 ? <p className="text-sm">Проверки появятся после отправки.</p> : checks.checks.map((item) => (
          <p key={item.source} className="text-sm">{item.source}: {item.result}</p>
        ))}
        {checks.reason_codes.map((code) => <p key={code} className="text-sm">{reasonText(code)}</p>)}
      </Card>

      <Card title="История"><StatusTimeline events={events} /></Card>

      <Card title="Предложения">
        {offers.offers.length === 0 ? <p className="text-sm">Предложений пока нет.</p> : (
          <OfferComparison application={application} offers={offers.offers} pending={pending} onAccept={(offerId) => {
            if (window.confirm("Принять это предложение? Сумму потом изменить нельзя.")) {
              act("accept", { version: application.version, offer_id: offerId });
            }
          }} />
        )}
        {offers.reason_codes.map((code) => <p key={code} className="mt-2 text-sm">{reasonText(code)}</p>)}
        {explanation && <p className="mt-3 whitespace-pre-wrap text-sm">{explanation}</p>}
        {application.status === "OFFERED" && <Button className="mt-3" kind="danger" disabled={pending} onClick={() => act("cancel", { version: application.version })}>Отказаться</Button>}
        {application.status === "ACCEPTED" && <Button className="mt-3" disabled={pending} onClick={() => act("sign", { version: application.version })}>Подписать договор</Button>}
        {application.status === "SIGNED" && <Button className="mt-3" disabled={pending} onClick={() => act("disburse", { version: application.version })}>Получить средства</Button>}
      </Card>
      {error && <Alert>{error}</Alert>}
      {notice && <Notice>{notice}</Notice>}
    </div>
  );
}
