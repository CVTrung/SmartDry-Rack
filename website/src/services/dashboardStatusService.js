import { dashboardConfig } from '../config/dashboardConfig.js';
import {
  auth,
  isFirebaseConfigured,
} from '../firebase.js';
import { getRackState } from './deviceControlService.js';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL
  || 'http://localhost:8000';
const RACK_STATE_POLL_INTERVAL_MS = 3000;

function assertAuthenticated() {
  if (
    !isFirebaseConfigured
    || !auth?.currentUser
  ) {
    throw new Error('Phiên đăng nhập không còn hợp lệ.');
  }
}

export async function getRainForecast({ signal } = {}) {
  assertAuthenticated();

  const idToken = await auth.currentUser.getIdToken();
  const searchParams = new URLSearchParams({
    hours: String(dashboardConfig.rainForecastWindowHours),
  });
  const response = await fetch(
    `${API_BASE_URL}/api/weather/forecast?${searchParams}`,
    {
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${idToken}`,
      },
      signal,
    },
  );

  if (response.status === 401 || response.status === 403) {
    throw new Error('Phiên đăng nhập đã hết hạn.');
  }

  if (!response.ok) {
    throw new Error('Không thể tải dữ liệu dự báo mưa.');
  }

  const data = await response.json();

  if (!Array.isArray(data?.items)) {
    throw new Error('Dữ liệu dự báo mưa không hợp lệ.');
  }

  return data.items;
}

export function subscribeToRackState({ onData, onError }) {
  const abortController = new AbortController();
  let timeoutId = null;
  let stopped = false;

  async function poll() {
    try {
      const data = await getRackState({
        signal: abortController.signal,
      });

      if (!stopped) {
        onData(data);
      }
    } catch (error) {
      if (!stopped && error?.name !== 'AbortError') {
        onError(
          error instanceof Error
            ? error
            : new Error('Không thể đọc trạng thái giàn phơi.'),
        );
      }
    }

    if (!stopped) {
      timeoutId = window.setTimeout(
        poll,
        RACK_STATE_POLL_INTERVAL_MS,
      );
    }
  }

  poll();

  return () => {
    stopped = true;
    abortController.abort();

    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
    }
  };
}
