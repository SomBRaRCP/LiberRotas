import { base64UrlToBytes, bytesToBase64Url } from "./base64";
import type { DeviceIdentity } from "./contracts";

const DATABASE_NAME = "feitour-trq-bec-device-identity";
const DATABASE_VERSION = 1;
const STORE_NAME = "device-keys";
const RECORD_PREFIX = "feitour:trq-bec:device-key:web:v1";
const ALGORITHM = { name: "Ed25519" } as const;

type StoredWebDeviceKey = {
  version: 1;
  privateKey: CryptoKey;
  publicKeyB64u: string;
  keyId: string;
};

let databasePromise: Promise<IDBDatabase> | undefined;

function stableBuffer(bytes: Uint8Array): ArrayBuffer {
  return Uint8Array.from(bytes).buffer;
}

function assertWebPlatformAvailable() {
  if (!globalThis.isSecureContext) {
    throw new Error("A identidade segura exige HTTPS ou acesso local por 127.0.0.1.");
  }
  if (!globalThis.crypto?.subtle || typeof globalThis.indexedDB === "undefined") {
    throw new Error("Este navegador não oferece WebCrypto e IndexedDB necessários para emitir a oferta.");
  }
}

function openDatabase(): Promise<IDBDatabase> {
  assertWebPlatformAvailable();

  databasePromise ??= new Promise((resolve, reject) => {
    const request = globalThis.indexedDB.open(DATABASE_NAME, DATABASE_VERSION);

    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME);
      }
    };
    request.onsuccess = () => {
      const database = request.result;
      database.onversionchange = () => {
        database.close();
        databasePromise = undefined;
      };
      resolve(database);
    };
    request.onerror = () => {
      databasePromise = undefined;
      reject(new Error("Não foi possível abrir o armazenamento seguro do navegador."));
    };
    request.onblocked = () => {
      databasePromise = undefined;
      reject(new Error("Feche outras abas do LiberRotas e tente novamente."));
    };
  });

  return databasePromise;
}

async function calculateKeyId(publicKey: Uint8Array): Promise<string> {
  const digest = new Uint8Array(
    await globalThis.crypto.subtle.digest("SHA-256", stableBuffer(publicKey)),
  );
  return `device:ed25519-lab:${bytesToBase64Url(digest.subarray(0, 18))}`;
}

async function deviceKeyRecord(ownerUid: string): Promise<string> {
  if (!ownerUid) throw new Error("Usuário inválido para a identidade do dispositivo.");
  const ownerBytes = new TextEncoder().encode(ownerUid);
  const digest = new Uint8Array(
    await globalThis.crypto.subtle.digest("SHA-256", stableBuffer(ownerBytes)),
  );
  return `${RECORD_PREFIX}:${bytesToBase64Url(digest.subarray(0, 18))}`;
}

function parseStoredKey(value: unknown): StoredWebDeviceKey {
  if (!value || typeof value !== "object") throw new Error("Registro de chave Web inválido.");
  const record = value as Partial<StoredWebDeviceKey>;
  const privateKey = record.privateKey;
  if (
    record.version !== 1
    || typeof record.publicKeyB64u !== "string"
    || typeof record.keyId !== "string"
    || !privateKey
    || privateKey.type !== "private"
    || privateKey.extractable
    || privateKey.algorithm.name !== ALGORITHM.name
    || !privateKey.usages.includes("sign")
  ) {
    throw new Error("Registro de chave Web inválido.");
  }
  if (base64UrlToBytes(record.publicKeyB64u).length !== 32) {
    throw new Error("Chave pública Web inválida.");
  }
  return record as StoredWebDeviceKey;
}

async function validateStoredKey(record: StoredWebDeviceKey): Promise<StoredWebDeviceKey> {
  const publicKeyBytes = base64UrlToBytes(record.publicKeyB64u);
  if (record.keyId !== await calculateKeyId(publicKeyBytes)) {
    throw new Error("A identidade segura armazenada está inconsistente.");
  }

  const publicKey = await globalThis.crypto.subtle.importKey(
    "raw",
    stableBuffer(publicKeyBytes),
    ALGORITHM,
    false,
    ["verify"],
  );
  const challenge = globalThis.crypto.getRandomValues(new Uint8Array(32));
  const signature = await globalThis.crypto.subtle.sign(
    ALGORITHM,
    record.privateKey,
    stableBuffer(challenge),
  );
  const verified = await globalThis.crypto.subtle.verify(
    ALGORITHM,
    publicKey,
    signature,
    stableBuffer(challenge),
  );
  if (!verified) throw new Error("A chave privada Web não corresponde à chave pública armazenada.");
  return record;
}

async function readRecord(recordKey: string): Promise<StoredWebDeviceKey | null> {
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readonly");
    const request = transaction.objectStore(STORE_NAME).get(recordKey);
    request.onsuccess = () => {
      try {
        resolve(request.result === undefined ? null : parseStoredKey(request.result));
      } catch (error) {
        reject(error);
      }
    };
    request.onerror = () => reject(new Error("Não foi possível ler a identidade segura do navegador."));
  });
}

async function storeIfAbsent(
  recordKey: string,
  candidate: StoredWebDeviceKey,
): Promise<StoredWebDeviceKey> {
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.get(recordKey);
    let selected: StoredWebDeviceKey | undefined;

    request.onsuccess = () => {
      try {
        if (request.result === undefined) {
          selected = candidate;
          store.add(candidate, recordKey);
        } else {
          selected = parseStoredKey(request.result);
        }
      } catch (error) {
        transaction.abort();
        reject(error);
      }
    };
    transaction.oncomplete = () => {
      if (selected) resolve(selected);
      else reject(new Error("A identidade segura não foi gravada."));
    };
    transaction.onerror = () => reject(new Error("Não foi possível gravar a identidade segura do navegador."));
    transaction.onabort = () => reject(new Error("A gravação da identidade segura foi cancelada."));
  });
}

async function createRecord(): Promise<StoredWebDeviceKey> {
  let keyPair: CryptoKeyPair;
  try {
    keyPair = await globalThis.crypto.subtle.generateKey(
      ALGORITHM,
      false,
      ["sign", "verify"],
    );
  } catch {
    throw new Error("Este navegador não oferece assinatura Ed25519 por WebCrypto.");
  }
  if (keyPair.privateKey.extractable) {
    throw new Error("O navegador não protegeu a chave privada corretamente.");
  }
  const publicKey = new Uint8Array(
    await globalThis.crypto.subtle.exportKey("raw", keyPair.publicKey),
  );
  if (publicKey.length !== 32) throw new Error("O navegador gerou uma chave pública Ed25519 inválida.");
  return {
    version: 1,
    privateKey: keyPair.privateKey,
    publicKeyB64u: bytesToBase64Url(publicKey),
    keyId: await calculateKeyId(publicKey),
  };
}

async function loadOrCreateKey(ownerUid: string): Promise<StoredWebDeviceKey> {
  assertWebPlatformAvailable();
  const recordKey = await deviceKeyRecord(ownerUid);
  const existing = await readRecord(recordKey);
  if (existing) return validateStoredKey(existing);
  return validateStoredKey(await storeIfAbsent(recordKey, await createRecord()));
}

export async function getOrCreateDeviceIdentity(ownerUid: string): Promise<DeviceIdentity> {
  const record = await loadOrCreateKey(ownerUid);
  return {
    keyId: record.keyId,
    publicKeyB64u: record.publicKeyB64u,
    algorithm: "ED25519_LAB",
    storageProfile: "WEB_CRYPTO_INDEXEDDB_LAB",
  };
}

export async function signDeviceProof(message: Uint8Array, ownerUid: string): Promise<string> {
  const record = await loadOrCreateKey(ownerUid);
  const signature = await globalThis.crypto.subtle.sign(
    ALGORITHM,
    record.privateKey,
    stableBuffer(message),
  );
  return bytesToBase64Url(new Uint8Array(signature));
}

export async function removeDeviceIdentity(ownerUid: string): Promise<void> {
  assertWebPlatformAvailable();
  const database = await openDatabase();
  const recordKey = await deviceKeyRecord(ownerUid);
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).delete(recordKey);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(new Error("Não foi possível remover a identidade segura do navegador."));
    transaction.onabort = () => reject(new Error("A remoção da identidade segura foi cancelada."));
  });
}
