import { useEffect, useRef, useState } from 'react';

import { useAuth } from '../auth/AuthContext.jsx';
import {
  getDeviceConfig,
  getDeviceStatus,
  getRackState,
  sendRackCommand,
  updateDeviceConfig,
} from '../services/deviceControlService.js';

const LIVE_POLL_INTERVAL_MS = 2000;

const timestampFormatter = new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'medium',
  timeStyle: 'medium',
});

const rackStateLabels = {
  error: 'Lỗi',
  extended: 'Yêu cầu phơi',
  retracted: 'Yêu cầu thu',
};

function formatEpochSeconds(value) {
  const timestamp = Number(value);

  if (!Number.isFinite(timestamp) || timestamp <= 0) {
    return 'Chưa có dữ liệu'; 
  }

  return timestampFormatter.format(new Date(timestamp * 1000));
}

function formatDurationSeconds(value) {
  const seconds = Number(value);

  if (!Number.isFinite(seconds) || seconds < 0) {
    return '—';
  }

  return `${Math.round(seconds * 10) / 10}s`;
}

function getCommandLabel(command) {
  return command === 'open' ? 'Phơi đồ' : 'Thu đồ';
}

export default function MonitorPage() {
  const { user } = useAuth();
  const deviceId = user?.device_id;
  const [deviceStatus, setDeviceStatus] = useState(null);
  const [hasCheckedStatus, setHasCheckedStatus] = useState(false);
  const [livePollingStopped, setLivePollingStopped] = useState(false);
  const [statusError, setStatusError] = useState('');
  const [rackData, setRackData] = useState(null);
  const [rackError, setRackError] = useState('');
  const [deviceConfig, setDeviceConfig] = useState(null);
  const [configError, setConfigError] = useState('');
  const [modeUpdating, setModeUpdating] = useState(false);
  const [modeFeedback, setModeFeedback] = useState('');
  const [pendingCommand, setPendingCommand] = useState(null);
  const [commandFeedback, setCommandFeedback] = useState(null);
  const commandAbortControllerRef = useRef(null);
  const pendingCommandRef = useRef(null);
  const modeUpdateRef = useRef(false);

  useEffect(() => {
    const abortController = new AbortController();
    let timeoutId = null;
    let stopped = false;

    setDeviceStatus(null);
    setHasCheckedStatus(false);
    setLivePollingStopped(false);
    setStatusError('');
    setRackData(null);
    setRackError('');
    setDeviceConfig(null);
    setConfigError('');

    if (!deviceId) {
      setStatusError('Không xác định được Device ID.');
      setRackError('Không xác định được Device ID.');
      setConfigError('Không xác định được Device ID.');
      setHasCheckedStatus(true);
      return () => abortController.abort();
    }

    async function pollLiveState() {
      let shouldPollAgain = true;
      const [statusResult, rackResult, configResult] = (
        await Promise.allSettled([
          getDeviceStatus({ signal: abortController.signal }),
          getRackState({ signal: abortController.signal }),
          getDeviceConfig({ signal: abortController.signal }),
        ])
      );

      if (stopped) {
        return;
      }

      setHasCheckedStatus(true);

      if (statusResult.status === 'fulfilled') {
        const nextStatus = statusResult.value;
        const staleSeconds = Number(nextStatus?.stale_for_seconds);
        const timeoutSeconds = Number(nextStatus?.timeout_seconds);
        const exceededOfflineThreshold = (
          nextStatus?.status === 'offline'
          && (
            nextStatus?.sensor_timestamp == null
            || (
              Number.isFinite(staleSeconds)
              && Number.isFinite(timeoutSeconds)
              && staleSeconds >= timeoutSeconds
            )
          )
        );

        setDeviceStatus(nextStatus);
        setStatusError('');

        if (exceededOfflineThreshold) {
          shouldPollAgain = false;
          setLivePollingStopped(true);
        }
      } else if (statusResult.reason?.name !== 'AbortError') {
        setStatusError(
          statusResult.reason?.message
          || 'Không thể đọc trạng thái kết nối ESP32.',
        );
      }

      if (rackResult.status === 'fulfilled') {
        setRackData(rackResult.value);
        setRackError('');
      } else if (rackResult.reason?.name !== 'AbortError') {
        setRackError(
          rackResult.reason?.message
          || 'Không thể đọc trạng thái giàn phơi.',
        );
      }

      if (configResult.status === 'fulfilled') {
        setDeviceConfig(configResult.value);
        setConfigError('');
      } else if (configResult.reason?.name !== 'AbortError') {
        setConfigError(
          configResult.reason?.message
          || 'Không thể đọc chế độ vận hành.',
        );
      }

      if (shouldPollAgain) {
        timeoutId = window.setTimeout(
          pollLiveState,
          LIVE_POLL_INTERVAL_MS,
        );
      }
    }

    pollLiveState();

    return () => {
      stopped = true;
      abortController.abort();

      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [deviceId]);

  useEffect(() => () => {
    commandAbortControllerRef.current?.abort();
  }, []);

  const isOnline = !statusError && deviceStatus?.online === true;
  const connectionState = !hasCheckedStatus
    ? 'checking'
    : statusError
      ? 'unknown'
      : deviceStatus?.status === 'checking'
        ? 'checking'
      : isOnline
        ? 'online'
        : 'offline';
  const connectionLabel = {
    checking: 'Đang kiểm tra',
    offline: 'Mất kết nối',
    online: 'Đã kết nối',
    unknown: 'Chưa xác định',
  }[connectionState];
  const mode = deviceConfig?.mode || rackData?.mode || null;
  const rackState = rackData?.rack_state || null;
  const controlsDisabled = (
    !isOnline
    || pendingCommand !== null
    || modeUpdating
  );

  async function handleModeToggle() {
    if (
      (mode !== 'auto' && mode !== 'manual')
      || modeUpdateRef.current
      || pendingCommandRef.current
    ) {
      return;
    }

    const nextMode = mode === 'auto' ? 'manual' : 'auto';
    modeUpdateRef.current = true;
    setModeUpdating(true);
    setModeFeedback('');
    setConfigError('');

    try {
      const updatedConfig = await updateDeviceConfig(nextMode);
      setDeviceConfig(updatedConfig);
      setRackData((current) => (
        current ? { ...current, mode: updatedConfig.mode } : current
      ));
      setModeFeedback(
        nextMode === 'auto'
          ? 'Đã bật chế độ tự động.'
          : 'Đã chuyển sang điều khiển thủ công.',
      );
    } catch (error) {
      setConfigError(
        error?.message || 'Không thể cập nhật chế độ vận hành.',
      );
    } finally {
      modeUpdateRef.current = false;
      setModeUpdating(false);
    }
  }

  async function handleCommand(command) {
    if (
      controlsDisabled
      || pendingCommandRef.current
      || !deviceId
    ) {
      return;
    }

    const pending = { command };
    const abortController = new AbortController();
    commandAbortControllerRef.current = abortController;
    pendingCommandRef.current = pending;
    setPendingCommand(pending);
    setCommandFeedback({
      message: `Đang gửi lệnh ${getCommandLabel(command)}…`,
      phase: 'pending',
    });

    try {
      const acceptedCommand = await sendRackCommand(command, {
        signal: abortController.signal,
      });

      setDeviceConfig((current) => ({
        ...current,
        device_id: acceptedCommand.device_id,
        mode: acceptedCommand.mode,
      }));
      setRackData((current) => (
        current ? { ...current, mode: acceptedCommand.mode } : current
      ));
      setCommandFeedback({
        message: `Đã gửi yêu cầu ${getCommandLabel(command)}.`,
        phase: 'accepted',
      });
    } catch (error) {
      if (error?.name !== 'AbortError') {
        setCommandFeedback({
          message: error?.message || 'Không thể gửi lệnh tới giàn phơi.',
          phase: 'failed',
        });
      }
    } finally {
      commandAbortControllerRef.current = null;
      pendingCommandRef.current = null;
      setPendingCommand(null);
    }
  }

  return (
    <section className="monitor-page" aria-labelledby="monitor-title">
      <header className="monitor-heading">
        <div>
          <p className="monitor-eyebrow">ESP32 / Wokwi</p>
          <h1 id="monitor-title">Điều khiển giàn phơi</h1>
        </div>
        <span className="iot-mode-badge live">LIVE MODE</span>
      </header>

      <article
        className={`device-connection-card ${connectionState}`}
        aria-labelledby="device-connection-title"
      >
        <div className="device-connection-copy">
          <p className="monitor-card-kicker">Trạng thái kết nối ESP32</p>
          <h2 id="device-connection-title">{connectionLabel}</h2>
          <p className="heartbeat-detail">
            {deviceStatus?.sensor_timestamp == null
              ? 'Chưa nhận được heartbeat từ Wokwi.'
              : `Wokwi uptime: ${deviceStatus.sensor_timestamp} giây.`}
          </p>
        </div>

        <span className={`device-status-badge ${connectionState}`} role="status">
          <span aria-hidden="true" />
          {deviceStatus?.status || connectionState}
        </span>

        <dl className="device-metadata">
          <div>
            <dt>Device ID</dt>
            <dd>{deviceStatus?.device_id || deviceId || '—'}</dd>
          </div>
          <div>
            <dt>Heartbeat đổi lần cuối</dt>
            <dd>
              {formatEpochSeconds(deviceStatus?.last_change_observed_at)}
            </dd>
          </div>
          <div>
            <dt>Độ trễ / Ngưỡng offline</dt>
            <dd>
              {formatDurationSeconds(deviceStatus?.stale_for_seconds)}
              {' / '}
              {formatDurationSeconds(deviceStatus?.timeout_seconds)}
            </dd>
          </div>
        </dl>

        {statusError && (
          <p className="monitor-alert error" role="alert">
            {statusError} Hệ thống sẽ tự thử lại.
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

        <div className="rack-live-summary">
          <div>
            <span>Trạng thái yêu cầu trên Firebase</span>
            <strong className={`rack-state-value ${rackState || 'unknown'}`}>
              {rackStateLabels[rackState] || 'Chưa có dữ liệu'}
            </strong>
            <small>
              Cập nhật: {formatEpochSeconds(rackData?.updated_at)}
            </small>
          </div>

          <div className="operating-mode-control">
            <span>Chế độ vận hành</span>
            <button
              type="button"
              className="connection-switch"
              role="switch"
              aria-checked={mode === 'auto'}
              aria-label="Chuyển chế độ tự động hoặc thủ công"
              disabled={
                (mode !== 'auto' && mode !== 'manual')
                || modeUpdating
                || pendingCommand !== null
              }
              onClick={handleModeToggle}
            >
              <span className="switch-track" aria-hidden="true">
                <span className="switch-thumb" />
              </span>
              <span>
                {modeUpdating
                  ? 'Đang cập nhật…'
                  : mode === 'auto'
                    ? 'Tự động'
                    : mode === 'manual'
                      ? 'Thủ công'
                      : 'Chưa xác định'}
              </span>
            </button>
            <small>Lệnh từ web luôn chuyển thiết bị sang thủ công.</small>
          </div>
        </div>

        {rackError && (
          <p className="monitor-alert error" role="alert">
            {rackError} Hệ thống sẽ tự thử lại.
          </p>
        )}

        {configError && (
          <p className="monitor-alert error" role="alert">
            {configError} Hệ thống sẽ tự thử lại.
          </p>
        )}

        {modeFeedback && !configError && (
          <p className="command-feedback accepted" role="status">
            {modeFeedback}
          </p>
        )}

        <div className="rack-command-grid">
          <button
            type="button"
            className="rack-command-button extend"
            disabled={controlsDisabled}
            onClick={() => handleCommand('open')}
          >
            <span className="command-icon" aria-hidden="true">↗</span>
            <span>
              <strong>Phơi đồ</strong>
              <small>Gửi command: open</small>
            </span>
          </button>

          <button
            type="button"
            className="rack-command-button retract"
            disabled={controlsDisabled}
            onClick={() => handleCommand('close')}
          >
            <span className="command-icon" aria-hidden="true">↙</span>
            <span>
              <strong>Thu đồ</strong>
              <small>Gửi command: close</small>
            </span>
          </button>
        </div>

        {livePollingStopped ? (
          <p className="monitor-alert error" role="status">
            Heartbeat đã vượt ngưỡng offline. Hệ thống đã dừng kiểm tra
            LIVE; tải lại trang để bắt đầu kiểm tra lại.
          </p>
        ) : !isOnline && hasCheckedStatus && (
          <p className="monitor-alert error" role="status">
            ESP32 đang offline hoặc còn trong giai đoạn kiểm tra heartbeat.
            Tạm thời không thể gửi lệnh.
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
