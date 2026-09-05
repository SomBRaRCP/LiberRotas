export type CryptoEnvelope = {
  v: 1;
  suite_id: string;
  key_id: string;
  policy_version: string;
  iss: string;
  aud: "app-liberrotas";
  purpose: string;
  iat: number;
  exp: number;
  jti: string;
  intent_digest: string;
  signature: string;
};

export type FreshnessChallenge = {
  challenge_id: string;
  random_128: string;
  issued_at: number;
  expires_at: number;
  operation_id: string;
};

export type AuthorizationDecision = "DENY" | "ALLOW" | "STEP_UP" | "HOLD_OR_REVIEW";

export type AuthorizationResponse = {
  decision: AuthorizationDecision;
  operation_id: string;
  crypto_ok: boolean;
  reason_codes: string[];
  event_refs: string[];
  idempotent: boolean;
};

export interface DeviceSigner {
  /** O identificador é opaco; a chave privada não pode sair do armazenamento seguro. */
  getOrCreateKeyId(): Promise<string>;
  /** Assina os bytes canônicos produzidos pelo backend ou por codec idêntico auditado. */
  sign(message: Uint8Array): Promise<string>;
}

