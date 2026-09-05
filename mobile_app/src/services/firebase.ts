import { getAuth } from "firebase/auth";
import { app, db } from "@/services/firebase-core";

/**
 * Entrada Web do Firebase. No Android/iOS, o Metro seleciona automaticamente
 * firebase.native.ts, que persiste a sessao no AsyncStorage.
 */
export const auth = getAuth(app);

export { app, db };

export default db;
