import * as ed from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha2.js";
import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import { base64UrlToBytes, bytesToBase64Url } from "./base64";
import type { DeviceIdentity } from "./contracts";

const LEGACY_DEVICE_KEY_RECORD = "feitour:trq-bec:device-key:v1";
const DEVICE_KEY_PREFIX = "feitour:trq-bec:device-key:v2";

// Perfil de dispositivo do laboratório: a seed Ed25519 é cifrada pelo
// SecureStore, mas continua exportável para o processo JavaScript. Produção
// deve trocar este adapter por Keystore/Secure Enclave não exportável e,
// quando disponível, atestado. O provider pós-quântico permanece no backend.

type StoredDeviceKey = {
  version: 1;
  secretKeyB64u: string;
  publicKeyB64u: string;
  keyId: string;
};

ed.hashes.sha512 = sha512;
ed.hashes.sha512Async = async (message: Uint8Array) => sha512(message);

async function calculateKeyId(publicKey: Uint8Array) {
  const stableBuffer = Uint8Array.from(publicKey).buffer;
  const digest = new Uint8Array(await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256, stableBuffer));
  return `device:ed25519-lab:${bytesToBase64Url(digest.subarray(0, 18))}`;
}

async function deviceKeyRecord(ownerUid: string) {
  const ownerDigest = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    ownerUid,
  );
  return `${DEVICE_KEY_PREFIX}:${ownerDigest.slice(0, 32)}`;
}

function parseStoredKey(raw: string): StoredDeviceKey {
  const parsed = JSON.parse(raw) as Partial<StoredDeviceKey>;
  if (
    parsed.version !== 1
    || typeof parsed.secretKeyB64u !== "string"
    || typeof parsed.publicKeyB64u !== "string"
    || typeof parsed.keyId !== "string"
  ) {
    throw new Error("Registro de chave de dispositivo inválido.");
  }
  const secret = base64UrlToBytes(parsed.secretKeyB64u);
  const publicKey = base64UrlToBytes(parsed.publicKeyB64u);
  if (secret.length !== 32 || publicKey.length !== 32) throw new Error("Tamanho de chave de dispositivo inválido.");
  return parsed as StoredDeviceKey;
}

async function loadOrCreateKey(ownerUid: string): Promise<StoredDeviceKey> {
  const recordKey = await deviceKeyRecord(ownerUid);
  let current = await SecureStore.getItemAsync(recordKey);
  if (!current) {
    // Migração única do perfil anterior, que armazenava uma chave global.
    current = await SecureStore.getItemAsync(LEGACY_DEVICE_KEY_RECORD);
    if (current) {
      await SecureStore.setItemAsync(recordKey, current, {
        keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
      });
      await SecureStore.deleteItemAsync(LEGACY_DEVICE_KEY_RECORD);
    }
  }
  if (current) return parseStoredKey(current);

  const secretKey = await Crypto.getRandomBytesAsync(32);
  const publicKey = ed.getPublicKey(secretKey);
  const record: StoredDeviceKey = {
    version: 1,
    secretKeyB64u: bytesToBase64Url(secretKey),
    publicKeyB64u: bytesToBase64Url(publicKey),
    keyId: await calculateKeyId(publicKey),
  };
  await SecureStore.setItemAsync(recordKey, JSON.stringify(record), {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
  secretKey.fill(0);
  return record;
}

export async function getOrCreateDeviceIdentity(ownerUid: string): Promise<DeviceIdentity> {
  const record = await loadOrCreateKey(ownerUid);
  return {
    keyId: record.keyId,
    publicKeyB64u: record.publicKeyB64u,
    algorithm: "ED25519_LAB",
    storageProfile: "EXPO_SECURE_STORE_LAB",
  };
}

export async function signDeviceProof(message: Uint8Array, ownerUid: string): Promise<string> {
  const record = await loadOrCreateKey(ownerUid);
  const secretKey = base64UrlToBytes(record.secretKeyB64u);
  try {
    return bytesToBase64Url(ed.sign(message, secretKey));
  } finally {
    secretKey.fill(0);
  }
}

export async function removeDeviceIdentity(ownerUid: string) {
  await SecureStore.deleteItemAsync(await deviceKeyRecord(ownerUid));
}
