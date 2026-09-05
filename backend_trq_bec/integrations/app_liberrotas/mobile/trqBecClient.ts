import type {
  AuthorizationResponse,
  CryptoEnvelope,
  DeviceSigner,
  FreshnessChallenge,
} from "./contracts";

type BeginResponse = {
  operation_id: string;
  session_id: string;
  envelope: CryptoEnvelope;
  challenge: FreshnessChallenge;
  proof_message_b64u: string;
};

export class TrqBecClient {
  constructor(
    private readonly baseUrl: string,
    private readonly signer: DeviceSigner,
    private readonly fetchFn: typeof fetch = fetch,
  ) {}

  async authorizeResource(resourceRef: string): Promise<AuthorizationResponse> {
    const deviceKeyId = await this.signer.getOrCreateKeyId();
    const begin = await this.post<BeginResponse>("/v1/trq-bec/begin", {
      resource_ref: resourceRef,
      device_key_id: deviceKeyId,
    });

    const proofBytes = decodeBase64Url(begin.proof_message_b64u);
    const deviceProof = await this.signer.sign(proofBytes);

    return this.post<AuthorizationResponse>("/v1/trq-bec/authorize", {
      operation_id: begin.operation_id,
      session_id: begin.session_id,
      envelope: begin.envelope,
      challenge_id: begin.challenge.challenge_id,
      device_key_id: deviceKeyId,
      device_proof_b64u: deviceProof,
    });
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const response = await this.fetchFn(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(`TRQ-BEC request failed (${response.status})`);
    }
    return (await response.json()) as T;
  }
}

function decodeBase64Url(value: string): Uint8Array {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  const binary = globalThis.atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

