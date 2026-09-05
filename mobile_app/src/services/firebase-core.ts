import { getApp, getApps, initializeApp, type FirebaseOptions } from "firebase/app";
import { getFirestore } from "firebase/firestore";

const firebaseConfig: FirebaseOptions = {
  apiKey: process.env.EXPO_PUBLIC_FIREBASE_API_KEY?.trim(),
  authDomain: process.env.EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN?.trim(),
  projectId: process.env.EXPO_PUBLIC_FIREBASE_PROJECT_ID?.trim(),
  storageBucket: process.env.EXPO_PUBLIC_FIREBASE_STORAGE_BUCKET?.trim(),
  messagingSenderId: process.env.EXPO_PUBLIC_FIREBASE_MESSAGING_SENDER_ID?.trim(),
  appId: process.env.EXPO_PUBLIC_FIREBASE_APP_ID?.trim(),
};

const missingFirebaseConfig = Object.entries(firebaseConfig)
  .filter(([, value]) => typeof value !== "string" || value.length === 0)
  .map(([name]) => name);

if (missingFirebaseConfig.length > 0) {
  throw new Error(
    `Configuracao publica do Firebase incompleta: ${missingFirebaseConfig.join(", ")}. `
      + "Preencha as variaveis EXPO_PUBLIC_FIREBASE_* no arquivo .env.local.",
  );
}

/** Evita inicializacao duplicada durante o Fast Refresh do Expo. */
export const app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);

/** Instancia compartilhada do Cloud Firestore. */
export const db = getFirestore(app);
