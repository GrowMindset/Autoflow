const APP_TIMEZONE = 'Asia/Kolkata';

const dateTimeFormatter = new Intl.DateTimeFormat('en-IN', {
  timeZone: APP_TIMEZONE,
  dateStyle: 'medium',
  timeStyle: 'short',
});

const timeFormatter = new Intl.DateTimeFormat('en-IN', {
  timeZone: APP_TIMEZONE,
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

const sidebarFormatter = new Intl.DateTimeFormat('en-IN', {
  timeZone: APP_TIMEZONE,
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

export const getAppTimezone = (): string => APP_TIMEZONE;

export const formatDateTimeInAppTimezone = (value: string | null | undefined): string => {
  if (!value) return '—';
  return dateTimeFormatter.format(new Date(value));
};

export const formatTimeInAppTimezone = (value: string | null | undefined): string => {
  if (!value) return '--:--:--';
  return timeFormatter.format(new Date(value));
};

export const formatSidebarDateTimeInAppTimezone = (value: string | null | undefined): string => {
  if (!value) return '—';
  return sidebarFormatter.format(new Date(value));
};
