export function capitalizeDisplayValue(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function startCaseDisplayValue(value: string): string {
  return capitalizeDisplayValue(value);
}
