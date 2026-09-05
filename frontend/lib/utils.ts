const IST_TIMEZONE = "Asia/Kolkata";

export function formatTimeIST(date: Date): string {
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: IST_TIMEZONE,
  }) + " IST";
}

export function formatTime12hIST(date: Date): string {
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
    timeZone: IST_TIMEZONE,
  });
}

export function formatDateTimeIST(date: Date): string {
  return date.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: IST_TIMEZONE,
  });
}

export function formatISOTimeIST(isoString: string | undefined): string {
  if (!isoString) return "---";
  return formatTimeIST(new Date(isoString));
}

export function formatISOTime12hIST(isoString: string | undefined): string {
  if (!isoString) return "---";
  return formatTime12hIST(new Date(isoString));
}
