import { auth, isFirebaseConfigured } from '../firebase.js';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL
  || 'http://localhost:8000';
const RECONNECT_DELAY_MS = 3000;
const sensorDataCache = new Map();

export function getCachedSensorSnapshot() {
  const deviceId = auth?.currentUser?.uid;

  if (!deviceId || !sensorDataCache.has(deviceId)) {
    return {
      hasData: false,
      data: null,
    };
  }

  return {
    hasData: true,
    data: sensorDataCache.get(deviceId),
  };
}

function parseEventBlock(block) {
  let eventName = 'message';
  const dataLines = [];

  block.split('\n').forEach((line) => {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  });

  if (dataLines.length === 0) {
    return null;
  }

  return {
    eventName,
    data: JSON.parse(dataLines.join('\n')),
  };
}

async function readEventStream(response, onSensorData, onStreamError) {
  if (!response.body) {
    throw new Error('Trình duyệt không hỗ trợ nhận dữ liệu realtime.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    buffer = buffer.replaceAll('\r\n', '\n');

    let boundaryIndex = buffer.indexOf('\n\n');

    while (boundaryIndex !== -1) {
      const block = buffer.slice(0, boundaryIndex);
      buffer = buffer.slice(boundaryIndex + 2);

      const parsedEvent = parseEventBlock(block);

      if (parsedEvent?.eventName === 'sensor') {
        onSensorData(parsedEvent.data);
      } else if (parsedEvent?.eventName === 'error') {
        onStreamError(
          new Error(
            parsedEvent.data?.message
            || 'Không thể đọc dữ liệu cảm biến.',
          ),
        );
      }

      boundaryIndex = buffer.indexOf('\n\n');
    }
  }
}

function waitBeforeReconnect(signal) {
  return new Promise((resolve) => {
    const timeoutId = window.setTimeout(resolve, RECONNECT_DELAY_MS);

    signal.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timeoutId);
        resolve();
      },
      { once: true },
    );
  });
}

export function subscribeToSensorData({ onData, onError }) {
  const abortController = new AbortController();
  let stopped = false;

  async function connect() {
    while (!stopped) {
      try {
        if (!isFirebaseConfigured || !auth?.currentUser) {
          throw new Error('Phiên đăng nhập không còn hợp lệ.');
        }

        const idToken = await auth.currentUser.getIdToken();
        const response = await fetch(
          `${API_BASE_URL}/api/sensors/stream`,
          {
            headers: {
              Accept: 'text/event-stream',
              Authorization: `Bearer ${idToken}`,
            },
            signal: abortController.signal,
          },
        );

        if (response.status === 401 || response.status === 403) {
          throw new Error('Phiên đăng nhập đã hết hạn.');
        }

        if (!response.ok) {
          throw new Error('Không thể kết nối dữ liệu cảm biến.');
        }

        const deviceId = auth.currentUser.uid;

        await readEventStream(
          response,
          (data) => {
            sensorDataCache.set(deviceId, data);
            onData(data);
          },
          onError,
        );

        if (!stopped) {
          throw new Error('Kết nối realtime đã bị gián đoạn.');
        }
      } catch (error) {
        if (stopped || error?.name === 'AbortError') {
          return;
        }

        onError(
          error instanceof Error
            ? error
            : new Error('Không thể kết nối dữ liệu cảm biến.'),
        );
      }

      await waitBeforeReconnect(abortController.signal);
    }
  }

  connect();

  return () => {
    stopped = true;
    abortController.abort();
  };
}
