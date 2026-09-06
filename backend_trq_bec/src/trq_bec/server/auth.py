"""Fronteira de verificação do Firebase ID token e esquema Bearer do OpenAPI."""

from __future__ import annotations

from functools import lru_cache, partial
from typing import Annotated, Protocol

import firebase_admin
import requests
from cachecontrol import CacheControl
from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token

from .config import ServerSettings
from .models import Principal


# Tolerância solicitada para o desvio entre Windows/Docker e Firebase.
# O Admin SDK limita seu parâmetro a 60 s; somente falhas de tempo passam pela
# segunda verificação assinada com google-auth, que aceita os 300 s completos.
FIREBASE_ID_TOKEN_CLOCK_SKEW_SECONDS = 300
FIREBASE_ADMIN_CLOCK_SKEW_SECONDS = 60


@lru_cache(maxsize=1)
def _firebase_certificate_request():
    # Respeita o Cache-Control das chaves públicas e limita a espera de rede.
    session = CacheControl(requests.Session())
    return partial(GoogleAuthRequest(session=session), timeout=10)


def _verify_firebase_id_token(bearer_token: str, *, check_revoked: bool) -> dict:
    try:
        return auth.verify_id_token(
            bearer_token,
            check_revoked=check_revoked,
            clock_skew_seconds=FIREBASE_ADMIN_CLOCK_SKEW_SECONDS,
        )
    except auth.InvalidIdTokenError as exc:
        # O SDK já validou algoritmo, kid, projeto, emissor e sub antes desta
        # falha. Outros erros nunca habilitam a tolerância adicional.
        if not isinstance(exc.cause, ValueError) or not str(exc.cause).startswith(
            ("Token used too early,", "Token expired,")
        ):
            raise

    claims = dict(id_token.verify_firebase_token(
        bearer_token,
        request=_firebase_certificate_request(),
        audience=firebase_admin.get_app().project_id,
        clock_skew_in_seconds=FIREBASE_ID_TOKEN_CLOCK_SKEW_SECONDS,
    ))
    claims["uid"] = claims["sub"]
    if check_revoked:
        # Mesma regra do Firebase Admin 7: revogação compara iat com o marco
        # da conta, sem aplicar tolerância à revogação ou a contas desativadas.
        user = auth.get_user(claims["uid"])
        if user.disabled:
            raise auth.UserDisabledError("The user record is disabled.")
        if claims["iat"] * 1000 < user.tokens_valid_after_timestamp:
            raise auth.RevokedIdTokenError("The Firebase ID token has been revoked.")
    return claims


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
            claims = _verify_firebase_id_token(
                bearer_token,
                check_revoked=self.settings.firebase_check_revoked,
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
