import { useEffect, useMemo, useRef, useState } from 'react';

import { useAuth } from '../auth/AuthContext.jsx';
import {
  getMockCommand,
  getMockSimulation,
  isMockIotMode,
  recordMockCommandResult,
  refreshMockHeartbeat,
  setMockDeviceOnline,
  subscribeToMockIotState,
} from '../mocks/iotMockStore.js';

const ONLINE_THRESHOLD_MS = 30_000;
const HEARTBEAT_INTERVAL_MS = 10_000;

const timestampFormatter = new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'medium',
  timeStyle: 'medium',
});

function formatTimestamp(value) {
  const timestamp = Number(value);

  if (!Number.isFinite(timestamp) || timestamp <= 0) {
    return 'Chưa có heartbeat';
  }

  return timestampFormatter.format(new Date(timestamp));
}

function getRandomDelay({ ack_delay_min_ms: min, ack_delay_max_ms: max }) {
  return Math.round(min + (Math.random() * (max - min)));
}

export default function MonitorPage() {
  const { user } = useAuth();
  const deviceId = user?.device_id;
  const [deviceStatus, setDeviceStatus] = useState(null);
  const [hasCheckedStatus, setHasCheckedStatus] = useState(false);
  const [statusError, setStatusError] = useState('');
  const [now, setNow] = useState(Date.now());
  const [pendingCommand, setPendingCommand] = useState(null);
  const [commandFeedback, setCommandFeedback] = useState(null);
  const [nextOutcome, setNextOutcome] = useState('success');
  const commandTimerRef = useRef(null);
  const pendingCommandRef = useRef(null);

  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(clock);
  }, []);

  useEffect(() => {
    setDeviceStatus(null);
    setHasCheckedStatus(false);
    setStatusError('');

    if (!deviceId) {
      setStatusError('Không xác định được Device ID.');
      setHasCheckedStatus(true);
      return () => {};
    }

    if (isMockIotMode) {
      const unsubscribe = subscribeToMockIotState(
        deviceId,
        (state) => {
          setDeviceStatus(state.deviceStatus);
          setHasCheckedStatus(true);
          setStatusError('');
        },
      );
      refreshMockHeartbeat(deviceId);
      const heartbeat = window.setInterval(
        () => refreshMockHeartbeat(deviceId),
        HEARTBEAT_INTERVAL_MS,
      );

      return () => {
        unsubscribe();
        window.clearInterval(heartbeat);
      };
    }

    setStatusError(
      'Backend chưa cung cấp API trạng thái kết nối ESP32.',
    );
    setHasCheckedStatus(true);
    return () => {};
  }, [deviceId]);

  useEffect(() => () => {
    if (commandTimerRef.current !== null) {
      window.clearTimeout(commandTimerRef.current);
    }
  }, []);

  const lastSeenValue = deviceStatus?.last_seen;
  const lastSeen = lastSeenValue === undefined
    || lastSeenValue === null
    || lastSeenValue === ''
    ? Number.NaN
    : Number(lastSeenValue);
  const heartbeatAge = Number.isFinite(lastSeen)
    ? now - lastSeen
    : Number.POSITIVE_INFINITY;
  const isOnline = hasCheckedStatus
    && !statusError
    && heartbeatAge <= ONLINE_THRESHOLD_MS;
  const connectionState = !hasCheckedStatus
    ? 'checking'
    : isOnline
      ? 'online'
      : 'offline';
  const connectionLabel = {
    checking: 'Đang kiểm tra',
    online: 'Đã kết nối',
    offline: 'Mất kết nối',
  }[connectionState];
  const heartbeatDetail = useMemo(() => {
    if (!Number.isFinite(lastSeen)) {
      return 'Thiết bị chưa gửi heartbeat.';
    }

    const secondsAgo = Math.max(0, Math.floor(heartbeatAge / 1000));
    return `${formatTimestamp(lastSeen)} · ${secondsAgo} giây trước`;
  }, [heartbeatAge, lastSeen]);
  const controlsDisabled = !isMockIotMode
    || !isOnline
    || pendingCommand !== null;

  function handleConnectionToggle() {
    if (!isMockIotMode || pendingCommandRef.current || !deviceId) {
      return;
    }

    setMockDeviceOnline(deviceId, !isOnline);
    setCommandFeedback(null);
  }

  function finishCommand({ action, requestedAt, status, error = '' }) {
    recordMockCommandResult({
      action,
      deviceId,
      error,
      requestedAt,
      status,
    });
    pendingCommandRef.current = null;
    setPendingCommand(null);

    if (status === 'completed') {
      setCommandFeedback({
        phase: 'completed',
        message: getMockCommand(action).completed_label,
      });
      return;
    }

    setCommandFeedback({
      phase: 'failed',
      message: error,
    });
  }

  function handleCommand(action) {
    if (
      !isMockIotMode
      || !isOnline
      || pendingCommandRef.current
      || !deviceId
    ) {
      return;
    }

    const command = getMockCommand(action);
    const simulation = getMockSimulation();
    const requestedAt = Date.now();
    const pending = { action, requestedAt };
    pendingCommandRef.current = pending;
    setPendingCommand(pending);
    setCommandFeedback({
      phase: 'pending',
      message: command.pending_label,
    });

    if (nextOutcome === 'timeout') {
      commandTimerRef.current = window.setTimeout(() => {
        finishCommand({
          action,
          requestedAt,
          status: 'timeout',
          error: 'Thiết bị không phản hồi ACK trong 12 giây.',
        });
      }, simulation.command_timeout_ms);
      return;
    }

    commandTimerRef.current = window.setTimeout(() => {
      if (nextOutcome === 'failure') {
        finishCommand({
          action,
          requestedAt,
          status: 'failed',
          error: 'Thiết bị từ chối lệnh mô phỏng.',
        });
        return;
      }

      finishCommand({
        action,
        requestedAt,
        status: 'completed',
      });
    }, getRandomDelay(simulation));
  }

  return (
    <section className="monitor-page" aria-labelledby="monitor-title">
      <header className="monitor-heading">
        <div>
          <p className="monitor-eyebrow">ESP32 / Wokwi</p>
          <h1 id="monitor-title">Monitor Page</h1>
        </div>
        <span className={`iot-mode-badge ${isMockIotMode ? 'mock' : 'live'}`}>
          {isMockIotMode ? 'MOCK MODE' : 'LIVE MODE'}
        </span>
      </header>

      <article
        className={`device-connection-card ${connectionState}`}
        aria-labelledby="device-connection-title"
      >
        <div className="device-connection-copy">
          <p className="monitor-card-kicker">Trạng thái kết nối ESP32</p>
          <h2 id="device-connection-title">{connectionLabel}</h2>
          <p className="heartbeat-detail">Heartbeat: {heartbeatDetail}</p>
        </div>

        <button
          type="button"
          className="connection-switch"
          role="switch"
          aria-checked={isOnline}
          aria-label="Trạng thái kết nối thiết bị"
          aria-readonly={!isMockIotMode}
          disabled={!isMockIotMode || pendingCommand !== null}
          onClick={handleConnectionToggle}
        >
          <span className="switch-track" aria-hidden="true">
            <span className="switch-thumb" />
          </span>
          <span>{isOnline ? 'Bật' : 'Tắt'}</span>
        </button>

        <dl className="device-metadata">
          <div>
            <dt>Device ID</dt>
            <dd>{deviceId || '—'}</dd>
          </div>
          <div>
            <dt>Simulator</dt>
            <dd>{deviceStatus?.simulator || '—'}</dd>
          </div>
          <div>
            <dt>Firmware</dt>
            <dd>{deviceStatus?.firmware_version || '—'}</dd>
          </div>
        </dl>

        {!isMockIotMode && (
          <p className="read-only-note">
            Switch chỉ phản ánh heartbeat và được khóa trong Live Mode.
          </p>
        )}

        {statusError && (
          <p className="monitor-alert error" role="alert">
            {statusError}
          </p>
        )}
      </article>

      <article className="rack-control-card" aria-labelledby="rack-control-title">
        <header className="rack-control-header">
          <div>
            <p className="monitor-card-kicker">Điều khiển giàn phơi</p>
            <h2 id="rack-control-title">Gửi lệnh tới thiết bị</h2>
          </div>
          {pendingCommand && (
            <span className="pending-badge">
              <span className="pending-spinner" aria-hidden="true" />
              Đang gửi
            </span>
          )}
        </header>

        {isMockIotMode && (
          <label className="mock-outcome-control">
            Kết quả lệnh tiếp theo
            <select
              value={nextOutcome}
              disabled={pendingCommand !== null}
              onChange={(event) => setNextOutcome(event.target.value)}
            >
              <option value="success">Thành công</option>
              <option value="failure">Thất bại</option>
              <option value="timeout">Timeout (12 giây)</option>
            </select>
          </label>
        )}

        <div className="rack-command-grid">
          <button
            type="button"
            className="rack-command-button extend"
            disabled={controlsDisabled}
            onClick={() => handleCommand('extend')}
          >
            <span className="command-icon" aria-hidden="true">↗</span>
            <span>
              <strong>Phơi đồ</strong>
            </span>
          </button>

          <button
            type="button"
            className="rack-command-button retract"
            disabled={controlsDisabled}
            onClick={() => handleCommand('retract')}
          >
            <span className="command-icon" aria-hidden="true">↙</span>
            <span>
              <strong>Thu đồ</strong>
            </span>
          </button>
        </div>

        {!isMockIotMode && (
          <p className="monitor-alert info" role="status">
            Hai lệnh đang được khóa vì backend chưa có command/ACK endpoint.
            Chuyển sang <code>VITE_IOT_MODE=mock</code> để chạy MVP mock.
          </p>
        )}

        {isMockIotMode && !isOnline && (
          <p className="monitor-alert error" role="status">
            Thiết bị đang offline. Không thể gửi lệnh.
          </p>
        )}

        {commandFeedback && (
          <p
            className={`command-feedback ${commandFeedback.phase}`}
            role={commandFeedback.phase === 'failed' ? 'alert' : 'status'}
            aria-live="polite"
          >
            {commandFeedback.message}
          </p>
        )}
      </article>
    </section>
  );
}
