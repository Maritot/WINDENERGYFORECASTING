export type ComparisonRow = Record<string, string | number | boolean | null>;

export type ModelMetadata = {
  best_model?: string;
  lookback_window?: number;
  required_columns?: string[];
};

export type ModelInfoResponse = {
  model_ready: boolean;
  comparison_ready: boolean;
  metadata?: ModelMetadata;
  minimum_history_rows?: number;
  feature_warmup_rows?: number;
  comparison?: ComparisonRow[];
};

export type HealthResponse = {
  status: string;
};

export type LocationResult = {
  name: string;
  country: string | null;
  admin1: string | null;
  latitude: number;
  longitude: number;
  timezone: string;
};

export type LocationSearchResponse = {
  results: LocationResult[];
};

export type ForecastRequest = {
  location: LocationResult;
  start_date: string;
  days: number;
};

export type DailyForecast = {
  date: string;
  total_energy: number;
  average_power: number;
  peak_power: number;
  peak_time: string;
  is_selected: boolean;
};

export type HourlyForecast = {
  timestamp: string;
  wind_speed: number;
  wind_direction: number;
  temperature: number;
  pressure: number;
  predicted_power: number;
};

export type ForecastResponse = {
  location: LocationResult;
  selected_date: string;
  days: number;
  model_name: string;
  daily_forecast: DailyForecast[];
  selected_day_hourly: HourlyForecast[];
};

export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

function getErrorMessage(payload: unknown): string {
  if (!payload) {
    return "Request failed.";
  }

  if (typeof payload === "string") {
    return payload;
  }

  if (typeof payload === "object") {
    const detail = Reflect.get(payload, "detail");
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === "string") {
            return item;
          }
          if (item && typeof item === "object") {
            return String(Reflect.get(item, "msg") ?? JSON.stringify(item));
          }
          return String(item);
        })
        .join("; ");
    }

    if (typeof detail === "string") {
      return detail;
    }

    const message = Reflect.get(payload, "message");
    if (typeof message === "string") {
      return message;
    }
  }

  return "Request failed.";
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    throw new Error(getErrorMessage(payload));
  }

  return payload as T;
}

export function fetchHealth() {
  return requestJson<HealthResponse>("/health");
}

export function fetchModelInfo() {
  return requestJson<ModelInfoResponse>("/model-info");
}

export function searchLocations(query: string) {
  const params = new URLSearchParams({ q: query });
  return requestJson<LocationSearchResponse>(`/locations/search?${params.toString()}`);
}

export function fetchForecast(request: ForecastRequest) {
  return requestJson<ForecastResponse>("/forecast", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
