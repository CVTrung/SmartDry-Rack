import {
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
} from 'firebase/auth';

import {
  auth,
  isFirebaseConfigured,
} from '../firebase.js';

const DEVICE_ID_PATTERN = /^[a-z0-9_-]+$/;
const DEVICE_EMAIL_SUFFIX = '@smartdry.local';
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL
  || 'http://localhost:8000';

export function normalizeDeviceId(value) {
  const deviceId = value.trim().toLowerCase();

  if (!deviceId) {
    throw new Error('Vui lòng nhập Device ID.');
  }

  if (!DEVICE_ID_PATTERN.test(deviceId)) {
    throw new Error(
      'Device ID chỉ được chứa chữ thường, số, dấu gạch ngang và dấu gạch dưới.',
    );
  }

  return deviceId;
}

function assertFirebaseConfigured() {
  if (!isFirebaseConfigured || !auth) {
    throw new Error('Firebase chưa được cấu hình. Vui lòng kiểm tra file website/.env.');
  }
}

export function mapDeviceIdToEmail(value) {
  const deviceId = normalizeDeviceId(value);
  return `${deviceId}${DEVICE_EMAIL_SUFFIX}`;
}

function getLoginError(error) {
  const code = error?.code;

  if (
    code === 'auth/invalid-credential'
    || code === 'auth/user-not-found'
    || code === 'auth/wrong-password'
    || code === 'auth/invalid-email'
  ) {
    return new Error('Device ID hoặc mật khẩu không đúng.');
  }

  if (code === 'auth/network-request-failed') {
    return new Error('Mất kết nối. Vui lòng kiểm tra mạng và thử lại.');
  }

  if (code === 'auth/too-many-requests') {
    return new Error('Đăng nhập thất bại quá nhiều lần. Vui lòng thử lại sau.');
  }

  return error instanceof Error ? error : new Error('Không thể đăng nhập.');
}

async function loadDeviceAccount(user, expectedDeviceId) {
  const idToken = await user.getIdToken();

  const response = await fetch(
    `${API_BASE_URL}/api/auth/me`,
    {
      headers: {
        Authorization: `Bearer ${idToken}`,
      },
    },
  );

  if (response.status === 401 || response.status === 403) {
    await firebaseSignOut(auth);
    throw new Error(
      'Tài khoản không tồn tại hoặc đã bị vô hiệu hóa.',
    );
  }

  if (!response.ok) {
    throw new Error(
      'Không thể kiểm tra tài khoản với máy chủ.',
    );
  }

  const account = await response.json();

  if (
    expectedDeviceId
    && account.device_id !== normalizeDeviceId(expectedDeviceId)
  ) {
    await firebaseSignOut(auth);
    throw new Error('Device ID hoặc mật khẩu không đúng.');
  }

  return account;
}

export async function loginWithDeviceId(rawDeviceId, password) {
  const deviceId = normalizeDeviceId(rawDeviceId);

  if (!password) {
    throw new Error('Vui lòng nhập mật khẩu.');
  }

  assertFirebaseConfigured();

  try {
    const credential = await signInWithEmailAndPassword(
      auth,
      mapDeviceIdToEmail(deviceId),
      password,
    );

    return await loadDeviceAccount(
      credential.user,
      deviceId,
    );
  } catch (error) {
    throw getLoginError(error);
  }
}

export function observeAuthState(callback) {
  if (!isFirebaseConfigured || !auth) {
    callback(null);
    return () => { };
  }

  return onAuthStateChanged(auth, async (firebaseUser) => {
    if (!firebaseUser) {
      callback(null);
      return;
    }

    try {
      callback(await loadDeviceAccount(firebaseUser));
    } catch {
      callback(null);
    }
  });
}

export async function logoutFromFirebase() {
  assertFirebaseConfigured();
  await firebaseSignOut(auth);
}
