import { useEffect, useState } from 'react';

import { useAuth } from '../auth/AuthContext.jsx';
import {
  getMockIotState,
  isMockIotMode,
  subscribeToMockIotState,
} from '../mocks/iotMockStore.js';

const timestampFormatter = new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'medium',
  timeStyle: 'medium',
});

const rackStateLabels = {
  extended: 'Đang phơi',
  retracted: 'Đã thu',
  error: 'Lỗi',
};

const resultLabels = {
  completed: 'Hoàn tất',
  failed: 'Thất bại',
  timeout: 'Timeout',
};

function formatTimestamp(value) {
  const timestamp = Number(value);
  return Number.isFinite(timestamp) && timestamp > 0
    ? timestampFormatter.format(new Date(timestamp))
    : '—';
}

export default function HistoryPage() {
  const { user } = useAuth();
  const deviceId = user?.device_id;
  const [mockState, setMockState] = useState(() => (
    getMockIotState(deviceId)
  ));

  useEffect(() => {
    if (!isMockIotMode || !deviceId) {
      return () => {};
    }

    return subscribeToMockIotState(deviceId, setMockState);
  }, [deviceId]);

  return (
    <section className="history-page" aria-labelledby="history-title">
      <header className="history-heading">
        <div>
          <p className="monitor-eyebrow">Nhật ký thiết bị</p>
          <h1 id="history-title">Lịch sử hoạt động</h1>
        </div>
        {isMockIotMode && (
          <span className="iot-mode-badge mock">MOCK MODE</span>
        )}
      </header>

      {!isMockIotMode ? (
        <div className="history-empty-state">
          <h2>Chưa có nguồn lịch sử tích hợp</h2>
          <p>
            Trang không gọi service frontend vì backend chưa cung cấp API
            lịch sử command/ACK.
          </p>
        </div>
      ) : (
        <>
          {mockState.history.length === 0 ? (
            <div className="history-empty-state">
              <h2>Chưa có lệnh nào</h2>
              <p>
                Lệnh hoàn tất, thất bại hoặc timeout từ Monitor Page sẽ xuất
                hiện tại đây.
              </p>
            </div>
          ) : (
            <ol className="command-history-list">
              {mockState.history.map((item) => (
                <li className="command-history-item" key={item.command_id}>
                  <span
                    className={`history-result ${item.status}`}
                  >
                    {resultLabels[item.status] || item.status}
                  </span>
                  <div className="history-command-copy">
                    <h2>{item.label}</h2>
                    <p>
                      {rackStateLabels[item.previous_state] || item.previous_state}
                      {' → '}
                      {rackStateLabels[item.final_state] || item.final_state}
                    </p>
                    {item.error && <p className="history-error">{item.error}</p>}
                  </div>
                  <time dateTime={new Date(item.completed_at).toISOString()}>
                    {formatTimestamp(item.completed_at)}
                  </time>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  );
}
