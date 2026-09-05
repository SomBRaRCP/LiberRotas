"""Fronteira de verificação do Firebase ID token e esquema Bearer do OpenAPI."""

from __future__ import annotations

from typing import Annotated, Protocol

import firebase_admin
from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials

from .config import ServerSettings
from .models import Principal


# O Firebase Admin aceita no máximo 60 segundos. Mantemos uma janela curta para
# absorver a diferença de relógio entre Windows, Docker Desktop e os servidores
# do Firebase durante o login imediato. Em máquinas Windows sem sincronização
# NTP ativa, observamos tokens emitidos 11 segundos à frente do relógio local;
# 30 segundos cobre esse desvio sem desativar a validação nem a revogação.
FIREBASE_ID_TOKEN_CLOCK_SKEW_SECONDS = 30


firebase_id_token = HTTPBearer(
    scheme_name="FirebaseIDToken",
    bearerFormat="Firebase ID token (JWT)",
    description=(
        "Firebase ID token emitido para o usuário autenticado do LiberRotas. "
        "Cole somente o valor do token; a Swagger UI acrescenta o prefixo `Bearer` automaticamente."
    ),
    auto_error=False,
)


class Authenticator(Protocol):
    def verify(self, bearer_token: str) -> Principal: ...


class FirebaseAuthenticator:
    def __init__(self, settings: ServerSettings) -> None:
        self.settings = settings
        try:
            firebase_admin.get_app()
            initialized = True
        except ValueError:
            initialized = False
        if not initialized:
            options = {"projectId": settings.firebase_project_id} if settings.firebase_project_id else None
            if settings.firebase_credentials_path:
                credential = credentials.Certificate(str(settings.firebase_credentials_path))
            else:
                credential = credentials.ApplicationDefault()
            firebase_admin.initialize_app(credential, options)

    def verify(self, bearer_token: str) -> Principal:
        try:
            claims = auth.verify_id_token(
                bearer_token,
                check_revoked=self.settings.firebase_check_revoked,
                clock_skew_seconds=FIREBASE_ID_TOKEN_CLOCK_SKEW_SECONDS,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="AUTH_TOKEN_INVALID",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        uid = claims.get("uid") or claims.get("sub")
        if not isinstance(uid, str) or not uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="AUTH_SUBJECT_INVALID",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Somente a Custom Claim fechada `role` participa da autorização. Um
        # campo legado, formulário ou perfil público nunca substitui a claim.
        role = claims.get("role")
        return Principal(
            uid=uid,
            role=role if isinstance(role, str) else None,
            email=claims.get("email") if isinstance(claims.get("email"), str) else None,
            claims=dict(claims),
        )


def extract_bearer(authorization: str | None) -> str:
    """Interpreta um cabeçalho Authorization bruto para clientes externos e testes."""

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="AUTH_BEARER_REQUIRED",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    if not token or len(token) > 8192:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="AUTH_BEARER_INVALID",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def require_principal(
    request: Request,
    credentials_value: Annotated[HTTPAuthorizationCredentials | None, Security(firebase_id_token)],
) -> Principal:
    """Resolve o principal autenticado e publica o esquema Bearer no OpenAPI."""

    if credentials_value is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="AUTH_BEARER_REQUIRED",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials_value.credentials.strip()
    if not token or len(token) > 8192:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="AUTH_BEARER_INVALID",
            headers={"WWW-Authenticate": "Bearer"},
        )
    authenticator: Authenticator = request.app.state.authenticator
    return authenticator.verify(token)
