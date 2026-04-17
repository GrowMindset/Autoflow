import { WorkflowNodeData } from '../types/workflow';

const DELAY_UNIT_SECONDS: Record<string, number> = {
  second: 1,
  seconds: 1,
  minute: 60,
  minutes: 60,
  hour: 3600,
  hours: 3600,
};

const WEEKDAY_NAME_TO_INT: Record<string, number> = {
  SUN: 0,
  MON: 1,
  TUE: 2,
  WED: 3,
  THU: 4,
  FRI: 5,
  SAT: 6,
};

const WEEKDAY_SHORT_TO_INT: Record<string, number> = {
  Sun: 0,
  Mon: 1,
  Tue: 2,
  Wed: 3,
  Thu: 4,
  Fri: 5,
  Sat: 6,
};

const MONTH_NAME_TO_INT: Record<string, number> = {
  JAN: 1,
  FEB: 2,
  MAR: 3,
  APR: 4,
  MAY: 5,
  JUN: 6,
  JUL: 7,
  AUG: 8,
  SEP: 9,
  OCT: 10,
  NOV: 11,
  DEC: 12,
};

const MAX_SCHEDULE_LOOKAHEAD_MINUTES = 60 * 24 * 400;
const scheduleNextRunCache = new Map<
  string,
  { minuteBucket: number; nextRunMs: number | null }
>();
const timeFormatterCache = new Map<string, Intl.DateTimeFormat>();

type LocalizedDateParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  weekday: number;
};

const toInteger = (
  rawValue: unknown,
  {
    fallback,
    minimum,
    maximum,
  }: { fallback: number; minimum: number; maximum: number },
): number => {
  const parsed = Number.parseInt(String(rawValue ?? ''), 10);
  const safeValue = Number.isFinite(parsed) ? parsed : fallback;
  if (safeValue < minimum) return minimum;
  if (safeValue > maximum) return maximum;
  return safeValue;
};

const toBoolean = (rawValue: unknown, fallback = true): boolean => {
  if (rawValue === undefined || rawValue === null) return fallback;
  if (typeof rawValue === 'boolean') return rawValue;
  if (typeof rawValue === 'number') return rawValue !== 0;
  if (typeof rawValue === 'string') {
    const normalized = rawValue.trim().toLowerCase();
    if (!normalized) return fallback;
    if (['1', 'true', 'yes', 'on'].includes(normalized)) return true;
    if (['0', 'false', 'no', 'off'].includes(normalized)) return false;
  }
  return fallback;
};

const normalizeTimeZone = (rawValue: unknown): string => {
  const candidate = String(rawValue || 'Asia/Kolkata').trim() || 'Asia/Kolkata';
  try {
    Intl.DateTimeFormat('en-US', { timeZone: candidate });
    return candidate;
  } catch {
    return 'Asia/Kolkata';
  }
};

const getTimeFormatter = (timezone: string): Intl.DateTimeFormat => {
  const cached = timeFormatterCache.get(timezone);
  if (cached) return cached;

  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    weekday: 'short',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  timeFormatterCache.set(timezone, formatter);
  return formatter;
};

const getLocalizedDateParts = (
  date: Date,
  timezone: string,
): LocalizedDateParts | null => {
  const formatter = getTimeFormatter(timezone);
  const parts = formatter.formatToParts(date);
  let year = 0;
  let month = 0;
  let day = 0;
  let hour = 0;
  let minute = 0;
  let weekday = 0;

  for (const part of parts) {
    if (part.type === 'year') year = Number.parseInt(part.value, 10) || 0;
    if (part.type === 'month') month = Number.parseInt(part.value, 10) || 0;
    if (part.type === 'day') day = Number.parseInt(part.value, 10) || 0;
    if (part.type === 'hour') hour = Number.parseInt(part.value, 10) || 0;
    if (part.type === 'minute') minute = Number.parseInt(part.value, 10) || 0;
    if (part.type === 'weekday') weekday = WEEKDAY_SHORT_TO_INT[part.value] ?? 0;
  }

  if (!year || !month || !day) return null;
  return { year, month, day, hour, minute, weekday };
};

const formatRemaining = (remainingMs: number): string => {
  const totalSeconds = Math.max(0, Math.floor(remainingMs / 1000));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  return `${days}d ${String(hours).padStart(2, '0')}h ${String(minutes).padStart(2, '0')}m ${String(seconds).padStart(2, '0')}s`;
};

const parseDelayTargetTime = (
  config: Record<string, any>,
  startedAt: string | null | undefined,
): number | null => {
  const untilDateRaw = String(config?.until_datetime || '').trim();
  if (untilDateRaw) {
    const targetMs = Date.parse(untilDateRaw);
    return Number.isFinite(targetMs) ? targetMs : null;
  }

  const amountRaw = config?.amount ?? config?.seconds;
  if (amountRaw === undefined || amountRaw === null || String(amountRaw).trim() === '') {
    return null;
  }

  const amount = Number.parseFloat(String(amountRaw).trim());
  if (!Number.isFinite(amount) || amount < 0) {
    return null;
  }

  const startedAtMs = Date.parse(String(startedAt || ''));
  if (!Number.isFinite(startedAtMs)) {
    return null;
  }

  const unit = String(config?.unit || 'seconds').trim().toLowerCase();
  const multiplier = DELAY_UNIT_SECONDS[unit];
  if (!multiplier) return null;

  return startedAtMs + amount * multiplier * 1000;
};

const isWildcard = (expr: string): boolean => expr.trim() === '*';

const combineDayMatches = (
  dayOfMonthExpr: string,
  dayOfWeekExpr: string,
  dayOfMonthMatch: boolean,
  dayOfWeekMatch: boolean,
): boolean => {
  const domWildcard = isWildcard(dayOfMonthExpr);
  const dowWildcard = isWildcard(dayOfWeekExpr);

  if (domWildcard && dowWildcard) return true;
  if (domWildcard) return dayOfWeekMatch;
  if (dowWildcard) return dayOfMonthMatch;
  return dayOfMonthMatch || dayOfWeekMatch;
};

const tokenToInt = (
  token: string,
  {
    minimum,
    maximum,
    nameToValue,
    treat7As0,
  }: {
    minimum: number;
    maximum: number;
    nameToValue?: Record<string, number>;
    treat7As0?: boolean;
  },
): number => {
  const normalized = token.trim().toUpperCase();
  let value: number;

  if (nameToValue && Object.prototype.hasOwnProperty.call(nameToValue, normalized)) {
    value = nameToValue[normalized];
  } else {
    value = Number.parseInt(normalized, 10);
  }

  if (!Number.isFinite(value)) {
    throw new Error(`Invalid schedule token '${token}'.`);
  }

  if (treat7As0 && value === 7) value = 0;
  if (value < minimum || value > maximum) {
    throw new Error(`Schedule value '${value}' out of range [${minimum}, ${maximum}].`);
  }
  return value;
};

const expandValues = (
  expr: string,
  {
    minimum,
    maximum,
    nameToValue,
    treat7As0,
  }: {
    minimum: number;
    maximum: number;
    nameToValue?: Record<string, number>;
    treat7As0?: boolean;
  },
): Set<number> => {
  const cleaned = expr.trim().toUpperCase();
  if (!cleaned) {
    throw new Error('Schedule field cannot be empty.');
  }

  const values = new Set<number>();
  const segments = cleaned.split(',').map((part) => part.trim());
  for (const segment of segments) {
    if (!segment) {
      throw new Error(`Invalid empty schedule segment in '${expr}'.`);
    }

    let step = 1;
    let base = segment;
    if (segment.includes('/')) {
      const [baseRaw, stepRaw] = segment.split('/', 2);
      base = baseRaw.trim();
      step = Number.parseInt(stepRaw.trim(), 10);
      if (!Number.isFinite(step) || step <= 0) {
        throw new Error(`Invalid step value '${stepRaw}' in '${segment}'.`);
      }
    }

    let start = minimum;
    let end = maximum;

    if (base !== '*') {
      if (base.includes('-')) {
        const [leftRaw, rightRaw] = base.split('-', 2);
        start = tokenToInt(leftRaw, { minimum, maximum, nameToValue, treat7As0 });
        end = tokenToInt(rightRaw, { minimum, maximum, nameToValue, treat7As0 });
        if (end < start) {
          throw new Error(`Invalid range '${base}' (end < start).`);
        }
      } else {
        const single = tokenToInt(base, { minimum, maximum, nameToValue, treat7As0 });
        start = single;
        end = single;
      }
    }

    for (let value = start; value <= end; value += step) {
      values.add(value);
    }
  }

  return values;
};

const valueMatches = (
  expr: string,
  value: number,
  {
    minimum,
    maximum,
    nameToValue,
    treat7As0,
  }: {
    minimum: number;
    maximum: number;
    nameToValue?: Record<string, number>;
    treat7As0?: boolean;
  },
): boolean => {
  const allowed = expandValues(expr, { minimum, maximum, nameToValue, treat7As0 });
  return allowed.has(value);
};

const cronMatches = (
  cronExpr: string,
  date: Date,
  timezone: string,
): boolean => {
  const fields = cronExpr.split(/\s+/).map((part) => part.trim()).filter(Boolean);
  if (fields.length !== 5) {
    return false;
  }

  const localized = getLocalizedDateParts(date, timezone);
  if (!localized) return false;

  const [minuteExpr, hourExpr, domExpr, monthExpr, dowExpr] = fields;

  const minuteMatch = valueMatches(minuteExpr, localized.minute, { minimum: 0, maximum: 59 });
  const hourMatch = valueMatches(hourExpr, localized.hour, { minimum: 0, maximum: 23 });
  const monthMatch = valueMatches(monthExpr, localized.month, {
    minimum: 1,
    maximum: 12,
    nameToValue: MONTH_NAME_TO_INT,
  });
  const dayOfMonthMatch = valueMatches(domExpr, localized.day, { minimum: 1, maximum: 31 });
  const dayOfWeekMatch = valueMatches(dowExpr, localized.weekday, {
    minimum: 0,
    maximum: 6,
    nameToValue: WEEKDAY_NAME_TO_INT,
    treat7As0: true,
  });

  const dayMatch = combineDayMatches(
    domExpr,
    dowExpr,
    dayOfMonthMatch,
    dayOfWeekMatch,
  );

  return minuteMatch && hourMatch && monthMatch && dayMatch;
};

const normalizeWeekday = (rawValue: unknown): number => {
  const normalized = String(rawValue ?? '').trim().toUpperCase();
  if (Object.prototype.hasOwnProperty.call(WEEKDAY_NAME_TO_INT, normalized)) {
    return WEEKDAY_NAME_TO_INT[normalized];
  }
  let value = Number.parseInt(normalized || '0', 10);
  if (!Number.isFinite(value)) value = 0;
  if (value === 7) value = 0;
  if (value < 0 || value > 6) return 0;
  return value;
};

const scheduleRuleMatches = (
  rule: Record<string, any>,
  date: Date,
  timezone: string,
): boolean => {
  const interval = String(rule?.interval || '').trim().toLowerCase();
  const localized = getLocalizedDateParts(date, timezone);
  if (!localized) return false;

  if (interval === 'custom') {
    const cronExpr = String(rule?.cron || '').trim();
    if (!cronExpr) return false;
    return cronMatches(cronExpr, date, timezone);
  }

  if (!['minutes', 'hours', 'days', 'weeks', 'months'].includes(interval)) {
    return false;
  }

  const every = toInteger(rule?.every, {
    fallback: 1,
    minimum: 1,
    maximum: interval === 'minutes'
      ? 59
      : interval === 'hours'
        ? 23
        : interval === 'days'
          ? 31
          : interval === 'weeks'
            ? 52
            : 12,
  });
  const triggerMinute = toInteger(rule?.trigger_minute, {
    fallback: 0,
    minimum: 0,
    maximum: 59,
  });

  if (interval === 'minutes') {
    return localized.minute % every === 0;
  }

  if (interval === 'hours') {
    return localized.minute === triggerMinute && localized.hour % every === 0;
  }

  const triggerHour = toInteger(rule?.trigger_hour, {
    fallback: 0,
    minimum: 0,
    maximum: 23,
  });
  if (localized.hour !== triggerHour || localized.minute !== triggerMinute) {
    return false;
  }

  if (interval === 'days') {
    return (localized.day - 1) % every === 0;
  }

  if (interval === 'weeks') {
    const targetWeekday = normalizeWeekday(rule?.trigger_weekday ?? 1);
    if (localized.weekday !== targetWeekday) {
      return false;
    }
    const epochMondayUtc = Date.UTC(1970, 0, 5);
    const localDateUtc = Date.UTC(localized.year, localized.month - 1, localized.day);
    const weekIndex = Math.floor((localDateUtc - epochMondayUtc) / (7 * 86400000));
    return weekIndex % every === 0;
  }

  const targetDayOfMonth = toInteger(rule?.trigger_day_of_month, {
    fallback: 1,
    minimum: 1,
    maximum: 31,
  });
  if (localized.day !== targetDayOfMonth) {
    return false;
  }
  const monthIndex = localized.year * 12 + (localized.month - 1);
  return monthIndex % every === 0;
};

const buildLegacyCron = (config: Record<string, any>): string => {
  const explicit = String(config?.cron || '').trim();
  if (explicit) return explicit;
  const minute = String(config?.minute ?? '*').trim() || '*';
  const hour = String(config?.hour ?? '*').trim() || '*';
  const dayOfMonth = String(config?.day_of_month ?? '*').trim() || '*';
  const month = String(config?.month ?? '*').trim() || '*';
  const dayOfWeek = String(config?.day_of_week ?? '*').trim() || '*';
  return `${minute} ${hour} ${dayOfMonth} ${month} ${dayOfWeek}`;
};

const findNextScheduleRunMs = (
  config: Record<string, any>,
  nowMs: number,
): number | null => {
  const cacheKey = JSON.stringify(config || {});
  const minuteBucket = Math.floor(nowMs / 60000);
  const cached = scheduleNextRunCache.get(cacheKey);
  if (cached && cached.minuteBucket === minuteBucket) {
    return cached.nextRunMs;
  }

  const timezone = normalizeTimeZone(config?.timezone);
  const rules = Array.isArray(config?.rules)
    ? config.rules.filter((item: any) => item && typeof item === 'object')
    : [];
  const enabledRules = rules.filter((rule: any) => toBoolean(rule?.enabled, true));
  const hasRules = enabledRules.length > 0;
  const legacyCron = buildLegacyCron(config);

  const baseMinuteMs = Math.floor(nowMs / 60000) * 60000;
  let nextRunMs: number | null = null;
  for (let offset = 1; offset <= MAX_SCHEDULE_LOOKAHEAD_MINUTES; offset += 1) {
    const candidateMs = baseMinuteMs + offset * 60000;
    const candidate = new Date(candidateMs);
    const due = hasRules
      ? enabledRules.some((rule: any) => scheduleRuleMatches(rule, candidate, timezone))
      : cronMatches(legacyCron, candidate, timezone);
    if (due) {
      nextRunMs = candidateMs;
      break;
    }
  }

  scheduleNextRunCache.set(cacheKey, { minuteBucket, nextRunMs });
  return nextRunMs;
};

const getDelayCountdownLabel = (
  data: WorkflowNodeData,
  nowMs: number,
): string | null => {
  if (data.type !== 'delay' || data.status !== 'RUNNING') {
    return null;
  }

  const startedAt = data.last_execution_result?.started_at;
  const targetMs = parseDelayTargetTime(data.config || {}, startedAt);
  if (!Number.isFinite(targetMs)) {
    return 'Waiting...';
  }

  const remainingMs = Math.max(0, Number(targetMs) - nowMs);
  return `Delay: ${formatRemaining(remainingMs)}`;
};

const getScheduleCountdownLabel = (
  data: WorkflowNodeData,
  nowMs: number,
): string | null => {
  const runtimeStatus = String(data?.status || '').toUpperCase();
  const executionStatus = String(data?.last_execution_result?.status || '').toUpperCase();
  const isActiveScheduleRun =
    (runtimeStatus === 'RUNNING' || runtimeStatus === 'PENDING')
    && (executionStatus === 'RUNNING' || executionStatus === 'PENDING');

  if (data.type !== 'schedule_trigger' || !isActiveScheduleRun) {
    return null;
  }

  const config = data.config || {};
  if (!toBoolean(config.enabled, true)) {
    return 'Schedule: paused';
  }

  const nextRunMs = findNextScheduleRunMs(config, nowMs);
  if (!nextRunMs) {
    return 'Schedule: no upcoming run';
  }

  return `Next: ${formatRemaining(Math.max(0, nextRunMs - nowMs))}`;
};

export const shouldShowLiveNodeCountdown = (data: WorkflowNodeData): boolean => {
  if (data.type === 'delay') {
    return data.status === 'RUNNING';
  }
  if (data.type === 'schedule_trigger') {
    const runtimeStatus = String(data?.status || '').toUpperCase();
    const executionStatus = String(data?.last_execution_result?.status || '').toUpperCase();
    return (
      (runtimeStatus === 'RUNNING' || runtimeStatus === 'PENDING')
      && (executionStatus === 'RUNNING' || executionStatus === 'PENDING')
    );
  }
  return false;
};

export const getNodeCountdownLabel = (
  data: WorkflowNodeData,
  nowMs: number,
): string | null => {
  if (data.type === 'delay') {
    return getDelayCountdownLabel(data, nowMs);
  }
  if (data.type === 'schedule_trigger') {
    return getScheduleCountdownLabel(data, nowMs);
  }
  return null;
};
