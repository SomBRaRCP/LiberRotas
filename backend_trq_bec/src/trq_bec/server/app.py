"""Transporte FastAPI do backend TRQ-BEC para o app_LiberRotas."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Callable, Literal

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.routing import APIRoute

from .. import __version__
from .account_cleanup import delete_account_documents
from .auth import Authenticator, require_principal
from .config import ServerSettings, get_settings
from .docs import (
    ADMIN_FORBIDDEN_RESPONSE,
    AUTHENTICATION_RESPONSE,
    CHECKPOINT_CONFLICT_RESPONSE,
    ENROLL_CONFLICT_RESPONSE,
    ENROLL_FORBIDDEN_RESPONSE,
    ENROLL_LIMIT_RESPONSE,
    INTERNAL_API_DESCRIPTION,
    INTERNAL_OPENAPI_TAGS,
    PUBLIC_API_DESCRIPTION,
    PUBLIC_OPENAPI_TAGS,
    SWAGGER_UI_PARAMETERS,
)
from .models import (
    AccountDeletionPreparationResponse,
    AccountDeviceListResponse,
    AccessAccountStatusRequest,
    AccessAccountSummaryResponse,
    AccessSessionResponse,
    AdminAccountListResponse,
    AdminOperationsSummaryResponse,
    CryptoHealthResponse,
    EnrollDeviceRequest,
    EnrollDeviceResponse,
    DeviceApprovalRequest,
    DeviceApprovalResponse,
    DeviceApprovalResendRequest,
    DeviceApprovalResendResponse,
    EmailVerificationQueueResponse,
    HealthResponse,
    InstitutionCreateRequest,
    InstitutionApplicationListResponse,
    InstitutionApplicationResponse,
    InstitutionApplicationStatusUpdateRequest,
    InstitutionListResponse,
    InstitutionResponse,
    LedgerCheckpointResponse,
    MediaAssetListResponse,
    MediaAssetResponse,
    MediaCleanupResponse,
    MediaUploadAuthorizationResponse,
    MediaUploadCreateRequest,
    MerchantResponse,
    MerchantStatusRequest,
    Principal,
    PublicRegistrationRequest,
    PublicInstitutionApplicationCreateRequest,
    PublicInstitutionApplicationCreatedResponse,
    RevokeAllDevicesResponse,
    SecurityAccountListResponse,
    SecurityMonitoringSummaryResponse,
    ServerTimeResponse,
    StaffAccountCreateRequest,
    StaffAccountValidationRequest,
    SupportAccountListResponse,
    TrqBecSecurityStatusResponse,
)
from .runtime import Runtime, build_runtime
from .routers.community import router as community_router
from .routers.coupons import router as coupons_router
from .routers.directory import router as directory_router
from .routers.institutions import router as institutions_router
from .routers.marketplace import router as marketplace_router
from .routers.messaging import router as messaging_router
from .routers.support import router as support_router
from .service import CouponSecurityService, ServiceError


logger = logging.getLogger(__name__)


def create_app(
    settings: ServerSettings | None = None,
    *,
    service_override: CouponSecurityService | None = None,
    authenticator_override: Authenticator | None = None,
    account_cleanup_override: Callable[[str], int] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    documentation_enabled = settings.docs_enabled and settings.environment != "production"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime: Runtime | None = None
        email_queue_stop = asyncio.Event()
        email_queue_task: asyncio.Task[None] | None = None
        if service_override is not None and authenticator_override is not None:
            app.state.service = service_override
            app.state.authenticator = authenticator_override
            app.state.pqc_provider = service_override.pqc_provider
        else:
            runtime = build_runtime(settings)
            app.state.service = runtime.service
            app.state.authenticator = runtime.authenticator
            app.state.pqc_provider = runtime.pqc_provider
        app.state.account_cleanup = account_cleanup_override or delete_account_documents

        async def process_email_queue() -> None:
            while not email_queue_stop.is_set():
                try:
                    await asyncio.to_thread(
                        app.state.service.process_email_verification_queue,
                        10,
                    )
                except Exception:
                    logger.exception("Falha ao processar a fila de verificacao de e-mail")
                try:
                    await asyncio.wait_for(email_queue_stop.wait(), timeout=5)
                except TimeoutError:
                    continue

        email_queue_task = asyncio.create_task(process_email_queue())
        try:
            yield
        finally:
            email_queue_stop.set()
            if email_queue_task is not None:
                await email_queue_task
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
        allow_methods=["DELETE", "GET", "PATCH", "POST", "PUT"],
        allow_headers=["authorization", "content-type", "x-request-id"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id[:128]
        response = await call_next(request)
        response.headers["x-request-id"] = request_id[:128]
        response.headers["x-content-type-options"] = "nosniff"
        public_media_path = request.url.path.startswith("/v1/public/media/")
        public_avatar_path = (
            request.url.path.startswith("/v1/public/profile/")
            and request.url.path.endswith("/avatar")
        )
        cacheable_media_redirect = (
            response.status_code == 307
            and (public_media_path or public_avatar_path)
            and "cache-control" in response.headers
        )
        if not cacheable_media_redirect:
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
        def without_input(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    key: without_input(item)
                    for key, item in value.items()
                    if key != "input"
                }
            if isinstance(value, list):
                return [without_input(item) for item in value]
            if isinstance(value, tuple):
                return [without_input(item) for item in value]
            return value

        return JSONResponse(
            status_code=422,
            content=jsonable_encoder({"detail": without_input(exc.errors())}),
            headers={"cache-control": "no-store"},
        )

    def service(request: Request) -> CouponSecurityService:
        return request.app.state.service

    def media_request_context(request: Request) -> dict[str, str | None]:
        return {
            "request_id": getattr(request.state, "request_id", ""),
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }

    app.include_router(community_router)
    app.include_router(coupons_router)
    app.include_router(directory_router)
    app.include_router(institutions_router)
    app.include_router(marketplace_router)
    app.include_router(messaging_router)
    app.include_router(support_router)

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
        "/v1/time",
        response_model=ServerTimeResponse,
        tags=["Saúde e prontidão"],
        summary="Consultar o relógio UTC do backend",
        description="Fonte pública de horário para exibição e contagens regressivas do cliente.",
        operation_id="getServerTime",
    )
    def server_time(request: Request) -> ServerTimeResponse:
        return service(request).server_time()

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

    @app.get(
        "/v1/access/me",
        response_model=AccessSessionResponse,
        tags=["Conta"],
        summary="Resolver o acesso da conta autenticada",
        description=(
            "Valida o Firebase ID Token, lê a Custom Claim, carrega função, status e "
            "permissões no PostgreSQL e retorna somente o painel autorizado. Não recebe role "
            "em corpo, formulário, query string ou parâmetro de rota."
        ),
        operation_id="resolveAuthenticatedAccess",
        responses=AUTHENTICATION_RESPONSE,
    )
    def resolve_authenticated_access(
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> AccessSessionResponse:
        return service(request).resolve_access(principal)

    @app.post(
        "/v1/access/public-registration",
        response_model=EmailVerificationQueueResponse,
        status_code=202,
        tags=["Conta"],
        summary="Concluir o cadastro público e verificar e-mail quando necessário",
        description=(
            "Permite somente visitor ou entrepreneur para o próprio UID autenticado. "
            "Visitante entra sem verificação cadastral e recebe somente o alerta de "
            "novo dispositivo; empreendedor permanece pendente até confirmar o e-mail. "
            "Funções administrativas, de suporte, segurança e instituição nunca são aceitas."
        ),
        operation_id="registerPublicAccount",
        responses=AUTHENTICATION_RESPONSE,
    )
    def register_public_account(
        payload: PublicRegistrationRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> EmailVerificationQueueResponse:
        return service(request).register_public_account(principal, payload)

    @app.post(
        "/v1/public/institution-applications",
        response_model=PublicInstitutionApplicationCreatedResponse,
        status_code=201,
        tags=["Conta"],
        summary="Enviar interesse público em uma conta institucional",
        description=(
            "Recebe dados de contato para análise do Suporte. Esta operação não cria "
            "identidade Firebase, conta, função ou permissão institucional."
        ),
        operation_id="createPublicInstitutionApplication",
    )
    def create_public_institution_application(
        payload: PublicInstitutionApplicationCreateRequest,
        request: Request,
    ) -> PublicInstitutionApplicationCreatedResponse:
        source_ref = request.client.host if request.client else "unavailable"
        return service(request).create_public_institution_application(
            payload,
            source_ref,
        )

    @app.post(
        "/v1/access/email-verification/resend",
        response_model=EmailVerificationQueueResponse,
        status_code=202,
        tags=["Conta"],
        summary="Reenfileirar a verificação do próprio e-mail",
        operation_id="resendPublicEmailVerification",
        responses=AUTHENTICATION_RESPONSE,
    )
    def resend_public_email_verification(
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> EmailVerificationQueueResponse:
        return service(request).resend_public_email_verification(principal)

    @app.post(
        "/v1/admin/institutions",
        response_model=InstitutionResponse,
        status_code=201,
        tags=["Administracao"],
        summary="Provisionar uma conta institucional",
        description=(
            "Exige admin.institutions.manage e autenticacao recente. A funcao institution "
            "e definida exclusivamente pelo backend."
        ),
        operation_id="createInstitutionAccount",
        responses=AUTHENTICATION_RESPONSE,
    )
    def create_institution(
        payload: InstitutionCreateRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> InstitutionResponse:
        return service(request).create_institution(principal, payload)

    @app.post(
        "/v1/support/institutions",
        response_model=InstitutionResponse,
        status_code=201,
        tags=["Suporte"],
        summary="Provisionar uma conta institucional pelo suporte",
        description=(
            "Exige support.institutions.create e autenticacao recente. A funcao institution "
            "e definida exclusivamente pelo backend; role, permissoes e senha nao fazem parte "
            "do contrato aceito."
        ),
        operation_id="createInstitutionAccountBySupport",
        responses=AUTHENTICATION_RESPONSE,
    )
    def create_support_institution(
        payload: InstitutionCreateRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> InstitutionResponse:
        return service(request).create_support_institution(principal, payload)

    @app.get(
        "/v1/admin/institutions",
        response_model=InstitutionListResponse,
        tags=["Administracao"],
        summary="Listar contas institucionais",
        operation_id="listInstitutionAccounts",
        responses=AUTHENTICATION_RESPONSE,
    )
    def list_institutions(
        request: Request,
        limit: int = Query(default=100, ge=1, le=200),
        principal: Principal = Depends(require_principal),
    ) -> InstitutionListResponse:
        return service(request).list_institutions(principal, limit)

    @app.get(
        "/v1/admin/accounts",
        response_model=AdminAccountListResponse,
        tags=["Administracao"],
        summary="Listar contas e permissoes autorizadas",
        operation_id="listAdminAccounts",
        responses=AUTHENTICATION_RESPONSE,
    )
    def list_admin_accounts(
        request: Request,
        limit: int = Query(default=100, ge=1, le=200),
        principal: Principal = Depends(require_principal),
    ) -> AdminAccountListResponse:
        return service(request).list_admin_accounts(principal, limit)

    @app.post(
        "/v1/admin/staff-accounts",
        response_model=AccessAccountSummaryResponse,
        status_code=201,
        tags=["Administracao"],
        summary="Criar uma conta de equipe pendente",
        description=(
            "Cria somente admin, suporte ou seguranca usando pacotes fechados de "
            "permissoes. A conta permanece sem acesso ate confirmar o e-mail e "
            "ser validada por um administrador autenticado recentemente."
        ),
        operation_id="createStaffAccount",
        responses=AUTHENTICATION_RESPONSE,
    )
    def create_staff_account(
        payload: StaffAccountCreateRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> AccessAccountSummaryResponse:
        return service(request).create_staff_account(principal, payload)

    @app.get(
        "/v1/admin/staff-accounts",
        response_model=AdminAccountListResponse,
        tags=["Administracao"],
        summary="Listar contas oficiais e convites de equipe",
        operation_id="listStaffAccounts",
        responses=AUTHENTICATION_RESPONSE,
    )
    def list_staff_accounts(
        request: Request,
        limit: int = Query(default=100, ge=1, le=200),
        principal: Principal = Depends(require_principal),
    ) -> AdminAccountListResponse:
        return service(request).list_staff_accounts(principal, limit)

    @app.post(
        "/v1/admin/staff-accounts/{uid}/validate",
        response_model=AccessAccountSummaryResponse,
        tags=["Administracao"],
        summary="Validar uma conta de equipe pendente",
        description=(
            "Exige autenticação recente, e-mail confirmado no Firebase e motivo. "
            "Somente depois desta operação o backend ativa a conta, aplica a claim "
            "de validação e revoga sessões anteriores."
        ),
        operation_id="validateStaffAccount",
        responses=AUTHENTICATION_RESPONSE,
    )
    def validate_staff_account(
        payload: StaffAccountValidationRequest,
        request: Request,
        uid: str = Path(min_length=1, max_length=128),
        principal: Principal = Depends(require_principal),
    ) -> AccessAccountSummaryResponse:
        return service(request).validate_staff_account(
            principal,
            uid,
            payload,
        )

    @app.get(
        "/v1/admin/operations/summary",
        response_model=AdminOperationsSummaryResponse,
        tags=["Administracao"],
        summary="Consultar o resumo operacional sem segredos",
        operation_id="getAdminOperationsSummary",
        responses=AUTHENTICATION_RESPONSE,
    )
    def admin_operations_summary(
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> AdminOperationsSummaryResponse:
        return service(request).admin_operations_summary(principal)

    @app.get(
        "/v1/support/accounts",
        response_model=SupportAccountListResponse,
        tags=["Suporte"],
        summary="Consultar contas em modo somente leitura",
        operation_id="listSupportAccounts",
        responses=AUTHENTICATION_RESPONSE,
    )
    def list_support_accounts(
        request: Request,
        limit: int = Query(default=100, ge=1, le=200),
        principal: Principal = Depends(require_principal),
    ) -> SupportAccountListResponse:
        return service(request).list_support_accounts(principal, limit)

    @app.get(
        "/v1/security/accounts",
        response_model=SecurityAccountListResponse,
        tags=["Seguranca"],
        summary="Consultar contas e eventos de acesso recentes",
        operation_id="listSecurityAccounts",
        responses=AUTHENTICATION_RESPONSE,
    )
    def list_security_accounts(
        request: Request,
        limit: int = Query(default=100, ge=1, le=200),
        events_limit: int = Query(default=50, ge=1, le=200),
        principal: Principal = Depends(require_principal),
    ) -> SecurityAccountListResponse:
        return service(request).list_security_accounts(principal, limit, events_limit)

    @app.get(
        "/v1/security/monitoring/summary",
        response_model=SecurityMonitoringSummaryResponse,
        tags=["Seguranca"],
        summary="Consultar monitoramento agregado da plataforma",
        operation_id="getSecurityMonitoringSummary",
        responses=AUTHENTICATION_RESPONSE,
    )
    def security_monitoring_summary(
        request: Request,
        events_limit: int = Query(default=10, ge=1, le=50),
        principal: Principal = Depends(require_principal),
    ) -> SecurityMonitoringSummaryResponse:
        return service(request).security_monitoring_summary(principal, events_limit)

    @app.get(
        "/v1/security/trq-bec/status",
        response_model=TrqBecSecurityStatusResponse,
        tags=["Seguranca"],
        summary="Acompanhar os controles do TRQ-BEC",
        description=(
            "Exibe somente telemetria sanitizada: política, saúde dos serviços, "
            "ledger, contas privilegiadas, dispositivos e filas. Nenhuma chave, "
            "token, senha ou dado criptográfico privado é retornado."
        ),
        operation_id="getTrqBecSecurityStatus",
        responses=AUTHENTICATION_RESPONSE,
    )
    def trq_bec_security_status(
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> TrqBecSecurityStatusResponse:
        return service(request).trq_bec_security_status(principal)

    @app.post(
        "/v1/security/accounts/{uid}/status",
        response_model=AccessAccountSummaryResponse,
        tags=["Seguranca"],
        summary="Suspender ou reativar uma conta nao protegida",
        description=(
            "Exige security.incidents.manage e autenticacao recente. Nao altera funcao ou permissoes."
        ),
        operation_id="updateSecurityAccountStatus",
        responses=AUTHENTICATION_RESPONSE,
    )
    def update_security_account_status(
        payload: AccessAccountStatusRequest,
        request: Request,
        uid: str = Path(min_length=1, max_length=128),
        principal: Principal = Depends(require_principal),
    ) -> AccessAccountSummaryResponse:
        return service(request).update_security_account_status(principal, uid, payload)

    @app.get(
        "/v1/support/institution-applications",
        response_model=InstitutionApplicationListResponse,
        tags=["Suporte"],
        summary="Listar solicitações públicas de instituição",
        operation_id="listInstitutionApplications",
        responses=AUTHENTICATION_RESPONSE,
    )
    def list_institution_applications(
        request: Request,
        status: Literal["NEW", "IN_REVIEW", "CONTACTED", "APPROVED", "REJECTED"] | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=200),
        principal: Principal = Depends(require_principal),
    ) -> InstitutionApplicationListResponse:
        return service(request).list_institution_applications(principal, status, limit)

    @app.patch(
        "/v1/support/institution-applications/{application_id}",
        response_model=InstitutionApplicationResponse,
        tags=["Suporte"],
        summary="Registrar a análise de uma solicitação institucional",
        operation_id="updateInstitutionApplicationStatus",
        responses=AUTHENTICATION_RESPONSE,
    )
    def update_institution_application_status(
        payload: InstitutionApplicationStatusUpdateRequest,
        request: Request,
        application_id: uuid.UUID,
        principal: Principal = Depends(require_principal),
    ) -> InstitutionApplicationResponse:
        return service(request).update_institution_application_status(
            principal,
            application_id,
            payload,
        )

    @app.post(
        "/v1/media/uploads",
        response_model=MediaUploadAuthorizationResponse,
        status_code=201,
        tags=["Midia"],
        summary="Autorizar o envio direto de uma imagem",
        description=(
            "Valida conta, entidade, tipo e tamanho antes de emitir uma URL V4 "
            "temporaria. O token Firebase nunca e enviado ao armazenamento."
        ),
        operation_id="createMediaUpload",
        responses=AUTHENTICATION_RESPONSE,
    )
    def create_media_upload(
        payload: MediaUploadCreateRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> MediaUploadAuthorizationResponse:
        return service(request).create_media_upload(
            principal,
            payload,
            **media_request_context(request),
        )

    @app.post(
        "/v1/media/uploads/{media_id}/confirm",
        response_model=MediaAssetResponse,
        tags=["Midia"],
        summary="Confirmar, validar e processar uma imagem enviada",
        operation_id="confirmMediaUpload",
        responses=AUTHENTICATION_RESPONSE,
    )
    def confirm_media_upload(
        request: Request,
        media_id: str = Path(
            pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        ),
        principal: Principal = Depends(require_principal),
    ) -> MediaAssetResponse:
        return service(request).confirm_media_upload(
            principal,
            media_id,
            **media_request_context(request),
        )

    @app.get(
        "/v1/media",
        response_model=MediaAssetListResponse,
        tags=["Midia"],
        summary="Listar imagens prontas de uma entidade",
        operation_id="listEntityMedia",
        responses=AUTHENTICATION_RESPONSE,
    )
    def list_media_assets(
        request: Request,
        entity_type: str = Query(
            pattern=(
                r"^(user|entrepreneur|product|post|fair|institution|support)$"
            )
        ),
        entity_id: str = Query(
            min_length=1,
            max_length=160,
            pattern=r"^[A-Za-z0-9:_-]+$",
        ),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=10000),
        principal: Principal = Depends(require_principal),
    ) -> MediaAssetListResponse:
        return service(request).list_media_assets(
            principal,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
            offset=offset,
        )

    @app.get(
        "/v1/public/media/entities/{entity_type}/{entity_id}/{media_role}",
        response_class=RedirectResponse,
        tags=["Midia"],
        summary="Abrir a imagem publica atual de uma entidade",
        description=(
            "Seleciona a imagem pronta mais recente da entidade e redireciona "
            "para uma variante processada temporaria."
        ),
        operation_id="openCurrentPublicEntityMedia",
    )
    def open_current_public_entity_media(
        request: Request,
        entity_type: Literal["product", "fair", "institution"] = Path(),
        entity_id: str = Path(
            min_length=1,
            max_length=160,
            pattern=r"^[A-Za-z0-9:_-]+$",
        ),
        media_role: Literal[
            "product_image",
            "fair_cover",
            "institution_logo",
        ] = Path(),
        variant: Literal["thumbnail", "display"] = Query(default="thumbnail"),
    ) -> RedirectResponse:
        max_age = max(
            0,
            min(60, settings.gcs_download_url_expiration_seconds - 30),
        )
        return RedirectResponse(
            url=service(request).get_public_entity_media_download_url(
                entity_type,
                entity_id,
                media_role,
                variant,
            ),
            status_code=307,
            headers={
                "Cache-Control": f"public, max-age={max_age}, stale-while-revalidate=30",
                "Referrer-Policy": "no-referrer",
            },
        )

    @app.get(
        "/v1/public/media/{media_id}",
        response_class=RedirectResponse,
        tags=["Midia"],
        summary="Abrir uma imagem publica processada",
        description=(
            "Redireciona uma referencia publica estavel para uma URL temporaria "
            "do armazenamento. Midias privadas, pendentes ou rejeitadas retornam 404."
        ),
        operation_id="openPublicMediaAsset",
    )
    def open_public_media_asset(
        request: Request,
        media_id: str = Path(
            pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        ),
        variant: Literal["thumbnail", "display"] | None = Query(default=None),
    ) -> RedirectResponse:
        max_age = max(
            0,
            min(240, settings.gcs_download_url_expiration_seconds - 30),
        )
        return RedirectResponse(
            url=service(request).get_public_media_download_url(media_id, variant),
            status_code=307,
            headers={
                "Cache-Control": f"public, max-age={max_age}, stale-while-revalidate=60",
                "Referrer-Policy": "no-referrer",
            },
        )

    @app.get(
        "/v1/public/profile/{uid}/avatar",
        response_class=RedirectResponse,
        tags=["Diretorio", "Midia"],
        summary="Abrir o avatar publico atual de um perfil",
        operation_id="openCurrentPublicProfileAvatar",
    )
    def open_current_public_profile_avatar(
        request: Request,
        uid: str = Path(min_length=1, max_length=128),
        variant: Literal["thumbnail", "display"] = Query(default="thumbnail"),
    ) -> RedirectResponse:
        max_age = max(
            0,
            min(60, settings.gcs_download_url_expiration_seconds - 30),
        )
        return RedirectResponse(
            url=service(request).get_public_profile_avatar_download_url(uid, variant),
            status_code=307,
            headers={
                "Cache-Control": f"public, max-age={max_age}, stale-while-revalidate=30",
                "Referrer-Policy": "no-referrer",
            },
        )

    @app.get(
        "/v1/media/{media_id}",
        response_model=MediaAssetResponse,
        tags=["Midia"],
        summary="Obter metadados e URL temporaria de uma imagem",
        operation_id="getMediaAsset",
        responses=AUTHENTICATION_RESPONSE,
    )
    def get_media_asset(
        request: Request,
        media_id: str = Path(
            pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        ),
        principal: Principal = Depends(require_principal),
    ) -> MediaAssetResponse:
        return service(request).get_media_asset(principal, media_id)

    @app.delete(
        "/v1/media/{media_id}",
        status_code=204,
        tags=["Midia"],
        summary="Excluir logicamente uma imagem e remover o objeto privado",
        operation_id="deleteMediaAsset",
        responses=AUTHENTICATION_RESPONSE,
    )
    def delete_media_asset(
        request: Request,
        media_id: str = Path(
            pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        ),
        principal: Principal = Depends(require_principal),
    ) -> Response:
        service(request).delete_media_asset(
            principal,
            media_id,
            **media_request_context(request),
        )
        return Response(status_code=204)

    @app.post(
        "/v1/admin/media/cleanup",
        response_model=MediaCleanupResponse,
        tags=["Administracao", "Midia"],
        summary="Limpar uploads pendentes expirados",
        description=(
            "Acao administrativa, autenticada e auditada. Remove somente "
            "objetos ainda nao confirmados cujo prazo ja expirou."
        ),
        operation_id="cleanupExpiredMedia",
        responses=AUTHENTICATION_RESPONSE,
    )
    def cleanup_expired_media(
        request: Request,
        limit: int = Query(default=25, ge=1, le=100),
        principal: Principal = Depends(require_principal),
    ) -> MediaCleanupResponse:
        return service(request).cleanup_expired_media(principal, limit)

    @app.post(
        "/v1/trq-bec/devices/enroll",
        response_model=EnrollDeviceResponse,
        tags=["Dispositivos"],
        summary="Cadastrar uma chave de dispositivo",
        description=(
            "Vincula a chave pública do dispositivo ao sujeito autenticado pelo Firebase. "
            "Visitantes são liberados imediatamente e recebem somente um alerta. "
            "Todo novo aparelho de empreendedor ou instituição passa por dez minutos "
            "de segurança antes da ativação automática."
        ),
        operation_id="enrollDevice",
        response_description="Dispositivo cadastrado ou já cadastrado para o mesmo sujeito.",
        responses={
            **AUTHENTICATION_RESPONSE,
            **ENROLL_FORBIDDEN_RESPONSE,
            **ENROLL_CONFLICT_RESPONSE,
            **ENROLL_LIMIT_RESPONSE,
        },
    )
    def enroll_device(
        payload: EnrollDeviceRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> EnrollDeviceResponse:
        return service(request).enroll_device(principal, payload)

    @app.get(
        "/v1/account/devices",
        response_model=AccountDeviceListResponse,
        tags=["Dispositivos"],
        summary="Listar os dispositivos da conta",
        description=(
            "Lista somente os metadados informativos do proprio titular. "
            "Chaves publicas e tokens de aprovacao nunca sao retornados."
        ),
        operation_id="listAccountDevices",
        responses=AUTHENTICATION_RESPONSE,
    )
    def list_account_devices(
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> AccountDeviceListResponse:
        return service(request).list_account_devices(principal)

    @app.post(
        "/v1/account/devices/approve",
        response_model=DeviceApprovalResponse,
        tags=["Dispositivos"],
        summary="Compatibilidade com links antigos de confirmacao",
        description=(
            "Rota legada mantida temporariamente para links emitidos por versoes "
            "anteriores. Novos alertas nao contem token e a ativacao ocorre "
            "automaticamente depois do periodo de seguranca."
        ),
        deprecated=True,
        operation_id="approveAccountDevice",
        responses=AUTHENTICATION_RESPONSE,
    )
    def approve_account_device(
        payload: DeviceApprovalRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> DeviceApprovalResponse:
        return service(request).approve_account_device(principal, payload)

    @app.post(
        "/v1/account/devices/resend-approval",
        response_model=DeviceApprovalResendResponse,
        tags=["Dispositivos"],
        summary="Reenviar o alerta de novo dispositivo",
        description=(
            "Exige autenticacao recente, aplica cooldown e reenvia o alerta "
            "Nao fui eu ao e-mail do Firebase sem reiniciar os dez minutos."
        ),
        operation_id="resendDeviceApproval",
        responses=AUTHENTICATION_RESPONSE,
    )
    def resend_device_approval(
        payload: DeviceApprovalResendRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> DeviceApprovalResendResponse:
        return service(request).resend_device_approval(principal, payload)

    @app.post(
        "/v1/account/devices/revoke-all",
        response_model=RevokeAllDevicesResponse,
        tags=["Dispositivos"],
        summary="Desconectar todos os dispositivos",
        description=(
            "Exige autenticacao recente, revoga refresh tokens no Firebase e "
            "revoga dispositivos ativos ou pendentes do proprio UID."
        ),
        operation_id="revokeAllAccountDevices",
        responses=AUTHENTICATION_RESPONSE,
    )
    def revoke_all_account_devices(
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> RevokeAllDevicesResponse:
        return service(request).revoke_all_account_devices(principal)

    @app.delete(
        "/v1/account",
        response_model=AccountDeletionPreparationResponse,
        tags=["Conta"],
        summary="Preparar a exclusão definitiva da conta",
        description=(
            "Encerra produtos, ofertas, cupons e chaves ativos e remove os documentos pessoais "
            "do Firestore. O cliente deve apagar o usuário do Firebase Authentication somente após esta confirmação. "
            "Registros técnicos necessários à integridade e à prevenção de fraude são preservados."
        ),
        operation_id="prepareAccountDeletion",
        responses=AUTHENTICATION_RESPONSE,
    )
    def prepare_account_deletion(
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> AccountDeletionPreparationResponse:
        service(request).prepare_account_deletion(principal)
        try:
            deleted_count = request.app.state.account_cleanup(principal.uid)
        except Exception as exc:
            # O encerramento comercial é idempotente; mantendo o Auth, o usuário
            # pode repetir a operação quando o Firestore voltar a responder.
            raise ServiceError("ACCOUNT_FIRESTORE_CLEANUP_FAILED", 503) from exc
        return AccountDeletionPreparationResponse(
            status="READY_FOR_AUTH_DELETION",
            firestore_documents_deleted=deleted_count,
        )

    @app.post(
        "/internal/v1/marketplace/merchants/status",
        response_model=MerchantResponse,
        tags=["Operações internas"],
        summary="Aprovar ou suspender um empreendedor",
        description=(
            "Cria ou atualiza a conta comercial autoritativa vinculada ao Firebase UID. "
            "A claim entrepreneur isolada não basta para emitir ofertas. Exige `admin=true`."
        ),
        operation_id="setMerchantStatus",
        responses={**AUTHENTICATION_RESPONSE, **ADMIN_FORBIDDEN_RESPONSE},
    )
    def set_merchant_status(
        payload: MerchantStatusRequest,
        request: Request,
        principal: Principal = Depends(require_principal),
    ) -> MerchantResponse:
        return service(request).set_merchant_status(principal, payload)

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

    def _route_scope(route: Any) -> str | None:
        """Classifica rotas diretas e routers incluídos sem usar API privada do FastAPI."""
        if isinstance(route, APIRoute):
            return "internal" if route.path.startswith("/internal/") else "public"

        original_router = getattr(route, "original_router", None)
        if original_router is None:
            return None
        child_scopes = {
            child_scope
            for child in original_router.routes
            if (child_scope := _route_scope(child)) is not None
        }
        if len(child_scopes) > 1:
            raise RuntimeError(
                "OPENAPI_ROUTER_SCOPE_MIXED: separe rotas publicas e internas em routers distintos"
            )
        return next(iter(child_scopes), None)

    def _build_schema(scope: str) -> dict[str, Any]:
        cached = schema_cache.get(scope)
        if cached is not None:
            return cached

        internal = scope == "internal"
        selected_routes = [
            route
            for route in app.routes
            if _route_scope(route) == ("internal" if internal else "public")
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
