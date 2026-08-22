const timestampFormatter = new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'medium',
  timeStyle: 'medium',
});

const statusLabels = {
  failed: 'Thất bại',
  pending: 'Đã tiếp nhận',
};

function parseTimestamp(value) {
  if (typeof value === 'string' && value.trim()) {
    const timestamp = Date.parse(value);
    return Number.isFinite(timestamp) ? timestamp : Number.NaN;
  }

  const numericValue = Number(value);

  if (!Number.isFinite(numericValue) || numericValue <= 0) {
    return Number.NaN;
  }

  return numericValue < 1_000_000_000_000
    ? numericValue * 1000
    : numericValue;
}

function formatTimestamp(value) {
  const timestamp = parseTimestamp(value);
  return Number.isFinite(timestamp)
    ? timestampFormatter.format(new Date(timestamp))
    : '—';
}

function getTimestampAttribute(value) {
  const timestamp = parseTimestamp(value);
  return Number.isFinite(timestamp)
    ? new Date(timestamp).toISOString()
    : undefined;
}

function getActionLabel(item) {
  if (item?.command === 'open' || item?.action === 'extend') {
    return 'Phơi đồ';
  }

  if (item?.command === 'close' || item?.action === 'retract') {
    return 'Thu đồ';
  }

  return item?.action || item?.command || 'Lệnh thiết bị';
}

export default function ActivityHistoryList({ items }) {
  return (
    <ol className="command-history-list">
      {items.map((item) => {
        const status = item.status || 'pending';
        const timestamp = (
          item.updated_at
          || item.requested_at
        );

        return (
          <li className="command-history-item" key={item.command_id}>
            <span className={`history-result ${status}`}>
              {statusLabels[status] || status}
            </span>
            <div className="history-command-copy">
              <h2>{getActionLabel(item)}</h2>
              <p>
                Lệnh <code>{item.command || '—'}</code>
                {item.source ? ` · Nguồn: ${item.source}` : ''}
              </p>
              {item.error && (
                <p className="history-error">{item.error}</p>
              )}
            </div>
            <time dateTime={getTimestampAttribute(timestamp)}>
              {formatTimestamp(timestamp)}
            </time>
          </li>
        );
      })}
    </ol>
  );
}
