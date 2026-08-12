import { initializeApp } from "firebase/app";
import {
    getAuth,
    signInWithEmailAndPassword,
    signOut,
} from "firebase/auth";
import { getFirestore } from "firebase/firestore";


const firebaseConfig = {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
    storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
    messagingSenderId:
        import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
    appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const firebaseApp = initializeApp(firebaseConfig);

export const firebaseAuth = getAuth(firebaseApp);
export const firestoreDatabase = getFirestore(firebaseApp);

function normalizeDeviceId(deviceId) {
    return deviceId.trim().toLowerCase();
}

function getDeviceLoginEmail(deviceId) {
    const normalizedDeviceId = normalizeDeviceId(deviceId);

    if (!normalizedDeviceId) {
        throw new Error("Device ID is required");
    }

    return `${normalizedDeviceId}@smartdry.local`;
}

export async function signInDevice(
    deviceId,
    password,
) {
    return signInWithEmailAndPassword(
        firebaseAuth,
        getDeviceLoginEmail(deviceId),
        password,
    );
}

export async function signOutDevice() {
    await signOut(firebaseAuth);
}