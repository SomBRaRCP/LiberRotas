"""Authoritative OpenAPI metadata for the TRQ-BEC LiberRotas API."""

from __future__ import annotations

from typing import Any

from .models import ApiErrorResponse

API_DESCRIPTION = """
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

A versão `0.5.0-alpha.1` mantém Ed25519 apenas como perfil de laboratório.
ML-KEM-768 e ML-DSA-65 permanecem bloqueados até a integração de um provider
auditado e aprovado.
""".strip()

OPENAPI_TAGS = [
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
    {
        "name": "Operações internas",
        "description": (
            "Rotas administrativas para integridade do ledger. Exigem custom claim `admin=true` e não integram o contrato público do aplicativo."
        ),
    },
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

AUTH_ERROR_RESPONSES = {
    401: {
        "model": ApiErrorResponse,
        "description": "Firebase ID token ausente, malformado, expirado, revogado ou inválido.",
        "content": {
            "application/json": {
                "example": {
                    "code": "AUTH_TOKEN_INVALID",
                    "message": "AUTH_TOKEN_INVALID",
                }
            }
        },
    },
    403: {
        "model": ApiErrorResponse,
        "description": "Identidade autenticada, porém sem claim, vínculo ou permissão necessária.",
        "content": {
            "application/json": {
                "example": {
                    "code": "ENTREPRENEUR_CLAIM_REQUIRED",
                    "message": "ENTREPRENEUR_CLAIM_REQUIRED",
                }
            }
        },
    },
}

CONFLICT_RESPONSE = {
    409: {
        "model": ApiErrorResponse,
        "description": "Conflito de vínculo, repetição, token já utilizado ou operação já concluída.",
        "content": {
            "application/json": {
                "example": {
                    "code": "TOKEN_NOT_REDEEMABLE",
                    "message": "TOKEN_NOT_REDEEMABLE",
                }
            }
        },
    }
}

UNAVAILABLE_RESPONSE = {
    503: {
        "model": ApiErrorResponse,
        "description": "Dependência crítica ou provider criptográfico indisponível. A operação falha fechada.",
        "content": {
            "application/json": {
                "example": {
                    "code": "PQC_PROVIDER_NOT_READY",
                    "message": "PQC_PROVIDER_NOT_READY",
                }
            }
        },
    }
}
