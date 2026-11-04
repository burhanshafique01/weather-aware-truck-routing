import type { Place, Plan, PlanInput } from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection and try again.");
  }
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(describeError(body, resp.status));
  return body as T;
}

/** DRF returns either {detail} or {field: [messages]}; flatten to one line. */
function describeError(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    const parts = Object.entries(record).map(([field, value]) => {
      const msg = Array.isArray(value) ? value.join(" ") : typeof value === "object" ? JSON.stringify(value) : String(value);
      return `${field.replace("_", " ")}: ${msg}`;
    });
    if (parts.length) return parts.join(" · ");
  }
  if (status === 429) return "Too many requests. Please wait a moment.";
  return `Request failed (${status}).`;
}

export function planTrip(input: PlanInput, signal?: AbortSignal): Promise<Plan> {
  return request<Plan>("/api/plan/", { method: "POST", body: JSON.stringify(input), signal });
}

export async function searchPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  const data = await request<{ results: Place[] }>(`/api/geocode/?q=${encodeURIComponent(query)}`, { signal });
  return data.results;
}
