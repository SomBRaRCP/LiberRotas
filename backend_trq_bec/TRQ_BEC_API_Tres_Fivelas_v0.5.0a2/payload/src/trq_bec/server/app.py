"""Transporte FastAPI do backend TRQ-BEC para o app_LiberRotas."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from .. import __version__
from .auth import Authenticator, require_principal
from .config import ServerSettings, get_settings
from .docs import (
    ADMIN_FORBIDDEN_RESPONSE,
    AUTHENTICATION_RESPONSE,
    AUTHORIZE_NOT_FOUND_RESPONSE,
    AUTHORIZE_UNAVAILABLE_RESPONSE,
    BEGIN_BAD_REQUEST_RESPONSE,
    BEGIN_CONFLICT_RESPONSE,
    BEGIN_EXPIRED_RESPONSE,
    BEGIN_FORBIDDEN_RESPONSE,
    BEGIN_NOT_FOUND_RESPONSE,
    CHECKPOINT_CONFLICT_RESPONSE,
    ENROLL_CONFLICT_RESPONSE,
    INTERNAL_API_DESCRIPTION,
    INTERNAL_OPENAPI_TAGS,
    ISSUE_FORBIDDEN_RESPONSE,
    ISSUE_NOT_FOUND_RESPONSE,
    ISSUE_UNAVAILABLE_RESPONSE,
    PUBLIC_API_DESCRIPTION,
    PUBLIC_OPENAPI_TAGS,
    SWAGGER_UI_PARAMETERS,
)
from .models import (
    AuthorizationResponse,
    AuthorizeRedemptionRequest,
    BeginRedemptionRequest,
    BeginRedemptionResponse,
    CryptoHealthResponse,
    EnrollDeviceRequest,
    EnrollDeviceResponse,
    HealthResponse,
    IssueCouponRequest,
    IssueCouponResponse,
    LedgerCheckpointResponse,
    Principal,
)
from .runtime import Runtime, build_runtime
from .service import CouponSecurityService, ServiceError


def create_app(
    settings: ServerSettings | None = None,
    *,
    service_override: CouponSecurityService | None = None,
    authenticator_override: Authenticator | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    documentation_enabled = settings.docs_enabled and settings.environment != "production"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime: Runtime | None = None
        if service_override is not None and authenticator_override is not None:
            app.state.service = service_override
            app.state.authenticator = authenticator_override
            app.state.pqc_provider = service_override.pqc_provider
        else:
            runtime = build_runtime(settings)
            app.state.service = runtime.service
            app.state.authenticator = runtime.authenticator
            app.state.pqc_provider = runtime.pqc_provider
        yield
        if runtime is not None:
            runtime.close()

    # As interfaces são registradas manualmente para separar o contrato público do administrativo.
    app = FastAPI(
        title="TRQ-BEC LiberRotas API",
        summary="Fronteira autoritativa de segurança para emissão e resgate de cupons.",
        description=PUBLIC_API_DESCRIPTION,
        version=__version__,
        contact={"name": "Equipe TRQ-BEC / LiberRotas"},
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["authorization", "content-type", "x-request-id"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["x-request-id"] = request_id[:128]
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["cache-control"] = "no-store"
        response.headers["referrer-policy"] = "no-referrer"
        return response

    @app.exception_handler(ServiceError)
    async def service_error_handler(_: Request, exc: ServiceError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
            headers={"cache-control": "no-store"},
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(_: Request, exc: HTTPException):
        code = exc.detail if isinstance(exc.detail, str) else "HTTP_ERROR"
        headers = dict(exc.headers or {})
        headers["cache-control"] = "no-store"
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "message": code},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
            headers={"cache-control": "no-store"},
        )

    def service(request: Request) -> CouponSecurityService:
        return request.app.state.service

    @app.get(
        "/health/",
        response_model=HealthResponse,
        tags=["Saúde e prontidão"],
        summary="Verificar a saúde da infraestrutura",
        description=(
            "Confirma conectividade com PostgreSQL e Redis e informa se a camada criptográfica "
            "pós-quântica está pronta. Endpoint público para sondas operacionais."
        ),
        operation_id="getInfrastructureHealth",
        response_description="Estado consolidado da infraestrutura.",
    )
    def health(request: Request) -> HealthResponse:
        return service(request).health()

    @app.get(
        "/health/crypto",
        response_model=CryptoHealthResponse,
        tags=["Saúde e prontidão"],
        summary="Verificar o provider criptográfico",
        description=(
            "Expõe identidade, aprovação, autoteste e suporte algorítmico do provider. "
            "`ready=false` mantém os fluxos pós-quânticos bloqueados por construção."
        ),
        operation_id="getCryptoProviderHealth",
        response_description="Estado detalhado do provider criptográfico.",
    )
    def crypto_health(request: Request) -> CryptoHealthResponse:
        status_value = request.app.state.pqc_provider.status()
        return CryptoHealthResponse(
            provider=status_value.name,
            version=status_value.version,
            approved=status_value.approved,
            self_test_passed=status_value.self_test_passed,
            ml_kem_768=status_value.ml_kem_768,
            ml_dsa_65=status_value.ml_dsa_65,
            ready=status_value.ready,
        )

    @app.post(
        "/v1/trq-bec/devices/enroll",
        response_model=EnrollDeviceResponse,
        tags=["Dispositivos"],
        summary="Cadastrar uma chave de dispositivo",
        description=(
            "Vincula a chave pública do dispositivo ao sujeito autenticado pelo Firebase. "
            "O cadastro é idempotente para a mesma identidade e falha com conflito quando há tentativa de reatribuição."
        ),
        operation_id="enrollDevice",
        response_description="Dispositivo cadastrado ou já cadastrado para o mesmo sujeito.",
        responses={**AUTHENTICATION_RESPONSE, **ENROLL_CONFLICT_RESPONSE},
    )
    def enroll_device(
        payload: EnrollDeviceRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> EnrollDeviceResponse:
        return service(request).enroll_device(principal, payload)

    @app.post(
        "/v1/trq-bec/coupons/issue",
        response_model=IssueCouponResponse,
        tags=["Cupons"],
        summary="Emitir um cupom protegido",
        description=(
            "Emite o envelope e o payload compacto de QR para um cupom ativo pertencente ao empreendedor. "
            "Exige claim `role=entrepreneur`, vínculo entre `issuer_id` e o Firebase UID e dispositivo previamente cadastrado."
        ),
        operation_id="issueCoupon",
        response_description="Payload compacto para QR e prazo de validade do envelope.",
        responses={
            **AUTHENTICATION_RESPONSE,
            **ISSUE_FORBIDDEN_RESPONSE,
            **ISSUE_NOT_FOUND_RESPONSE,
            **ISSUE_UNAVAILABLE_RESPONSE,
        },
    )
    def issue_coupon(
        payload: IssueCouponRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> IssueCouponResponse:
        return service(request).issue_coupon(principal, payload)

    @app.post(
        "/v1/trq-bec/coupons/redeem/begin",
        response_model=BeginRedemptionResponse,
        tags=["Resgate"],
        summary="Iniciar o resgate e emitir um desafio",
        description=(
            "Valida o vínculo do QR, o estado do token e o dispositivo do visitante. "
            "Cria uma operação, uma sessão e um desafio de uso único, retornando a mensagem exata que deverá ser assinada no dispositivo."
        ),
        operation_id="beginCouponRedemption",
        response_description="Operação pendente, desafio de frescor e mensagem para prova de posse.",
        responses={
            **AUTHENTICATION_RESPONSE,
            **BEGIN_BAD_REQUEST_RESPONSE,
            **BEGIN_FORBIDDEN_RESPONSE,
            **BEGIN_NOT_FOUND_RESPONSE,
            **BEGIN_CONFLICT_RESPONSE,
            **BEGIN_EXPIRED_RESPONSE,
        },
    )
    def begin_redemption(
        payload: BeginRedemptionRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> BeginRedemptionResponse:
        return service(request).begin_redemption(principal, payload)

    @app.post(
        "/v1/trq-bec/coupons/redeem/authorize",
        response_model=AuthorizationResponse,
        tags=["Resgate"],
        summary="Autorizar o resgate mediante prova de posse",
        description=(
            "Consome o desafio de uso único, valida a assinatura do dispositivo, reserva replay de forma distribuída, "
            "executa os gates criptográficos e aplica a política determinística. Repetições da mesma operação são idempotentes."
        ),
        operation_id="authorizeCouponRedemption",
        response_description="Decisão autoritativa e referência de evidência no ledger.",
        responses={
            **AUTHENTICATION_RESPONSE,
            **AUTHORIZE_NOT_FOUND_RESPONSE,
            **AUTHORIZE_UNAVAILABLE_RESPONSE,
        },
    )
    def authorize_redemption(
        payload: AuthorizeRedemptionRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> AuthorizationResponse:
        return service(request).authorize_redemption(principal, payload)

    @app.post(
        "/internal/v1/ledger/checkpoint",
        response_model=LedgerCheckpointResponse,
        tags=["Operações internas"],
        summary="Criar um checkpoint assinado do ledger",
        description=(
            "Operação administrativa que cobre a cadeia append-only atual, vincula a versão de política "
            "e assina o hash raiz com a chave de checkpoint. Exige custom claim `admin=true`."
        ),
        operation_id="createLedgerCheckpoint",
        response_description="Checkpoint persistido e assinado.",
        responses={
            **AUTHENTICATION_RESPONSE,
            **ADMIN_FORBIDDEN_RESPONSE,
            **CHECKPOINT_CONFLICT_RESPONSE,
        },
        include_in_schema=True,
    )
    def create_checkpoint(
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> LedgerCheckpointResponse:
        return LedgerCheckpointResponse.model_validate(service(request).checkpoint(principal))

    schema_cache: dict[str, dict[str, Any]] = {}

    def _build_schema(scope: str) -> dict[str, Any]:
        cached = schema_cache.get(scope)
        if cached is not None:
            return cached

        internal = scope == "internal"
        selected_routes = [
            route
            for route in app.routes
            if isinstance(route, APIRoute)
            and route.include_in_schema
            and route.path.startswith("/internal/") is internal
        ]
        schema = get_openapi(
            title=(
                "TRQ-BEC LiberRotas API — Contrato administrativo"
                if internal
                else "TRQ-BEC LiberRotas API"
            ),
            version=__version__,
            openapi_version=app.openapi_version,
            summary=(
                "Operações administrativas de integridade do ledger."
                if internal
                else "Fronteira autoritativa de segurança para emissão e resgate de cupons."
            ),
            description=INTERNAL_API_DESCRIPTION if internal else PUBLIC_API_DESCRIPTION,
            routes=selected_routes,
            tags=INTERNAL_OPENAPI_TAGS if internal else PUBLIC_OPENAPI_TAGS,
            contact={"name": "Equipe TRQ-BEC / LiberRotas"},
            separate_input_output_schemas=app.separate_input_output_schemas,
        )
        schema_cache[scope] = schema
        return schema

    def public_openapi() -> dict[str, Any]:
        return _build_schema("public")

    def internal_openapi() -> dict[str, Any]:
        return _build_schema("internal")

    # Mantém app.openapi() como contrato público para compatibilidade com ferramentas e exportadores.
    app.openapi = public_openapi  # type: ignore[method-assign]
    app.state.public_openapi = public_openapi
    app.state.internal_openapi = internal_openapi

    if documentation_enabled:

        @app.get("/openapi.json", include_in_schema=False)
        def public_openapi_json():
            return JSONResponse(public_openapi())

        @app.get("/docs", include_in_schema=False)
        def public_swagger_ui():
            return get_swagger_ui_html(
                openapi_url="/openapi.json",
                title="TRQ-BEC LiberRotas API — Swagger UI",
                swagger_ui_parameters=SWAGGER_UI_PARAMETERS,
            )

        @app.get("/redoc", include_in_schema=False)
        def public_redoc():
            return get_redoc_html(
                openapi_url="/openapi.json",
                title="TRQ-BEC LiberRotas API — ReDoc",
            )

        @app.get("/internal/openapi.json", include_in_schema=False)
        def internal_openapi_json():
            return JSONResponse(internal_openapi())

        @app.get("/internal/docs", include_in_schema=False)
        def internal_swagger_ui():
            return get_swagger_ui_html(
                openapi_url="/internal/openapi.json",
                title="TRQ-BEC LiberRotas — Swagger administrativo",
                swagger_ui_parameters=SWAGGER_UI_PARAMETERS,
            )

        @app.get("/internal/redoc", include_in_schema=False)
        def internal_redoc():
            return get_redoc_html(
                openapi_url="/internal/openapi.json",
                title="TRQ-BEC LiberRotas — ReDoc administrativo",
            )

    return app


app = create_app()
