# Wind Energy Forecasting Project Report Diagrams

## System Architecture Diagram

```mermaid
flowchart LR
    User[User Browser]
    FE[Next.js Frontend]
    API[FastAPI Backend]
    Geo[Open-Meteo Geocoding API]
    Weather[Open-Meteo Forecast API]
    Runtime[Prediction Runtime]
    Seed[Seed History CSV]
    Model[Saved Model Artifacts]
    Output[Daily and Hourly Forecast Output]

    User --> FE
    FE --> API
    API --> Geo
    API --> Weather
    API --> Runtime
    Runtime --> Seed
    Runtime --> Model
    Runtime --> Output
    Output --> API
    API --> FE
    FE --> User
```

## Workflow Diagram

```mermaid
flowchart TD
    A[Open Forecast Page] --> B[Search Location]
    B --> C[Choose Forecast Date]
    C --> D[Submit Forecast Request]
    D --> E[Validate Request Window]
    E --> F[Fetch Hourly Weather]
    F --> G[Load Seed History and Model]
    G --> H[Run Recursive Hourly Prediction]
    H --> I[Aggregate Daily Forecast]
    I --> J[Render Summary, 7-Day Outlook, Hourly Table]
```

## DFD Level 0

```mermaid
flowchart LR
    User[User] -->|Location + Date| System[Wind Energy Forecasting System]
    System -->|Forecast Results| User
    System -->|Weather Query| OpenMeteo[Open-Meteo]
    OpenMeteo -->|Hourly Forecast Data| System
```

## DFD Level 1

```mermaid
flowchart LR
    User --> P1[Location Search and Date Input]
    P1 --> P2[Forecast Request Handler]
    P2 --> P3[Weather Retrieval]
    P2 --> P4[Model Runtime Loader]
    P3 --> P5[Recursive Forecast Engine]
    P4 --> P5
    P5 --> P6[Daily Aggregation]
    P6 --> User
```

## DFD Level 2

```mermaid
flowchart TD
    A[Receive Forecast Request] --> B[Validate Start Date]
    B --> C[Load Model Metadata]
    C --> D[Load Preprocessor]
    D --> E[Load Seed History Rows]
    E --> F[Fetch Hourly Weather]
    F --> G[Append Future Weather Row]
    G --> H[Predict Hourly Power]
    H --> I[Write Prediction Back to History]
    I --> J{More Hours?}
    J -->|Yes| G
    J -->|No| K[Aggregate by Local Date]
    K --> L[Return Forecast Response]
```

## Use Case Diagram

```mermaid
flowchart LR
    User((User))
    UC1[Search Location]
    UC2[Select Forecast Date]
    UC3[Generate Forecast]
    UC4[View Selected-Day Summary]
    UC5[View 7-Day Outlook]
    UC6[Inspect Hourly Breakdown]
    UC7[Check Backend Status]

    User --> UC1
    User --> UC2
    User --> UC3
    User --> UC4
    User --> UC5
    User --> UC6
    User --> UC7
```

## Class Diagram

```mermaid
classDiagram
    class ForecastStudio {
      +locationQuery: string
      +forecastDate: string
      +handleForecastSubmit()
    }

    class ForecastRequest {
      +location
      +start_date
      +days
    }

    class ForecastResponse {
      +location
      +selected_date
      +daily_forecast
      +selected_day_hourly
    }

    class WindDataPreprocessor {
      +minimum_history_rows
      +transform_recent_history()
    }

    class ForecastEngine {
      +generate_forecast()
      +aggregate_daily()
    }

    ForecastStudio --> ForecastRequest
    ForecastRequest --> ForecastEngine
    ForecastEngine --> WindDataPreprocessor
    ForecastEngine --> ForecastResponse
```

## Sequence Diagram

```mermaid
sequenceDiagram
    participant U as User
    participant F as Next.js Frontend
    participant B as FastAPI Backend
    participant O as Open-Meteo
    participant M as Model Runtime

    U->>F: Select location and date
    F->>B: POST /forecast
    B->>O: Request hourly weather
    O-->>B: Return hourly records
    B->>M: Load runtime and seed history
    M-->>B: Ready for inference
    B->>M: Predict recursively per hour
    M-->>B: Hourly predicted power values
    B-->>F: Forecast response
    F-->>U: Display summary and tables
```

## Activity Diagram

```mermaid
flowchart TD
    Start([Start]) --> Search[Search Location]
    Search --> Pick[Pick Date]
    Pick --> Submit[Submit Request]
    Submit --> Validate{Valid?}
    Validate -->|No| Error[Show Validation Error]
    Validate -->|Yes| Fetch[Fetch Weather]
    Fetch --> Predict[Run Recursive Prediction]
    Predict --> Aggregate[Aggregate Daily Results]
    Aggregate --> Display[Display Forecast]
    Display --> End([End])
    Error --> End
```

## Component Diagram

```mermaid
flowchart LR
    FE[Frontend App]
    API[API Layer]
    Weather[Weather Connector]
    Engine[Forecast Engine]
    Model[Model Loader]
    Pre[Preprocessor]
    Data[Dataset and Seed History]

    FE --> API
    API --> Weather
    API --> Engine
    Engine --> Model
    Engine --> Pre
    Engine --> Data
```

## Deployment Diagram

```mermaid
flowchart TD
    Browser[Client Browser]
    FrontendServer[Next.js Dev / App Server]
    BackendServer[FastAPI / Uvicorn Server]
    FileStore[Local Models and Dataset]
    External[Open-Meteo Cloud API]

    Browser --> FrontendServer
    FrontendServer --> BackendServer
    BackendServer --> FileStore
    BackendServer --> External
```

## ER Diagram

```mermaid
erDiagram
    LOCATION ||--o{ FORECAST_REQUEST : uses
    FORECAST_REQUEST ||--|{ HOURLY_FORECAST : produces
    FORECAST_REQUEST ||--|{ DAILY_FORECAST : aggregates
    MODEL_METADATA ||--o{ FORECAST_REQUEST : informs
    SEED_HISTORY_RECORD ||--o{ HOURLY_FORECAST : seeds

    LOCATION {
      string name
      string country
      string admin1
      float latitude
      float longitude
      string timezone
    }

    FORECAST_REQUEST {
      string start_date
      int days
    }

    HOURLY_FORECAST {
      string timestamp
      float wind_speed
      float wind_direction
      float temperature
      float pressure
      float predicted_power
    }

    DAILY_FORECAST {
      string date
      float total_energy
      float average_power
      float peak_power
      string peak_time
    }

    MODEL_METADATA {
      string best_model
      int lookback_window
      int minimum_history_rows
    }

    SEED_HISTORY_RECORD {
      string timestamp
      float wind_speed
      float wind_direction
      float temperature
      float pressure
      float power_output
    }
```

## Forecast Flowchart

```mermaid
flowchart TD
    U[User] --> I[Input Location and Date]
    I --> W[Fetch Weather from Open-Meteo]
    W --> S[Load Seed History]
    S --> M[Run Saved Model]
    M --> R[Generate Hourly Prediction]
    R --> A[Aggregate Daily Forecast]
    A --> O[Display Output]
```
