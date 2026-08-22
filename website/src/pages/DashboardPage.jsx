import { useEffect, useState } from 'react';

import { useAuth } from '../auth/AuthContext.jsx';
import { dashboardConfig } from '../config/dashboardConfig.js';
import {
  getRainForecast,
  subscribeToRackState,
} from '../services/dashboardStatusService.js';
import {
  getCachedSensorSnapshot,
  subscribeToSensorData,
} from '../services/sensorService.js';

const numberFormatter = new Intl.NumberFormat('vi-VN', {
  maximumFractionDigits: 1,
});

const integerFormatter = new Intl.NumberFormat('vi-VN', {
  maximumFractionDigits: 0,
});

const timestampFormatter = new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'medium',
  timeStyle: 'medium',
});

function formatNumber(value, formatter = numberFormatter) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue)
    ? formatter.format(numericValue)
    : '—';
}

function getTimestampMilliseconds(timestamp) {
  const numericTimestamp = Number(timestamp);

  if (!Number.isFinite(numericTimestamp) || numericTimestamp <= 0) {
    return Number.NaN;
  }

  return numericTimestamp >= 1_000_000_000_000
    ? numericTimestamp
    : numericTimestamp * 1000;
}

function formatTimestamp(timestamp) {
  const timestampMilliseconds = getTimestampMilliseconds(timestamp);

  return Number.isFinite(timestampMilliseconds)
    ? timestampFormatter.format(new Date(timestampMilliseconds))
    : 'Chưa có dữ liệu';
}

function getTimestampAttribute(timestamp) {
  const timestampMilliseconds = getTimestampMilliseconds(timestamp);

  if (!Number.isFinite(timestampMilliseconds)) {
    return undefined;
  }

  return new Date(timestampMilliseconds).toISOString();
}

function getRainLabel(value) {
  if (value === true) {
    return 'Có mưa';
  }

  if (value === false) {
    return 'Không mưa';
  }

  return 'Chưa có dữ liệu';
}

function getRainForecastStatus(items, error) {
  if (error) {
    return {
      tone: 'unknown',
      label: 'CHƯA XÁC ĐỊNH',
      detail: error,
    };
  }

  if (items === null) {
    return {
      tone: 'unknown',
      label: 'CHƯA XÁC ĐỊNH',
      detail: 'Đang tải dữ liệu dự báo…',
    };
  }

  const forecastWindowMinutes =
    dashboardConfig.rainForecastWindowHours * 60;
  const relevantProbabilities = items
    .filter((item) => {
      const minutes = Number(item?.forecast_within_minutes);
      return (
        Number.isFinite(minutes)
        && minutes >= 0
        && minutes <= forecastWindowMinutes
      );
    })
    .map((item) => item?.rain_probability_percent)
    .filter((probability) => (
      probability !== null
      && probability !== undefined
      && probability !== ''
    ))
    .map(Number)
    .filter(Number.isFinite);

  if (relevantProbabilities.length === 0) {
    return {
      tone: 'unknown',
      label: 'CHƯA XÁC ĐỊNH',
      detail: 'Chưa có dữ liệu dự báo hợp lệ trong khung thời gian theo dõi.',
    };
  }

  const highestProbability = Math.max(...relevantProbabilities);
  const formattedProbability = integerFormatter.format(highestProbability);

  if (highestProbability >= dashboardConfig.rainWarningThresholdPercent) {
    return {
      tone: 'danger',
      label: 'CẢNH BÁO SẮP MƯA',
      detail: `${formattedProbability}%`,
    };
  }
  return {
    tone: 'success',
    label: 'KHÔNG MƯA',
    detail: `${formattedProbability}%`,
  };
}

function getRackStatus(data, hasReceivedData, error) {
  if (error) {
    return {
      tone: 'unknown',
      label: 'CHƯA XÁC ĐỊNH',
      detail: error,
    };
  }

  const states = {
    extended: {
      tone: 'success',
      label: 'YÊU CẦU PHƠI',
    },
    retracted: {
      tone: 'danger',
      label: 'YÊU CẦU THU',
    },
    error: {
      tone: 'error',
      label: 'LỖI',
    },
  };
  const status = states[data?.rack_state];

  if (!status) {
    return {
      tone: 'unknown',
      label: 'CHƯA XÁC ĐỊNH',
      detail: hasReceivedData
        ? 'Chưa có trạng thái hợp lệ từ giàn phơi.'
        : 'Đang đọc trạng thái giàn phơi…',
    };
  }

  return {
    ...status,
    detail: `Cập nhật gần nhất: ${formatTimestamp(data.updated_at)}.`,
  };
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [initialSnapshot] = useState(getCachedSensorSnapshot);
  const [sensorData, setSensorData] = useState(initialSnapshot.data);
  const [hasReceivedData, setHasReceivedData] = useState(
    initialSnapshot.hasData,
  );
  const [isLive, setIsLive] = useState(false);
  const [connectionError, setConnectionError] = useState('');
  const [forecastItems, setForecastItems] = useState(null);
  const [forecastError, setForecastError] = useState('');
  const [rackData, setRackData] = useState(null);
  const [hasReceivedRackData, setHasReceivedRackData] = useState(false);
  const [rackError, setRackError] = useState('');

  useEffect(() => subscribeToSensorData({
    onData(data) {
      setSensorData(data);
      setHasReceivedData(true);
      setIsLive(true);
      setConnectionError('');
    },
    onError(error) {
      setIsLive(false);
      setConnectionError(error.message);
    },
  }), []);

  useEffect(() => {
    const abortController = new AbortController();

    getRainForecast({ signal: abortController.signal })
      .then((items) => {
        setForecastItems(items);
        setForecastError('');
      })
      .catch((error) => {
        if (error?.name !== 'AbortError') {
          setForecastError(
            error?.message || 'Không thể tải dữ liệu dự báo mưa.',
          );
        }
      });

    const unsubscribeFromRackState = subscribeToRackState({
      onData(data) {
        setRackData(data);
        setHasReceivedRackData(true);
        setRackError('');
      },
      onError(error) {
        setRackError(
          error?.message || 'Không thể đọc trạng thái giàn phơi.',
        );
      },
    });

    return () => {
      abortController.abort();
      unsubscribeFromRackState();
    };
  }, [user?.device_id]);

  const connectionLabel = connectionError
    ? 'Mất kết nối'
    : isLive
      ? 'Đang cập nhật trực tiếp'
      : 'Đang kết nối…';
  const rainForecastStatus = getRainForecastStatus(
    forecastItems,
    forecastError,
  );
  const rackStatus = getRackStatus(
    rackData,
    hasReceivedRackData,
    rackError,
  );

  return (
    <section className="dashboard-page" aria-labelledby="dashboard-title">
      <header className="dashboard-heading">
        <p className="dashboard-eyebrow">Tổng quan hệ thống</p>
        <h1 id="dashboard-title">Dashboard</h1>
      </header>

      <article className="sensor-card" aria-labelledby="sensor-card-title">
        <header className="sensor-card-header">
          <div className="sensor-title-group">
            <span className="card-number" aria-hidden="true">01</span>
            <div>
              <p className="card-kicker">Thiết bị hiện tại</p>
              <h2 id="sensor-card-title">Dự đoán thời tiết</h2>
            </div>
          </div>

          <p
            className={`connection-status${connectionError ? ' error' : ''}`}
            role="status"
          >
            <span className="connection-dot" aria-hidden="true" />
            {connectionLabel}
          </p>
        </header>

        <dl className="sensor-metrics">
          <div className="sensor-metric">
            <dt>Độ ẩm</dt>
            <dd>
              {formatNumber(sensorData?.humidity_percent)}
              <span className="metric-unit">%</span>
            </dd>
          </div>

          <div className="sensor-metric">
            <dt>Nhiệt độ</dt>
            <dd>
              {formatNumber(sensorData?.temperature_celsius)}
              <span className="metric-unit">°C</span>
            </dd>
          </div>

          <div className="sensor-metric">
            <dt>Cảm biến mưa</dt>
            <dd className="rain-value">
              <span
                className={`rain-badge${sensorData?.rain_detected === true ? ' raining' : ''}`}
              >
                {getRainLabel(sensorData?.rain_detected)}
              </span>
            </dd>
          </div>

          <div className="sensor-metric">
            <dt>Cường độ ánh sáng</dt>
            <dd>
              {formatNumber(sensorData?.light_lux, integerFormatter)}
              <span className="metric-unit">lux</span>
            </dd>
          </div>
        </dl>

        <footer className="sensor-card-footer">
          <span>Thời điểm nhận dữ liệu cảm biến gần nhất</span>
          <time dateTime={getTimestampAttribute(sensorData?.received_at)}>
            {formatTimestamp(sensorData?.received_at)}
          </time>
        </footer>

        {hasReceivedData && sensorData === null && (
          <p className="sensor-empty-state" role="status">
            Thiết bị chưa gửi dữ liệu cảm biến.
          </p>
        )}

        {connectionError && (
          <p className="sensor-error" role="alert">
            {connectionError} Hệ thống đang thử kết nối lại…
          </p>
        )}
      </article>

      <article className="status-card" aria-labelledby="status-card-title">
        <header className="status-card-header">
          <div className="status-title-group">
            <span className="status-card-number" aria-hidden="true">02</span>
            <div>
              <p className="status-card-kicker">Theo dõi vận hành</p>
              <h2 id="status-card-title">Trạng thái hệ thống</h2>
            </div>
          </div>
        </header>

        <div className="status-grid">
          <section
            className={`status-item ${rainForecastStatus.tone}`}
            aria-labelledby="rain-forecast-title"
          >
            <div className="status-item-heading">
              <span className="status-indicator" aria-hidden="true" />
              <h3 id="rain-forecast-title">Dự báo mưa</h3>
            </div>
            <p className="status-value" role="status" aria-live="polite">
              {rainForecastStatus.label}
            </p>
            <p className="status-detail">{rainForecastStatus.detail}</p>
          </section>

          <section
            className={`status-item ${rackStatus.tone}`}
            aria-labelledby="rack-status-title"
          >
            <div className="status-item-heading">
              <span className="status-indicator" aria-hidden="true" />
              <h3 id="rack-status-title">Trạng thái giàn phơi</h3>
            </div>
            <p className="status-value" role="status" aria-live="polite">
              {rackStatus.label}
            </p>
            <p className="status-detail">{rackStatus.detail}</p>
          </section>
        </div>

      </article>
    </section>
  );
}
