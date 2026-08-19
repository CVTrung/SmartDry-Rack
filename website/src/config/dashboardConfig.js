function readNumber(value, fallback, { min, max, integer = false }) {
  if (value === undefined || value === null || value === '') {
    return fallback;
  }

  const parsedValue = Number(value);

  if (
    !Number.isFinite(parsedValue)
    || (integer && !Number.isInteger(parsedValue))
    || parsedValue < min
    || parsedValue > max
  ) {
    return fallback;
  }

  return parsedValue;
}

export const dashboardConfig = Object.freeze({
  rainForecastWindowHours: readNumber(
    import.meta.env.VITE_RAIN_FORECAST_WINDOW_HOURS,
    3,
    { min: 1, max: 120, integer: true },
  ),
  rainWarningThresholdPercent: readNumber(
    import.meta.env.VITE_RAIN_WARNING_THRESHOLD_PERCENT,
    60,
    { min: 0, max: 100 },
  ),
});
