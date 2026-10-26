export class ApiError extends Error {
  status: number;
  code: string;
  details: { fields?: { field: string; message: string }[] };

  constructor(status: number, code: string, message: string, details = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

function baseUrl() {
  // Same-origin routing works locally and behind a remote proxy/TLS.
  // Never make visitors' browsers connect to their own localhost:8000.
  return "/api/v1";
}

export async function api<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    token?: string | null;
    idempotencyKey?: string;
  } = {},
): Promise<T> {
  const headers = new Headers();
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);
  if (options.idempotencyKey) headers.set("Idempotency-Key", options.idempotencyKey);
  let response: Response;
  try {
    response = await fetch(`${baseUrl()}${path}`, {
      method: options.method ?? (options.body !== undefined ? "POST" : "GET"),
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "NETWORK", "Нет связи с сервером. Проверьте соединение и повторите попытку.");
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) onUnauthorized();
    throw new ApiError(response.status, data.code ?? "HTTP_ERROR", data.message ?? `Ошибка запроса (HTTP ${response.status})`, data.details ?? {});
  }
  return data as T;
}
