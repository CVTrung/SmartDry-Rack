import { auth, isFirebaseConfigured } from '../firebase.js';

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL
  || 'http://localhost:8000'
).replace(/\/$/, '');

async function getErrorMessage(response, fallbackMessage) {
  try {
    const payload = await response.json();
    const detail = payload?.detail;

    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }

    if (typeof payload?.message === 'string' && payload.message.trim()) {
      return payload.message;
    }
  } catch {
    // The status code and the caller-specific fallback remain useful when an
    // upstream proxy returns an empty or non-JSON response.
  }

  return fallbackMessage;
}

async function authenticatedRequest(
  path,
  {
    body,
    fallbackMessage,
    extraHeaders,
    method = 'GET',
    signal,
  } = {},
) {
  if (!isFirebaseConfigured || !auth?.currentUser) {
    throw new Error('Phiên đăng nhập không còn hợp lệ.');
  }

  const idToken = await auth.currentUser.getIdToken();
  const headers = {
    Accept: 'application/json',
    Authorization: `Bearer ${idToken}`,
    ...extraHeaders,
  };

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    body: body === undefined ? undefined : JSON.stringify(body),
    headers,
    method,
    signal,
  });

  if (response.status === 401 || response.status === 403) {
    throw new Error('Phiên đăng nhập đã hết hạn.');
  }

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, fallbackMessage));
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export async function getRackState({ signal } = {}) {
  const data = await authenticatedRequest('/api/rack/state', {
    fallbackMessage: 'Không thể đọc trạng thái giàn phơi.',
    signal,
  });

  if (
    data?.rack_state !== null
    && data?.rack_state !== 'extended'
    && data?.rack_state !== 'retracted'
    && data?.rack_state !== 'error'
  ) {
    throw new Error('Dữ liệu trạng thái giàn phơi không hợp lệ.');
  }

  return data;
}

export async function getDeviceStatus({ signal } = {}) {
  const data = await authenticatedRequest('/api/device/status', {
    fallbackMessage: 'Không thể đọc trạng thái kết nối ESP32.',
    signal,
  });

  if (
    typeof data?.online !== 'boolean'
    && data?.status !== 'online'
    && data?.status !== 'offline'
    && data?.status !== 'checking'
  ) {
    throw new Error('Dữ liệu trạng thái kết nối ESP32 không hợp lệ.');
  }

  return data;
}

export async function getDeviceConfig({ signal } = {}) {
  const data = await authenticatedRequest('/api/device/config', {
    fallbackMessage: 'Không thể đọc chế độ vận hành.',
    signal,
  });

  if (
    data?.mode !== null
    && data?.mode !== 'manual'
    && data?.mode !== 'auto'
  ) {
    throw new Error('Dữ liệu chế độ vận hành không hợp lệ.');
  }

  return data;
}

export async function updateDeviceConfig(mode, { signal } = {}) {
  if (mode !== 'manual' && mode !== 'auto') {
    throw new Error('Chế độ vận hành không hợp lệ.');
  }

  const data = await authenticatedRequest('/api/device/config', {
    body: { mode },
    fallbackMessage: 'Không thể cập nhật chế độ vận hành.',
    method: 'PUT',
    signal,
  });

  if (data?.mode !== 'manual' && data?.mode !== 'auto') {
    throw new Error('Phản hồi chế độ vận hành không hợp lệ.');
  }

  return data;
}

export async function sendRackCommand(command, { signal } = {}) {
  if (command !== 'open' && command !== 'close') {
    throw new Error('Lệnh giàn phơi không hợp lệ.');
  }

  const clientRequestId = crypto.randomUUID();
  const data = await authenticatedRequest('/api/rack/commands', {
    body: {
      client_request_id: clientRequestId,
      command,
    },
    extraHeaders: {
      'Idempotency-Key': clientRequestId,
    },
    fallbackMessage: 'Không thể gửi lệnh tới giàn phơi.',
    method: 'POST',
    signal,
  });

  if (
    !data
    || typeof data !== 'object'
    || typeof data.command_id !== 'string'
    || data.command !== command
    || data.status !== 'pending'
  ) {
    throw new Error('Phản hồi gửi lệnh không hợp lệ.');
  }

  return data;
}

export async function getCommandHistory({ limit = 50, signal } = {}) {
  const searchParams = new URLSearchParams({ limit: String(limit) });
  const data = await authenticatedRequest(
    `/api/history?${searchParams}`,
    {
      fallbackMessage: 'Không thể tải lịch sử hoạt động.',
      signal,
    },
  );

  if (!Array.isArray(data?.items)) {
    throw new Error('Dữ liệu lịch sử hoạt động không hợp lệ.');
  }

  return data.items;
}
