export const getToken = () => localStorage.getItem("token");
export const setToken = (t: string | null) =>
  t ? localStorage.setItem("token", t) : localStorage.removeItem("token");

export class ApiError extends Error {
  constructor(public status: number, public detail: any) {
    super(typeof detail === "string" ? detail : detail?.message || "Request failed");
  }
}

export async function api<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const t = getToken();
  if (t) headers.Authorization = `Bearer ${t}`;
  const r = await fetch(`/api/v1${path}`, { ...opts, headers: { ...headers, ...(opts.headers as any) } });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new ApiError(r.status, body.detail ?? r.statusText);
  }
  return r.json();
}

export async function download(path: string, filename: string) {
  const r = await fetch(`/api/v1${path}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!r.ok) throw new ApiError(r.status, (await r.json().catch(() => ({}))).detail ?? "Export failed");
  const url = URL.createObjectURL(await r.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}
