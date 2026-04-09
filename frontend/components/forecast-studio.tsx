"use client";

import { useEffect, useState } from "react";

import {
  apiBaseUrl,
  fetchForecast,
  fetchHealth,
  fetchModelInfo,
  searchLocations,
  type DailyForecast,
  type ForecastResponse,
  type LocationResult,
  type ModelInfoResponse,
} from "@/lib/api";

type FeedbackTone = "neutral" | "success" | "error";

type FeedbackState = {
  message: string;
  tone: FeedbackTone;
};

function toDateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(value: Date, days: number) {
  const next = new Date(value);
  next.setDate(next.getDate() + days);
  return next;
}

function formatNumber(value: number, maximumFractionDigits = 2) {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits,
  }).format(value);
}

function formatDisplayDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${value}T00:00:00`));
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(new Date(`${value}T00:00:00`));
}

function formatHour(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatLocationLabel(location: LocationResult) {
  return [location.name, location.admin1, location.country].filter(Boolean).join(", ");
}

function findSelectedDay(forecast: ForecastResponse | null): DailyForecast | null {
  if (!forecast) {
    return null;
  }
  return forecast.daily_forecast.find((day) => day.is_selected) ?? null;
}

export function ForecastStudio() {
  const today = new Date();
  const minForecastDate = toDateInputValue(today);
  const maxForecastDate = toDateInputValue(addDays(today, 9));

  const [healthLabel, setHealthLabel] = useState("Checking...");
  const [modelInfo, setModelInfo] = useState<ModelInfoResponse | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  const [locationQuery, setLocationQuery] = useState("");
  const [selectedLocation, setSelectedLocation] = useState<LocationResult | null>(null);
  const [locationOptions, setLocationOptions] = useState<LocationResult[]>([]);
  const [searchingLocations, setSearchingLocations] = useState(false);
  const [locationSearchMessage, setLocationSearchMessage] = useState("");

  const [forecastDate, setForecastDate] = useState(minForecastDate);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackState>({
    message: "Search for a city and choose the forecast start date to generate a 7-day estimate.",
    tone: "neutral",
  });

  useEffect(() => {
    async function loadDashboard() {
      try {
        const [health, info] = await Promise.all([fetchHealth(), fetchModelInfo()]);
        setHealthLabel(health.status === "ok" ? "Online" : health.status);
        setModelInfo(info);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Backend is unavailable.";
        setHealthLabel("Offline");
        setFeedback({
          message,
          tone: "error",
        });
      } finally {
        setStatusLoading(false);
      }
    }

    void loadDashboard();
  }, []);

  useEffect(() => {
    const trimmedQuery = locationQuery.trim();
    const selectedLabel = selectedLocation ? formatLocationLabel(selectedLocation) : "";

    if (!trimmedQuery || trimmedQuery.length < 2 || trimmedQuery === selectedLabel) {
      setLocationOptions([]);
      setLocationSearchMessage("");
      setSearchingLocations(false);
      return;
    }

    let isCancelled = false;
    const timeout = window.setTimeout(async () => {
      try {
        setSearchingLocations(true);
        setLocationSearchMessage("");
        const payload = await searchLocations(trimmedQuery);
        if (isCancelled) {
          return;
        }

        setLocationOptions(payload.results);
        if (payload.results.length === 0) {
          setLocationSearchMessage("No matching cities were found.");
        }
      } catch (error) {
        if (isCancelled) {
          return;
        }
        setLocationOptions([]);
        setLocationSearchMessage(
          error instanceof Error ? error.message : "Could not search locations right now."
        );
      } finally {
        if (!isCancelled) {
          setSearchingLocations(false);
        }
      }
    }, 320);

    return () => {
      isCancelled = true;
      window.clearTimeout(timeout);
    };
  }, [locationQuery, selectedLocation]);

  const minimumRows = modelInfo?.minimum_history_rows ?? modelInfo?.metadata?.lookback_window ?? "--";
  const activeModel = modelInfo?.metadata?.best_model ?? "Unavailable";
  const comparisonAvailable = modelInfo?.comparison_ready ? "Available" : "Not saved";
  const selectedDay = findSelectedDay(forecast);
  const showLocationResults =
    locationQuery.trim().length >= 2 &&
    (!selectedLocation || locationQuery.trim() !== formatLocationLabel(selectedLocation));

  function handleLocationInput(value: string) {
    setLocationQuery(value);
    setSelectedLocation(null);
  }

  function handleLocationSelect(location: LocationResult) {
    setSelectedLocation(location);
    setLocationQuery(formatLocationLabel(location));
    setLocationOptions([]);
    setLocationSearchMessage("");
  }

  async function handleForecastSubmit() {
    if (!selectedLocation) {
      setFeedback({
        message: "Choose a city from the search results before running the forecast.",
        tone: "error",
      });
      return;
    }

    if (!forecastDate) {
      setFeedback({
        message: "Select a valid forecast date.",
        tone: "error",
      });
      return;
    }

    try {
      setForecastLoading(true);
      setFeedback({
        message: "Fetching hourly weather data and generating your 7-day wind energy estimate...",
        tone: "neutral",
      });

      const payload = await fetchForecast({
        location: selectedLocation,
        start_date: forecastDate,
        days: 7,
      });

      setForecast(payload);
      setFeedback({
        message: "Forecast ready. These values are estimated from Open-Meteo weather inputs and the saved model.",
        tone: "success",
      });
    } catch (error) {
      setForecast(null);
      setFeedback({
        message: error instanceof Error ? error.message : "Forecast generation failed.",
        tone: "error",
      });
    } finally {
      setForecastLoading(false);
    }
  }

  return (
    <div className="studio-shell">
      <div className="ambient-orb one" />
      <div className="ambient-orb two" />

      <main className="studio">
        <section className="hero">
          <div className="hero-copy">
            <p className="eyebrow">7-Day Wind Energy Forecast</p>
            <h1>Choose a city and date. Forecast a week of wind energy output.</h1>
            <p className="hero-text">
              The app pulls hourly weather from Open-Meteo, then runs the saved wind model
              recursively to estimate the selected day and the next 6 days. Treat this as a
              prototype estimate, not a guaranteed generation commitment.
            </p>

            <div className="forecast-form">
              <div className="field-grid">
                <div className="field search-field">
                  <label htmlFor="location-search">City or forecast location</label>
                  <input
                    id="location-search"
                    type="text"
                    value={locationQuery}
                    onChange={(event) => handleLocationInput(event.target.value)}
                    placeholder="Search for Berlin, Chennai, Chicago..."
                    autoComplete="off"
                  />
                  <span className="field-hint">
                    {selectedLocation
                      ? `Selected: ${formatLocationLabel(selectedLocation)}`
                      : "Search and select one location result."}
                  </span>

                  {showLocationResults ? (
                    <div className="search-results">
                      {searchingLocations ? (
                        <div className="search-state">Searching locations...</div>
                      ) : locationOptions.length > 0 ? (
                        locationOptions.map((location) => (
                          <button
                            key={`${location.latitude}-${location.longitude}-${location.name}`}
                            className="search-option"
                            type="button"
                            onClick={() => handleLocationSelect(location)}
                          >
                            <strong>{formatLocationLabel(location)}</strong>
                            <span>{location.timezone}</span>
                          </button>
                        ))
                      ) : (
                        <div className="search-state">
                          {locationSearchMessage || "No matching locations were found."}
                        </div>
                      )}
                    </div>
                  ) : null}
                </div>

                <div className="field">
                  <label htmlFor="forecast-date">Forecast start date</label>
                  <input
                    id="forecast-date"
                    type="date"
                    value={forecastDate}
                    min={minForecastDate}
                    max={maxForecastDate}
                    onChange={(event) => setForecastDate(event.target.value)}
                  />
                  <span className="field-hint">
                    The forecast covers this date plus the next 6 days.
                  </span>
                </div>
              </div>

              <div className="hero-actions">
                <button
                  className="button primary"
                  type="button"
                  onClick={() => void handleForecastSubmit()}
                  disabled={forecastLoading}
                >
                  {forecastLoading ? "Forecasting..." : "Forecast Wind Energy"}
                </button>
              </div>

              <p
                className={`feedback ${
                  feedback.tone === "error" ? "error" : feedback.tone === "success" ? "success" : ""
                }`}
              >
                {feedback.message}
              </p>
            </div>
          </div>

          <aside className="hero-side">
            <div className="hero-stat">
              <p className="section-tag">Backend</p>
              <strong>{healthLabel}</strong>
              <span>{statusLoading ? "Checking service health..." : `Connected to ${apiBaseUrl}`}</span>
            </div>

            <div className="hero-stat">
              <p className="section-tag">Forecast Engine</p>
              <strong>{activeModel}</strong>
              <span>Recursive hourly model seeded from the saved history window.</span>
            </div>

            <div className="hero-stat">
              <p className="section-tag">Forecast Range</p>
              <strong>7 days</strong>
              <span>
                Choose a date from {minForecastDate} to {maxForecastDate}.
              </span>
            </div>
          </aside>
        </section>

        <section className="status-grid">
          <article className="status-card">
            <p className="status-label">Service Status</p>
            <strong>{healthLabel}</strong>
            <span className="muted">FastAPI forecast backend</span>
          </article>

          <article className="status-card">
            <p className="status-label">Active Model</p>
            <strong>{activeModel}</strong>
            <span className="muted">Best saved artifact returned by the backend.</span>
          </article>

          <article className="status-card">
            <p className="status-label">History Seed</p>
            <strong>{minimumRows} rows</strong>
            <span className="muted">Recent saved rows used to warm up lag and rolling features.</span>
          </article>

          <article className="status-card">
            <p className="status-label">Model Comparison</p>
            <strong>{comparisonAvailable}</strong>
            <span className="muted">Saved evaluation summary from training artifacts.</span>
          </article>
        </section>

        {forecast && selectedDay ? (
          <>
            <section className="panel selected-day-panel">
              <div className="section-heading">
                <div>
                  <p className="section-tag">Selected Day</p>
                  <h2>{formatDisplayDate(selectedDay.date)}</h2>
                </div>
                <div className="location-pill">{formatLocationLabel(forecast.location)}</div>
              </div>

              <p className="section-text">
                Estimated wind energy for the selected day based on Open-Meteo weather inputs and
                the saved recursive forecast model.
              </p>

              <div className="summary-band">
                <div className="summary-card warm">
                  <span className="metric-label">Estimated Daily Energy</span>
                  <strong className="metric-value">{formatNumber(selectedDay.total_energy)}</strong>
                  <span className="metric-note">Sum of hourly predicted power over the local day.</span>
                </div>

                <div className="summary-card cool">
                  <span className="metric-label">Average Power</span>
                  <strong className="metric-value">{formatNumber(selectedDay.average_power)}</strong>
                  <span className="metric-note">Average hourly output estimate for the selected day.</span>
                </div>

                <div className="summary-card deep">
                  <span className="metric-label">Peak Hour</span>
                  <strong className="metric-value">{formatNumber(selectedDay.peak_power)}</strong>
                  <span className="metric-note">{formatHour(selectedDay.peak_time)} local time</span>
                </div>

                <div className="summary-card neutral">
                  <span className="metric-label">Model Used</span>
                  <strong className="metric-value summary-model">{forecast.model_name}</strong>
                  <span className="metric-note">{forecast.location.timezone}</span>
                </div>
              </div>
            </section>

            <section className="panel">
              <div className="section-heading">
                <div>
                  <p className="section-tag">7-Day Outlook</p>
                  <h2>Daily Wind Energy Forecast</h2>
                </div>
              </div>

              <div className="days-grid">
                {forecast.daily_forecast.map((day) => (
                  <article
                    key={day.date}
                    className={`day-card ${day.is_selected ? "selected" : ""}`}
                  >
                    <p className="day-card-date">{formatShortDate(day.date)}</p>
                    <strong>{formatNumber(day.total_energy)}</strong>
                    <span>Avg power: {formatNumber(day.average_power)}</span>
                    <span>Peak: {formatNumber(day.peak_power)} at {formatHour(day.peak_time)}</span>
                  </article>
                ))}
              </div>
            </section>

            <section className="panel table-panel">
              <div className="section-heading">
                <div>
                  <p className="section-tag">Hourly Breakdown</p>
                  <h2>{formatDisplayDate(forecast.selected_date)}</h2>
                </div>
              </div>

              <p className="api-caption">
                Each row below uses Open-Meteo weather inputs for the hour and the recursively
                predicted power carried forward through the saved model history window.
              </p>

              <div className="table-shell">
                <table>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Wind Speed (m/s)</th>
                      <th>Direction (deg)</th>
                      <th>Temperature (C)</th>
                      <th>Pressure (hPa)</th>
                      <th>Predicted Power</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forecast.selected_day_hourly.map((row) => (
                      <tr key={row.timestamp}>
                        <td>{formatHour(row.timestamp)}</td>
                        <td>{formatNumber(row.wind_speed, 3)}</td>
                        <td>{formatNumber(row.wind_direction, 0)}</td>
                        <td>{formatNumber(row.temperature, 2)}</td>
                        <td>{formatNumber(row.pressure, 2)}</td>
                        <td>{formatNumber(row.predicted_power, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        ) : (
          <section className="panel empty-panel">
            <div className="section-heading">
              <div>
                <p className="section-tag">Forecast Output</p>
                <h2>Your 7-day estimate will appear here</h2>
              </div>
            </div>

            <p className="section-text">
              Choose a location from the city search, pick a valid start date, and run the forecast
              to see:
            </p>

            <ul className="helper-list">
              <li>A highlighted energy estimate for the selected date.</li>
              <li>A 7-day daily wind energy outlook.</li>
              <li>An hourly table for the selected day with weather inputs and predicted power.</li>
            </ul>
          </section>
        )}
      </main>
    </div>
  );
}
