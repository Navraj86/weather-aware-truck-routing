const timeFmt = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
const dayTimeFmt = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  hour: "numeric",
  minute: "2-digit",
});
const tzFmt = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" });

export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min`;
}

export function formatDayTime(iso: string | number | Date): string {
  return dayTimeFmt.format(new Date(iso));
}

export function formatTime(iso: string | number | Date): string {
  return timeFmt.format(new Date(iso));
}

export function localTimeZoneName(): string {
  const part = tzFmt.formatToParts(new Date()).find((p) => p.type === "timeZoneName");
  return part?.value ?? "local time";
}

export function formatMiles(mi: number): string {
  return `${mi >= 100 ? Math.round(mi).toLocaleString() : mi.toFixed(1)} mi`;
}

/** Value for <input type="datetime-local"> in the browser's time zone. */
export function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Next quarter hour from now, as a sensible default departure. */
export function nextQuarterHour(now = new Date()): Date {
  const d = new Date(now);
  d.setSeconds(0, 0);
  d.setMinutes(Math.ceil((d.getMinutes() + 1) / 15) * 15);
  return d;
}
