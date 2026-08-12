import {
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
} from 'firebase/auth';
import { get, ref } from 'firebase/database';

import {
  auth,
  database,
  isFirebaseConfigured,
} from '../firebase.js';

const INVALID_FIREBASE_KEY_CHARACTERS = /[.#$[\]\/]/;
const DEVICE_EMAIL_SUFFIX = '@smartdry.local';

export function normalizeDeviceId(value) {
  const deviceId = value.trim();

  if (!deviceId) {
    throw new Error('Vui lòng nhập Device ID.');
  }

  if (INVALID_FIREBASE_KEY_CHARACTERS.test(deviceId)) {
    throw new Error('Device ID không được chứa . # $ [ ] hoặc /.');
  }

  return deviceId;
}

function assertFirebaseConfigured() {
  if (!isFirebaseConfigured || !auth || !database) {
    throw new Error('Firebase chưa được cấu hình. Vui lòng kiểm tra file website/.env.');
  }
}

export function mapDeviceIdToEmail(value) {
  const deviceId = normalizeDeviceId(value);
  return `${deviceId}${DEVICE_EMAIL_SUFFIX}`;
}

function getDeviceIdFromUser(user) {
  const email = user.email?.trim().toLowerCase();

  if (!email?.endsWith(DEVICE_EMAIL_SUFFIX)) {
    throw new Error('Tài khoản không thuộc hệ thống SmartDry.');
  }

  return normalizeDeviceId(
    email.slice(0, -DEVICE_EMAIL_SUFFIX.length),
  );
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
  const deviceId = expectedDeviceId
    ? normalizeDeviceId(expectedDeviceId)
    : getDeviceIdFromUser(user);

  if (user.email?.toLowerCase() !== mapDeviceIdToEmail(deviceId).toLowerCase()) {
    await firebaseSignOut(auth);
    throw new Error('Device ID hoặc mật khẩu không đúng.');
  }

  const snapshot = await get(ref(database, `Device_Accounts/${deviceId}`));
  const account = snapshot.val();

  if (!account || account.enabled !== true) {
    await firebaseSignOut(auth);
    throw new Error('Thiết bị không tồn tại hoặc đã bị vô hiệu hóa.');
  }

  return {
    ...account,
    device_id: deviceId,
  };
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

    return await loadDeviceAccount(credential.user, deviceId);
  } catch (error) {
    throw getLoginError(error);
  }
}

export function observeAuthState(callback) {
  if (!isFirebaseConfigured || !auth || !database) {
    callback(null);
    return () => {};
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
