import { useEffect, useState } from 'react';

import ActivityHistoryList from '../components/ActivityHistoryList.jsx';
import { getCommandHistory } from '../services/deviceControlService.js';

const HISTORY_POLL_INTERVAL_MS = 5000;

export default function HistoryPage() {
  const [items, setItems] = useState([]);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [historyError, setHistoryError] = useState('');

  useEffect(() => {
    const abortController = new AbortController();
    let timeoutId = null;
    let stopped = false;

    async function pollHistory() {
      try {
        const historyItems = await getCommandHistory({
          limit: 50,
          signal: abortController.signal,
        });

        if (!stopped) {
          setItems(historyItems);
          setHasLoaded(true);
          setHistoryError('');
        }
      } catch (error) {
        if (!stopped && error?.name !== 'AbortError') {
          setHasLoaded(true);
          setHistoryError(
            error?.message || 'Không thể tải lịch sử hoạt động.',
          );
        }
      }

      if (!stopped) {
        timeoutId = window.setTimeout(
          pollHistory,
          HISTORY_POLL_INTERVAL_MS,
        );
      }
    }

    pollHistory();

    return () => {
      stopped = true;
      abortController.abort();

      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, []);

  return (
    <section className="history-page" aria-labelledby="history-title">
      <header className="history-heading">
        <div>
          <p className="monitor-eyebrow">Nhật ký thiết bị</p>
          <h1 id="history-title">Lịch sử hoạt động</h1>
        </div>
        <span className="iot-mode-badge live">LIVE MODE</span>
      </header>

      {historyError && (
        <p className="monitor-alert error" role="alert">
          {historyError} Hệ thống sẽ tự thử lại.
        </p>
      )}

      {!hasLoaded ? (
        <div className="history-empty-state" role="status">
          <h2>Đang tải lịch sử…</h2>
          <p>Đang đọc nhật ký lệnh đã lưu trên backend.</p>
        </div>
      ) : items.length === 0 ? (
        <div className="history-empty-state">
          <h2>Chưa có lệnh nào</h2>
          <p>
            Lệnh Phơi đồ hoặc Thu đồ gửi từ trang Điều khiển sẽ xuất hiện
            tại đây sau khi backend ghi nhận.
          </p>
        </div>
      ) : (
        <ActivityHistoryList items={items} />
      )}
    </section>
  );
}
