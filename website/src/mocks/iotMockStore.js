/*  
MOCK CÁC TÍNH NĂNG Ở MONITOR PAGE
*/

import mockFixture from './iotCommands.json'; 

export const isMockIotMode = import.meta.env.VITE_IOT_MODE === 'mock';

const STORAGE_PREFIX = 'smartdry:iot-mock:';
const MOCK_STATE_EVENT = 'smartdry:iot-mock-updated';
const OFFLINE_AFTER_MS = 30_000; // quá 30s không có tín hiệu là offline
const HISTORY_LIMIT = 50; 

function getStorageKey(deviceId) {
  return `${STORAGE_PREFIX}${deviceId}`;
}

function createInitialState() {
  const fixtureStatus = mockFixture.Device_Status['<device_id>'];
  const now = Date.now();

  return {
    deviceStatus: {
      ...fixtureStatus,
      last_seen: mockFixture.simulation.initial_online
        ? now
        : now - OFFLINE_AFTER_MS - 1,
    },
    isOnline: mockFixture.simulation.initial_online,
    rackState: {
      ...mockFixture.initial_rack_state,
      updated_at: Math.floor(now / 1000),
    },
    history: [],
  };
}

function normalizeState(value) {
  const fallback = createInitialState();

  if (!value || typeof value !== 'object') {
    return fallback;
  }

  return {
    deviceStatus: {
      ...fallback.deviceStatus,
      ...(value.deviceStatus || {}),
    },
    isOnline: typeof value.isOnline === 'boolean'
      ? value.isOnline
      : fallback.isOnline,
    rackState: {
      ...fallback.rackState,
      ...(value.rackState || {}),
    },
    history: Array.isArray(value.history) ? value.history : [],
  };
}

export function getMockIotState(deviceId) {
  if (typeof window === 'undefined' || !deviceId) {
    return createInitialState();
  }

  try {
    const storedValue = window.localStorage.getItem(
      getStorageKey(deviceId),
    );

    if (!storedValue) {
      const initialState = createInitialState();
      window.localStorage.setItem(
        getStorageKey(deviceId),
        JSON.stringify(initialState),
      );
      return initialState;
    }

    return normalizeState(JSON.parse(storedValue));
  } catch {
    return createInitialState();
  }
}

function saveMockIotState(deviceId, state) {
  const normalizedState = normalizeState(state);

  if (typeof window === 'undefined' || !deviceId) {
    return normalizedState;
  }

  try {
    window.localStorage.setItem(
      getStorageKey(deviceId),
      JSON.stringify(normalizedState),
    );
  } catch {
    // The current tab can still update even when storage is unavailable.
  }

  window.dispatchEvent(new CustomEvent(MOCK_STATE_EVENT, {
    detail: { deviceId, state: normalizedState },
  }));

  return normalizedState;
}

export function subscribeToMockIotState(deviceId, onChange) {
  if (typeof window === 'undefined' || !deviceId) {
    return () => {};
  }

  function handleLocalUpdate(event) {
    if (event.detail?.deviceId === deviceId) {
      onChange(event.detail.state);
    }
  }

  function handleStorageUpdate(event) {
    if (event.key === getStorageKey(deviceId)) {
      onChange(getMockIotState(deviceId));
    }
  }

  window.addEventListener(MOCK_STATE_EVENT, handleLocalUpdate);
  window.addEventListener('storage', handleStorageUpdate);
  onChange(getMockIotState(deviceId));

  return () => {
    window.removeEventListener(MOCK_STATE_EVENT, handleLocalUpdate);
    window.removeEventListener('storage', handleStorageUpdate);
  };
}

export function setMockDeviceOnline(deviceId, isOnline) {
  const state = getMockIotState(deviceId);
  const now = Date.now();

  return saveMockIotState(deviceId, {
    ...state,
    isOnline,
    deviceStatus: {
      ...state.deviceStatus,
      last_seen: isOnline ? now : now - OFFLINE_AFTER_MS - 1,
    },
  });
}

export function refreshMockHeartbeat(deviceId) {
  const state = getMockIotState(deviceId);

  if (!state.isOnline) {
    return state;
  }

  return saveMockIotState(deviceId, {
    ...state,
    deviceStatus: {
      ...state.deviceStatus,
      last_seen: Date.now(),
    },
  });
}

function createCommandId() {
  return globalThis.crypto?.randomUUID?.()
    || `mock-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function recordMockCommandResult({
  action,
  deviceId,
  error = '',
  requestedAt,
  status,
}) {
  const state = getMockIotState(deviceId);
  const command = mockFixture.commands[action];

  if (!command) {
    throw new Error(`Mock command không hợp lệ: ${action}`);
  }

  const completedAt = Date.now();
  const previousState = state.rackState.rack_state;
  const wasCompleted = status === 'completed';
  const finalState = wasCompleted
    ? command.rack_state
    : previousState;
  const nextRackState = wasCompleted
    ? {
        rack_state: finalState,
        reason: `Lệnh ${command.label} từ Monitor Page`,
        updated_at: Math.floor(completedAt / 1000),
      }
    : state.rackState;
  const historyItem = {
    command_id: createCommandId(),
    action,
    label: command.label,
    status,
    requested_at: requestedAt,
    completed_at: completedAt,
    previous_state: previousState,
    final_state: finalState,
    error,
  };

  return saveMockIotState(deviceId, {
    ...state,
    rackState: nextRackState,
    history: [historyItem, ...state.history].slice(0, HISTORY_LIMIT),
  });
}

export function getMockCommand(action) {
  return mockFixture.commands[action] || null;
}

export function getMockSimulation() {
  return mockFixture.simulation;
}
