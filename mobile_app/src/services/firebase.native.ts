import AsyncStorage from "@react-native-async-storage/async-storage";
import * as FirebaseAuth from "firebase/auth";
import type { Auth, Persistence } from "firebase/auth";
import { app, db } from "@/services/firebase-core";

// O pacote expo seleciona a exportacao React Native em tempo de execucao. A
// declaracao generica do Firebase usada pelo TypeScript nao lista esta funcao.
const getReactNativePersistence = (
  FirebaseAuth as typeof FirebaseAuth & {
    getReactNativePersistence(storage: typeof AsyncStorage): Persistence;
  }
).getReactNativePersistence;

/**
 * Firebase Auth nativo com sessao persistente no Expo Go.
 * O fallback atende apenas o Fast Refresh, quando a instancia ja existe.
 */
function initializeNativeAuth(): Auth {
  try {
    return FirebaseAuth.initializeAuth(app, {
      persistence: getReactNativePersistence(AsyncStorage),
    });
  } catch (error) {
    if (
      error
      && typeof error === "object"
      && "code" in error
      && error.code === "auth/already-initialized"
    ) {
      return FirebaseAuth.getAuth(app);
    }
    throw error;
  }
}

export const auth = initializeNativeAuth();

export { app, db };

export default db;
