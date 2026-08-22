export const LINE_HOURS = extra => extra ? 100 : 80;
export const PLANT_HOURS = extra => extra ? 300 : 240;

export function orderHours(quantity, sam) {
  return Number(quantity || 0) * Number(sam || 0) / 60;
}

export function durationDays(hours, extraHours = false) {
  return hours / LINE_HOURS(extraHours);
}

export function displayDuration(days) {
  return Math.round(days * 10) / 10;
}

export function occupancyTone(pct) {
  if (pct > 100) return 'red';
  if (pct >= 80) return 'yellow';
  return 'green';
}

export function liveCalc(quantity, sam, extraHours = false) {
  const hours = orderHours(quantity, sam);
  const days = durationDays(hours, extraHours);
  return { hours, days, displayDays: displayDuration(days), plantDays: displayDuration(hours / PLANT_HOURS(extraHours)) };
}
