"""Metadados OpenAPI autoritativos da TRQ-BEC LiberRotas API."""

from __future__ import annotations

from typing import Any

from .models import ApiErrorResponse

PUBLIC_API_DESCRIPTION = """
## Fronteira de segurança do LiberRotas

A **TRQ-BEC LiberRotas API** é a camada autoritativa para cadastro de dispositivos,
emissão de cupons, resgate com prova de posse e registro de evidências no ledger.

### Autenticação

As operações protegidas exigem um **Firebase ID token** no esquema HTTP Bearer.
No botão **Authorize**, cole somente o token — a interface acrescenta `Bearer` automaticamente.

### Regra criptográfica

A decisão é *fail-closed*: se a verificação criptográfica não estiver íntegra,
a autorização não produz `ALLOW`. O estado do provider pode ser consultado em
`GET /health/crypto`.

### Estado desta versão

A versão `0.5.0-alpha.2` mantém Ed25519 apenas como perfil de laboratório.
ML-KEM-768 e ML-DSA-65 permanecem bloqueados até a integração de um provider
auditado e aprovado.
""".strip()

INTERNAL_API_DESCRIPTION = """
## Contrato administrativo da TRQ-BEC

Este contrato é destinado exclusivamente a operadores autorizados da infraestrutura
LiberRotas. As rotas administrativas exigem **Firebase ID token** com a custom claim
`admin=true`.

### Separação de contratos

As operações internas não aparecem no OpenAPI público, no Swagger público nem na
ReDoc pública. Esta documentação administrativa também permanece desativada em
ambiente de produção.

### Integridade do ledger

O checkpoint cobre a cadeia append-only atual, vincula a versão de política ao hash
raiz e produz uma assinatura verificável com a chave administrativa de checkpoint.
""".strip()

PUBLIC_OPENAPI_TAGS = [
    {
        "name": "Saúde e prontidão",
        "description": (
            "Diagnósticos sem autenticação para disponibilidade do banco, Redis e provider criptográfico. "
            "Não representam autorização de negócio."
        ),
    },
    {
        "name": "Dispositivos",
        "description": (
            "Cadastro e vinculação de chaves públicas de dispositivo ao sujeito autenticado pelo Firebase."
        ),
    },
    {
        "name": "Cupons",
        "description": (
            "Emissão autoritativa de cupons por contas empreendedoras, com vínculo de identidade, dispositivo e política."
        ),
    },
    {
        "name": "Resgate",
        "description": (
            "Fluxo em duas etapas: criação de desafio de uso único e autorização mediante prova de posse da chave."
        ),
    },
]

INTERNAL_OPENAPI_TAGS = [
    {
        "name": "Operações internas",
        "description": (
            "Rotas administrativas para integridade do ledger. Exigem custom claim `admin=true` "
            "e não integram o contrato público do aplicativo."
        ),
    }
]

SWAGGER_UI_PARAMETERS: dict[str, Any] = {
    "deepLinking": True,
    "displayRequestDuration": True,
    "docExpansion": "none",
    "filter": True,
    "persistAuthorization": True,
    "defaultModelExpandDepth": 2,
    "defaultModelsExpandDepth": 1,
    "showExtensions": True,
    "showCommonExtensions": True,
}


def _error_response(
    description: str,
    examples: dict[str, tuple[str, str, str | None]],
) -> dict[str, Any]:
    """Cria uma resposta OpenAPI com exemplos nomeados e aderentes ao código real."""

    return {
        "model": ApiErrorResponse,
        "description": description,
        "content": {
            "application/json": {
                "examples": {
                    key: {
                        "summary": summary,
                        "value": {
                            "code": code,
                            "message": message or code,
                        },
                    }
                    for key, (summary, code, message) in examples.items()
                }
            }
        },
    }


AUTHENTICATION_RESPONSE = {
    401: _error_response(
        "Firebase ID token ausente, malformado, expirado, revogado ou inválido.",
        {
            "bearerAusente": ("Cabeçalho Bearer ausente", "AUTH_BEARER_REQUIRED", None),
            "bearerInvalido": ("Cabeçalho Bearer inválido", "AUTH_BEARER_INVALID", None),
            "tokenInvalido": ("Firebase ID token inválido", "AUTH_TOKEN_INVALID", None),
            "sujeitoInvalido": ("Sujeito do token inválido", "AUTH_SUBJECT_INVALID", None),
        },
    )
}

ENROLL_CONFLICT_RESPONSE = {
    409: _error_response(
        "A chave do dispositivo ou a chave pública já está vinculada a outra identidade.",
        {
            "identificadorJaVinculado": (
                "Identificador de chave já vinculado",
                "DEVICE_KEY_BINDING_CONFLICT",
                None,
            ),
            "chavePublicaJaVinculada": (
                "Chave pública já vinculada",
                "DEVICE_PUBLIC_KEY_ALREADY_BOUND",
                None,
            ),
        },
    )
}

ISSUE_FORBIDDEN_RESPONSE = {
    403: _error_response(
        "Identidade autenticada, porém sem claim, vínculo de emissor ou dispositivo necessário.",
        {
            "claimEmpreendedor": (
                "Claim de empreendedor ausente",
                "ENTREPRENEUR_CLAIM_REQUIRED",
                None,
            ),
            "vinculoEmissor": (
                "Emissor não corresponde ao Firebase UID",
                "ISSUER_BINDING_MISMATCH",
                None,
            ),
            "dispositivoNaoCadastrado": (
                "Dispositivo emissor não cadastrado",
                "DEVICE_NOT_ENROLLED",
                None,
            ),
        },
    )
}

ISSUE_NOT_FOUND_RESPONSE = {
    404: _error_response(
        "Cupom inexistente, inativo ou não pertencente ao emissor autenticado.",
        {
            "cupomIndisponivel": (
                "Cupom não está ativo ou não pertence ao emissor",
                "COUPON_NOT_ACTIVE_OR_NOT_OWNED",
                None,
            )
        },
    )
}

ISSUE_UNAVAILABLE_RESPONSE = {
    503: _error_response(
        "Provider pós-quântico indisponível ou adaptação do envelope ainda não aprovada. A emissão falha fechada.",
        {
            "providerNaoPronto": (
                "Provider pós-quântico não está pronto",
                "PQC_PROVIDER_NOT_READY",
                None,
            ),
            "adaptadorPendente": (
                "Adaptador de envelope aguarda aprovação",
                "PQC_ENVELOPE_ADAPTER_PENDING_APPROVAL",
                None,
            ),
        },
    )
}

BEGIN_BAD_REQUEST_RESPONSE = {
    400: _error_response(
        "QR inválido, vínculo inconsistente ou envelope criptográfico rejeitado.",
        {
            "vinculoQrInvalido": (
                "QR não corresponde ao token armazenado",
                "QR_BINDING_MISMATCH",
                None,
            ),
            "tokenCriptograficoInvalido": (
                "Envelope criptográfico inválido",
                "TOKEN_CRYPTO_INVALID",
                None,
            ),
        },
    )
}

BEGIN_FORBIDDEN_RESPONSE = {
    403: _error_response(
        "O dispositivo do visitante não está cadastrado para a identidade autenticada.",
        {
            "dispositivoNaoCadastrado": (
                "Dispositivo de resgate não cadastrado",
                "DEVICE_NOT_ENROLLED",
                None,
            )
        },
    )
}

BEGIN_NOT_FOUND_RESPONSE = {
    404: _error_response(
        "Referência de token desconhecida.",
        {
            "tokenDesconhecido": (
                "Referência do token não encontrada",
                "TOKEN_REFERENCE_UNKNOWN",
                None,
            )
        },
    )
}

BEGIN_CONFLICT_RESPONSE = {
    409: _error_response(
        "Token já utilizado, retido ou em estado incompatível com novo resgate.",
        {
            "tokenNaoResgatavel": (
                "Token não pode ser resgatado novamente",
                "TOKEN_NOT_REDEEMABLE",
                None,
            )
        },
    )
}

BEGIN_EXPIRED_RESPONSE = {
    410: _error_response(
        "Token expirado.",
        {
            "tokenExpirado": (
                "Prazo de validade do token encerrado",
                "TOKEN_EXPIRED",
                None,
            )
        },
    )
}

AUTHORIZE_NOT_FOUND_RESPONSE = {
    404: _error_response(
        "Operação de resgate desconhecida.",
        {
            "operacaoDesconhecida": (
                "Operação não encontrada",
                "OPERATION_UNKNOWN",
                None,
            )
        },
    )
}

AUTHORIZE_UNAVAILABLE_RESPONSE = {
    503: _error_response(
        "Reserva distribuída contra replay indisponível. A autorização falha fechada.",
        {
            "replayIndisponivel": (
                "Armazenamento de replay indisponível",
                "REPLAY_STORE_UNAVAILABLE",
                None,
            )
        },
    )
}

ADMIN_FORBIDDEN_RESPONSE = {
    403: _error_response(
        "Identidade autenticada sem a custom claim administrativa obrigatória.",
        {
            "claimAdmin": (
                "Custom claim admin=true ausente",
                "ADMIN_CLAIM_REQUIRED",
                None,
            )
        },
    )
}

CHECKPOINT_CONFLICT_RESPONSE = {
    409: _error_response(
        "Ledger vazio ou estado incompatível com a criação de checkpoint.",
        {
            "ledgerVazio": (
                "Não existem eventos para cobrir",
                "LEDGER_EMPTY",
                None,
            )
        },
    )
}
