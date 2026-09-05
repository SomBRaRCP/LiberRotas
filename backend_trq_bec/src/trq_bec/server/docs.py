"""Metadados OpenAPI autoritativos da TRQ-BEC LiberRotas API."""

from __future__ import annotations

from typing import Any

from .models import ApiErrorResponse

PUBLIC_API_DESCRIPTION = """
## Fronteira de segurança do LiberRotas

A **TRQ-BEC LiberRotas API** é a camada autoritativa para cadastro de dispositivos,
produtos, preços, estoque, emissão de ofertas ao vivo, resgate com prova de posse e
registro de evidências no ledger.

### Autenticação

As operações protegidas exigem um **Firebase ID token** no esquema HTTP Bearer.
No botão **Authorize**, cole somente o token — a interface acrescenta `Bearer` automaticamente.

### Regra criptográfica

A decisão é *fail-closed*: se a verificação criptográfica não estiver íntegra,
a autorização não produz `ALLOW`. O estado do provider pode ser consultado em
`GET /health/crypto`.

### Estado desta versão

A versão `0.6.0-alpha.1` mantém Ed25519 apenas como perfil de laboratório.
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
        "name": "Administracao",
        "description": "Provisionamento institucional autorizado pelo backend.",
    },
    {
        "name": "Suporte",
        "description": "Consulta de contas em modo estritamente somente leitura.",
    },
    {
        "name": "Seguranca",
        "description": "Consulta de auditoria e resposta controlada a incidentes de acesso.",
    },
    {
        "name": "Instituicao",
        "description": "Gestao isolada dos grupos pertencentes a instituicao autenticada.",
    },
    {
        "name": "Dispositivos",
        "description": (
            "Cadastro e vinculação de chaves públicas de dispositivo ao sujeito autenticado pelo Firebase."
        ),
    },
    {
        "name": "Marketplace",
        "description": (
            "Catálogo autenticado, produtos, estoques e painel de ofertas. Preços e quantidades "
            "retornados por estas rotas são autoritativos."
        ),
    },
    {
        "name": "Comunidade",
        "description": (
            "Publicação no Feed, de pontos e de feiras após validação autoritativa de função, status e permissões."
        ),
    },
    {
        "name": "Cupons",
        "description": (
            "Emissão e consulta de ofertas por contas comerciais ativas, com preço recalculado no backend."
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
            "Aprovação de contas comerciais e integridade do ledger. Exigem custom claim `admin=true` "
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

CATALOG_NOT_FOUND_RESPONSE = {
    404: _error_response(
        "Perfil comercial público inexistente ou indisponível.",
        {
            "perfilIndisponivel": (
                "Perfil público não encontrado",
                "MERCHANT_PUBLIC_PROFILE_NOT_FOUND",
                None,
            )
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
            "chaveRevogada": (
                "Uma chave revogada deve ser substituída no dispositivo",
                "DEVICE_KEY_REVOKED",
                None,
            ),
        },
    )
}

ENROLL_LIMIT_RESPONSE = {
    429: _error_response(
        "A conta atingiu o limite de dispositivos aguardando aprovação.",
        {
            "limitePendentes": (
                "Revise ou revogue dispositivos pendentes antes de adicionar outro",
                "PENDING_DEVICE_LIMIT_REACHED",
                None,
            )
        },
    )
}

ENROLL_FORBIDDEN_RESPONSE = {
    403: _error_response(
        "O primeiro cadastro do dispositivo exige autenticação recente.",
        {
            "autenticacaoRecente": (
                "Entre novamente antes de cadastrar o primeiro dispositivo",
                "RECENT_AUTHENTICATION_REQUIRED",
                None,
            )
        },
    )
}

ISSUE_FORBIDDEN_RESPONSE = {
    403: _error_response(
        "Identidade autenticada, porém sem claim, conta comercial ativa ou dispositivo necessário.",
        {
            "claimEmpreendedor": (
                "Claim de empreendedor ausente",
                "ENTREPRENEUR_CLAIM_REQUIRED",
                None,
            ),
            "contaComercialInativa": (
                "Conta comercial ausente ou suspensa",
                "MERCHANT_ACCOUNT_INACTIVE",
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
        "Produto inexistente, inativo, sem estoque ou não pertencente ao emissor autenticado.",
        {
            "cupomIndisponivel": (
                "Produto não está ativo ou não pertence ao emissor",
                "PRODUCT_NOT_ACTIVE_OR_NOT_OWNED",
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
            ),
            "claimVisitante": (
                "Claim de visitante ausente",
                "VISITOR_CLAIM_REQUIRED",
                None,
            ),
            "autorresgate": (
                "Empreendedor tentou resgatar a própria oferta",
                "SELF_REDEMPTION_FORBIDDEN",
                None,
            ),
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
            ),
            "empreendedorInativo": (
                "Empreendedor suspenso antes do início",
                "MERCHANT_ACCOUNT_INACTIVE",
                None,
            ),
            "produtoIndisponivel": (
                "Produto inativo ou sem estoque",
                "PRODUCT_NOT_ACTIVE_OR_OUT_OF_STOCK",
                None,
            ),
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
            ),
            "ofertaExpirada": (
                "Prazo da oferta encerrado",
                "OFFER_EXPIRED",
                None,
            ),
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

AUTHORIZE_CONFLICT_RESPONSE = {
    409: _error_response(
        "A mesma operação já está sendo confirmada por outra requisição.",
        {
            "operacaoEmAndamento": (
                "Aguarde o resultado idempotente da operação em andamento",
                "OPERATION_IN_PROGRESS",
                None,
            )
        },
    )
}

AUTHORIZE_UNAVAILABLE_RESPONSE = {
    503: _error_response(
        "Redis ou a confirmação durável está indisponível. A autorização falha fechada.",
        {
            "replayIndisponivel": (
                "Armazenamento de replay indisponível",
                "REPLAY_STORE_UNAVAILABLE",
                None,
            ),
            "desafioIndisponivel": (
                "Armazenamento do desafio indisponível",
                "CHALLENGE_STORE_UNAVAILABLE",
                None,
            ),
            "negativaNaoConfirmada": (
                "Negativa não pôde ser registrada de forma durável",
                "AUTHORIZATION_DENIAL_COMMIT_FAILED",
                None,
            ),
        },
    )
}

BEGIN_UNAVAILABLE_RESPONSE = {
    503: _error_response(
        "O desafio distribuído ou a persistência da expiração está indisponível.",
        {
            "desafioIndisponivel": (
                "Não foi possível criar o desafio de uso único",
                "CHALLENGE_STORE_UNAVAILABLE",
                None,
            ),
            "expiracaoNaoConfirmada": (
                "A expiração não pôde ser persistida com ledger",
                "OFFER_EXPIRATION_COMMIT_FAILED",
                None,
            ),
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
