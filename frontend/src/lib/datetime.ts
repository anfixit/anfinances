import type { IsoDate } from "@/types/api"

export function formatDate(
  iso: IsoDate,
  locale = "ru-RU",
  timeZone?: string,
): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    ...(timeZone ? { timeZone } : {}),
  }).format(new Date(iso))
}
