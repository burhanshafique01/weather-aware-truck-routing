const timeFmt = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
const dayTimeFmt = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  hour: "numeric",
  minute: "2-digit",
});
const tzName =
  new Intl.DateTimeFormat(undefined, { timeZoneName: "short" })
    .formatToParts(new Date())
    .find((p) => p.type === "timeZoneName")?.value ?? "";

export const timezoneLabel = tzName;

export function formatDuration(seconds: number): string {
  const totalMin = Math.round(seconds / 60);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return h ? `${h} h ${m.toString().padStart(2, "0")} min` : `${m} min`;
}

export function formatMiles(mi: number): string {
  return `${mi >= 100 ? Math.round(mi).toLocaleString() : mi.toFixed(1)} mi`;
}

export function formatTime(iso: string | Date): string {
  return timeFmt.format(typeof iso === "string" ? new Date(iso) : iso);
}

export function formatDayTime(iso: string | Date): string {
  return dayTimeFmt.format(typeof iso === "string" ? new Date(iso) : iso);
}

/** Value for <input type="datetime-local"> in the browser's timezone. */
export function toLocalInputValue(date: Date): string {
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function nextQuarterHour(from = new Date()): Date {
  const d = new Date(from);
  d.setSeconds(0, 0);
  d.setMinutes(Math.ceil((d.getMinutes() + 1) / 15) * 15);
  return d;
}
