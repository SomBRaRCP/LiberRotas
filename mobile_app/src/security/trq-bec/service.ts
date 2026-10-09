import Constants from "expo-constants";
import * as Device from "expo-device";
import { signOut } from "firebase/auth";
import { Platform } from "react-native";
import { auth } from "@/services/firebase";
import { createTrqBecHttpClient } from "@/api/http-client";
import { createCommunityApi } from "@/features/community/api";
import { createDirectoryApi } from "@/features/directory/api";
import { createInstitutionsApi } from "@/features/institutions/api";
import { createMarketplaceApi } from "@/features/marketplace/api";
import {
  createMessagingApi,
  createMessagingNormalizers,
} from "@/features/messaging/api";
import { createTrqBecApi } from "@/features/trq-bec/api";
import { base64UrlToBytes } from "./base64";
import { getOrCreateDeviceIdentity, removeDeviceIdentity, signDeviceProof } from "./device-signer";

const API_URL = process.env.EXPO_PUBLIC_TRQ_BEC_API_URL?.trim().replace(/\/+$/, "") || "";
const REQUEST_TIMEOUT_MS = 12_000;
let rejectedSessionCleanup: Promise<void> | null = null;

export type {
  GlobalSearchKind,
  GlobalSearchResult,
  PublicDirectoryProfile,
  PublicDirectoryProfileInput,
  PublicDirectoryRole,
} from "@/features/directory/api";
export type {
  CommunityPostPublishInput,
  CuratedPlacePublishInput,
  LiveFairPublishInput,
  PostComment,
  PostCommentLike,
} from "@/features/community/api";
export type {
  BlockedProfile,
  CreateSupportRequestInput,
  CreateSupportRequestResult,
  MessageConversationDetail,
  MessageConversationSummary,
  MessageDeliveryStatus,
  MessageParticipant,
  PrivateMessage,
  SendPrivateMessageInput,
  SendPrivateMessageResult,
  SupportMessage,
  SupportRequestDetail,
  SupportRequestStatus,
  SupportRequestSummary,
} from "@/features/messaging/api";
export type {
  CreateInstitutionFundedEventInput,
  CreateInstitutionGroupInput,
  EntrepreneurFundedEvent,
  EntrepreneurFundedEventReport,
  FundedEventAllocationMode,
  FundedEventEndMode,
  FundedEventStatus,
  InstitutionFundedEvent,
  InstitutionFundedEventProductAllocation,
  InstitutionFundedEventProductReport,
  InstitutionFundedEventReport,
  InstitutionFundedEventSellerAllocation,
  InstitutionFundedEventSellerReport,
  InstitutionGroup,
  InstitutionMembership,
  InstitutionMembershipStatus,
  InstitutionProfile,
  InstitutionReportsSummary,
  InstitutionSalesCurrencyTotal,
  InstitutionSalesReport,
  InstitutionSellerSales,
  LoadInstitutionSalesReportInput,
  UpdateInstitutionProfileInput,
} from "@/features/institutions/api";
export type { CreateProductInput } from "@/features/marketplace/api";
export { MAX_COMBINED_COUPONS } from "@/features/trq-bec/api";
export type {
  CouponRedemptionGroupFailure,
  CouponRedemptionGroupResult,
  IssueLiveOfferInput,
} from "@/features/trq-bec/api";

type ApiErrorPayload = {
  code?: string;
  message?: string;
  detail?: unknown;
};

type AccountDeletionPreparationResponse = {
  status: "READY_FOR_AUTH_DELETION";
  firestore_documents_deleted: number;
  commercial_data_disabled: boolean;
  security_records_retained: boolean;
};

export type AccessRole = "admin" | "support" | "security" | "institution" | "entrepreneur" | "visitor";
export type AccessState = "AUTHORIZED" | "PENDING" | "SUSPENDED" | "DENIED";
export type AccessPanel = AccessRole | "access_pending";
export type AccessSession = {
  access_state: AccessState;
  role: AccessRole | null;
  panel: AccessPanel;
  permissions: string[];
  reason: string;
};

export type PublicRegistrationInput = {
  role: "entrepreneur" | "visitor";
  displayName: string;
  establishmentName?: string;
};

export type EmailVerificationQueueResult = {
  status: "QUEUED" | "ALREADY_VERIFIED" | "NOT_REQUIRED";
  role: "entrepreneur" | "visitor";
};

export type PublicInstitutionApplicationInput = {
  organizationType: "COMPANY" | "NGO";
  organizationName: string;
  contactName: string;
  email: string;
  phone?: string;
  registrationNumber?: string;
  city: string;
  state: string;
  websiteOrSocial?: string;
  description: string;
};

export type InstitutionApplicationStatus = "NEW" | "IN_REVIEW" | "CONTACTED" | "APPROVED" | "REJECTED";

export type InstitutionApplication = {
  application_id: string;
  organization_type: "COMPANY" | "NGO";
  organization_name: string;
  contact_name: string;
  email: string;
  phone: string | null;
  registration_number: string | null;
  city: string;
  state: string;
  website_or_social: string | null;
  description: string;
  status: InstitutionApplicationStatus;
  support_notes: string | null;
  reviewed_by_uid: string | null;
  provisioned_uid: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type DevicePlatform = "android" | "ios" | "web" | "windows" | "macos" | "linux" | "unknown";
export type AccountDeviceStatus = "ACTIVE" | "PENDING_APPROVAL" | "REVOKED";
export type DeviceNotificationStatus = "NOT_REQUIRED" | "SENT" | "NOT_CONFIGURED" | "FAILED" | "PENDING";

export type CurrentDeviceEnrollment = {
  device_key_id: string;
  status: string;
  key_ref: string;
  is_new_device: boolean;
  is_additional_device: boolean;
  device_status: AccountDeviceStatus;
  notification_status: DeviceNotificationStatus;
};

export type AccountDevice = {
  device_key_id: string;
  key_ref: string;
  device_name: string | null;
  platform: DevicePlatform;
  model_name: string | null;
  app_version: string | null;
  storage_profile: string;
  status: AccountDeviceStatus;
  created_at: string;
  last_seen_at: string | null;
  revoked_at: string | null;
  approval_expires_at: string | null;
  approval_last_sent_at: string | null;
  approved_at: string | null;
  notification_status: DeviceNotificationStatus;
};

export type RevokeAllDevicesResult = {
  status: "ALL_DEVICES_REVOKED";
  revoked_devices: number;
  sessions_revoked: boolean;
};

export type ApproveDeviceResult = {
  status: "DEVICE_APPROVED";
  device_key_id: string;
  device_status: "ACTIVE";
};

export type ResendDeviceApprovalResult = {
  device_key_id: string;
  device_status: "PENDING_APPROVAL";
  notification_status: DeviceNotificationStatus;
};

export type ManagedAccountStatus = "ACTIVE" | "PENDING" | "SUSPENDED" | "DISABLED";
export type AuthorityValidationState = "PENDING" | "APPROVED" | "REJECTED" | "REVOKED";
export type ManagedAccountSummary = {
  firebase_uid: string;
  email: string | null;
  role: AccessRole;
  status: ManagedAccountStatus;
  permissions?: string[];
  created_at: string | null;
  updated_at: string | null;
  authority_validation_state?: AuthorityValidationState | null;
  protection_level?: "SYSTEM" | "PRIVILEGED" | null;
  account_origin?: "BOOTSTRAP" | "ADMIN_INVITATION" | null;
  authority_validated_at?: string | null;
  authority_validated_by_uid?: string | null;
  created_by_uid?: string | null;
};
export type ManagedInstitution = {
  firebase_uid: string;
  email: string;
  name: string;
  description: string | null;
  city: string | null;
  status: ManagedAccountStatus;
  created_at: string;
  updated_at: string;
};
export type AccessAuditEvent = {
  event_id: string;
  actor_uid: string;
  target_uid: string;
  event_type: string;
  previous_status: ManagedAccountStatus | null;
  new_status: ManagedAccountStatus | null;
  reason: string | null;
  created_at: string;
};
export type AdminOperationsSummary = {
  accounts_total: number;
  accounts_by_role: Partial<Record<AccessRole, number>>;
  accounts_by_status: Partial<Record<ManagedAccountStatus, number>>;
  institutions_total: number;
  groups_total: number;
  groups_active: number;
  merchants_active: number;
  merchants_suspended: number;
  products_active: number;
  offers_active: number;
  health_status: string;
  database_ok: boolean;
  redis_ok: boolean;
  pqc_ready: boolean;
  server_time_iso: string;
};

export type SecurityMonitoringSummary = {
  accounts_total: number;
  active_accounts: number;
  suspended_accounts: number;
  pending_accounts: number;
  disabled_accounts: number;
  recent_events_total: number;
  last_event_at: string | null;
  recent_events: AccessAuditEvent[];
  health_status: string;
  database_ok: boolean;
  redis_ok: boolean;
  pqc_ready: boolean;
  server_time_iso: string;
};

export type TrqBecSecurityStatus = {
  policy_version: string;
  environment: string;
  lab_suite_enabled: boolean;
  token_revocation_checks_enabled: boolean;
  access_validation_enforced: boolean;
  audit_ledger_append_only: boolean;
  database_ok: boolean;
  redis_ok: boolean;
  pqc_provider_name: string;
  pqc_provider_version: string;
  pqc_ready: boolean;
  privileged_accounts_total: number;
  official_accounts_total: number;
  privileged_accounts_pending_validation: number;
  access_events_total: number;
  access_events_last_24h: number;
  audit_events_total: number;
  audit_checkpoints_total: number;
  devices_active: number;
  devices_pending: number;
  devices_revoked: number;
  device_notifications_failed: number;
  email_verifications_pending: number;
  email_verifications_failed: number;
  latest_schema_migration: string | null;
  server_time_iso: string;
};
const FRIENDLY_MESSAGES: Record<string, string> = {
  INSTITUTION_APPLICATION_CONFLICT: "Esta solicitação não pôde ser registrada. Atualize a página e tente novamente.",
  INSTITUTION_APPLICATION_NOT_FOUND: "Esta solicitação institucional não foi encontrada.",
  INSTITUTION_APPLICATION_NOT_APPROVABLE: "Esta solicitação já foi aprovada ou não pode mais criar uma conta.",
  INSTITUTION_APPLICATION_FINALIZED: "Esta solicitação já criou uma conta institucional e não pode mais ser alterada.",
  INSTITUTION_APPLICATION_RECONCILIATION_REQUIRED: "A conta foi processada, mas a fila não confirmou o resultado. Não repita a aprovação; encaminhe ao Administrador.",
  INSTITUTION_FIRST_ACCESS_EMAIL_NOT_CONFIGURED: "O e-mail de primeiro acesso não está configurado. Nenhuma conta institucional foi criada.",
  INSTITUTION_FIRST_ACCESS_EMAIL_FAILED: "O link de primeiro acesso não pôde ser enviado. Nenhuma conta institucional foi criada; tente novamente mais tarde.",
  PUBLIC_ROLE_CONFLICT: "Esta conta já possui outro tipo de perfil e não pode ser alterada por esta tela.",
  PUBLIC_ROLE_PROTECTED: "Esta conta pertence a uma equipe autorizada e não pode ser convertida em perfil público.",
  PUBLIC_IDENTITY_PROVISIONER_UNAVAILABLE: "O cadastro público está temporariamente indisponível. Tente novamente em alguns minutos.",
  PUBLIC_IDENTITY_LOOKUP_FAILED: "Não foi possível consultar sua conta no Firebase. Tente novamente.",
  PUBLIC_CLAIM_UPDATE_FAILED: "Não foi possível concluir a permissão do perfil público. Tente novamente.",
  PUBLIC_ACCOUNT_NOT_PROVISIONED: "O cadastro público ainda não foi concluído no backend.",
  EMAIL_VERIFICATION_REQUIRED: "Confirme o endereço de e-mail cadastrado para liberar sua conta.",
  INSTITUTION_FUNDED_EVENT_NOT_FOUND: "Este evento institucional não foi encontrado.",
  INSTITUTION_FUNDED_EVENT_CONFLICT: "Já existe um evento institucional com os mesmos dados. Atualize a lista antes de tentar novamente.",
  INSTITUTION_EVENT_REQUIRES_ACTIVE_AFFILIATES: "O grupo precisa ter ao menos um empreendedor afiliado ativo antes de criar o evento.",
  INSTITUTION_EVENT_ACCESS_REQUIRED: "Esta conta não pode alterar o evento institucional selecionado.",
  INSTITUTION_EVENT_ALLOCATION_LOCKED: "As cotas deste evento já estão bloqueadas e não podem mais ser alteradas.",
  INSTITUTION_EVENT_DUPLICATE_SELLER: "Um mesmo afiliado foi informado mais de uma vez na divisão da verba.",
  INSTITUTION_EVENT_SELLER_SET_MISMATCH: "A divisão precisa incluir exatamente os afiliados ativos do grupo.",
  INSTITUTION_GROUP_CLOSED: "Este grupo está encerrado. Os selos, percentuais e a distribuição por selos não podem ser alterados.",
  INSTITUTION_BADGE_POLICY_REQUIRED: "Defina os percentuais dos três selos na aba Grupos antes de distribuir a verba.",
  INSTITUTION_BADGE_CLASSIFICATION_REQUIRED: "Classifique todos os feirantes participantes antes de distribuir por selos.",
  INSTITUTION_BADGE_EMPTY_CATEGORY: "Um selo com percentual maior que zero não tem participantes neste evento. Ajuste os percentuais ou a classificação antes de aplicar.",
  INSTITUTION_BADGE_ACTIVE_MEMBER_REQUIRED: "A classificação e a distribuição por selos exigem filiados ativos. Revise os participantes do grupo e do evento.",
  INSTITUTION_EVENT_BUDGET_TOTAL_MISMATCH: "A soma das cotas dos afiliados precisa ser igual ao valor total do evento.",
  INSTITUTION_EVENT_DUPLICATE_PRODUCT: "Um mesmo produto foi informado mais de uma vez na divisão da verba.",
  INSTITUTION_EVENT_PRODUCT_TOTAL_MISMATCH: "A soma destinada aos produtos precisa ser igual à cota do empreendedor.",
  INSTITUTION_EVENT_PRODUCT_NOT_ELIGIBLE: "Um dos produtos selecionados não está ativo, não pertence ao afiliado ou utiliza outra moeda.",
  INSTITUTION_EVENT_NOT_DRAFT: "Somente eventos que ainda estão em rascunho podem ser ativados.",
  INSTITUTION_EVENT_END_TIME_ALREADY_PASSED: "O horário final deste evento já passou. Edite ou crie um novo evento com término futuro.",
  INSTITUTION_GROUP_ALREADY_HAS_ACTIVE_FUNDED_EVENT: "Este grupo já possui outro evento promocional ativo.",
  INSTITUTION_EVENT_SELLER_HAS_NO_ACTIVE_PRODUCTS: "Um afiliado recebeu verba, mas não possui produto ativo em BRL. Cadastre ou reative ao menos um produto desse empreendedor antes de ativar o evento.",
  INSTITUTION_EVENT_NOT_ACTIVE: "Este evento não está ativo ou já foi encerrado.",
  ACCOUNT_CLOSURE_FAILED: "Não foi possível encerrar os produtos, ofertas e chaves da conta. O login foi preservado.",
  ACCOUNT_FIRESTORE_CLEANUP_FAILED: "Não foi possível remover os dados da conta no Firebase. O login foi preservado; tente novamente.",
  AUTH_REQUIRED: "Entre novamente para validar sua identidade.",
  AUTH_BEARER_REQUIRED: "O backend não recebeu sua sessão. Saia e entre novamente.",
  AUTH_TOKEN_INVALID: "Sua sessão não foi aceita pelo backend. Saia, entre novamente e confira se data e hora automáticas estão corretas no celular e no computador.",
  ACCOUNT_PERMISSION_REQUIRED: "Esta conta não possui a permissão necessária para concluir a ação.",
  ADMIN_ACCESS_REQUIRED: "Esta conta não possui acesso administrativo a esta ferramenta.",
  ADMIN_STAFF_ACCESS_REQUIRED: "Esta conta não possui permissão para criar ou validar a equipe autorizada.",
  STAFF_AUTHORITY_VALIDATION_REQUIRED: "Esta conta de equipe ainda aguarda validação administrativa.",
  STAFF_VALIDATED_CLAIM_REQUIRED: "A validação foi concluída. Saia e entre novamente para receber as novas permissões.",
  STAFF_EMAIL_EXISTS: "Este e-mail já está vinculado a uma conta no Firebase.",
  STAFF_ACCOUNT_EXISTS: "Esta conta de equipe já foi cadastrada.",
  STAFF_ACCOUNT_NOT_FOUND: "A conta de equipe não foi encontrada.",
  STAFF_PROVISIONER_UNAVAILABLE: "A criação de contas da equipe está temporariamente indisponível.",
  STAFF_PROVISION_FAILED: "Não foi possível criar a conta da equipe. Nenhum acesso privilegiado foi liberado.",
  STAFF_PROVISION_ROLLBACK_FAILED: "A criação não terminou com segurança. Procure a Segurança antes de repetir a operação.",
  STAFF_EMAIL_VERIFICATION_REQUIRED: "O endereço de e-mail ainda não foi confirmado. Peça à pessoa para abrir o link de verificação e tente novamente.",
  STAFF_IDENTITY_DISABLED: "A identidade está desativada no Firebase e não pode ser validada.",
  STAFF_IDENTITY_ROLE_MISMATCH: "A função registrada no Firebase não corresponde à solicitação. Nenhum acesso foi liberado.",
  STAFF_IDENTITY_EMAIL_MISMATCH: "O e-mail do Firebase não corresponde ao cadastro pendente. Nenhum acesso foi liberado.",
  STAFF_VALIDATION_STATE_INVALID: "Esta conta não está em um estado que permita validação. Atualize a lista.",
  STAFF_SELF_VALIDATION_FORBIDDEN: "Uma conta não pode validar a própria autoridade.",
  STAFF_CLAIM_UPDATE_FAILED: "O Firebase não confirmou as novas permissões. A conta permanece pendente.",
  STAFF_VALIDATION_RECONCILIATION_REQUIRED: "A validação ficou incompleta entre os serviços. A conta permaneceu bloqueada; encaminhe para a Segurança.",
  OPERATIONS_SUMMARY_UNAVAILABLE: "O resumo operacional está temporariamente indisponível.",
  SUPPORT_ACCESS_REQUIRED: "Esta conta de suporte não possui autorização para concluir a ação.",
  INSTITUTION_EMAIL_EXISTS: "Este e-mail já está vinculado a uma conta. Use outro e-mail institucional.",
  INSTITUTION_ACCOUNT_EXISTS: "Esta instituição já possui uma conta cadastrada.",
  INSTITUTION_PROVISIONER_UNAVAILABLE: "A criação de contas institucionais está temporariamente indisponível.",
  INSTITUTION_PROVISION_FAILED: "Não foi possível criar a conta institucional no Firebase. Nenhum acesso foi liberado.",
  INSTITUTION_PROVISION_ROLLBACK_FAILED: "A criação não foi concluída com segurança. Procure o administrador antes de tentar novamente.",
  INSTITUTION_ACCESS_REQUIRED: "Esta conta não possui autorização para esta ferramenta institucional.",
  INSTITUTION_PROFILE_NOT_FOUND: "O perfil desta instituição não foi encontrado.",
  INSTITUTION_PROFILE_FIELDS_REQUIRED: "Altere ao menos um campo antes de salvar o perfil.",
  INSTITUTION_PROFILE_NAME_REQUIRED: "O nome da instituição não pode ficar vazio.",
  SELLER_NAME_INVALID: "Digite o nome público único completo do empreendedor.",
  ELIGIBLE_SELLER_NOT_FOUND: "Nenhum empreendedor ativo foi encontrado com esse nome público único.",
  INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED: "Este grupo não existe ou não pertence à instituição autenticada.",
  INSTITUTION_GROUP_ACCESS_REQUIRED: "Esta conta não pode alterar o grupo selecionado.",
  INSTITUTION_GROUP_NOT_ACTIVE: "Este grupo está encerrado e não aceita novos convites ou alterações.",
  INSTITUTION_INVITATION_CONFLICT: "O convite foi alterado por outra operação. Atualize a lista antes de tentar novamente.",
  INSTITUTION_INVITATION_NOT_FOUND: "Este convite não existe ou não pertence à conta autenticada.",
  INSTITUTION_INVITATION_NOT_PENDING: "Este convite já foi respondido. Atualize a lista para conferir o estado atual.",
  SELLER_ALREADY_HAS_ACTIVE_MEMBERSHIP: "Este empreendedor já possui uma filiação institucional ativa.",
  INSTITUTION_MEMBERSHIP_ACCESS_REQUIRED: "Esta conta não pode responder ou alterar a filiação selecionada.",
  INSTITUTION_MEMBERSHIP_NOT_FOUND: "Esta filiação não foi encontrada.",
  INSTITUTION_MEMBERSHIP_NOT_FOUND_OR_NOT_OWNED: "Esta filiação não existe ou não pertence ao grupo selecionado.",
  INSTITUTION_MEMBERSHIP_NOT_ACTIVE: "Esta filiação já foi encerrada. Atualize a lista.",
  REPORT_TIMEZONE_REQUIRED: "O período do relatório precisa incluir o fuso horário. Atualize a tela e tente novamente.",
  REPORT_PERIOD_INVALID: "O período do relatório é inválido. Escolha outro intervalo.",
  REPORT_FUTURE_PERIOD_NOT_ALLOWED: "O relatório não pode consultar um período futuro.",
  REPORT_PERIOD_TOO_LARGE: "O período solicitado é muito longo. Escolha um intervalo menor.",
  SECURITY_ACCESS_REQUIRED: "Esta conta não possui autorização para esta ferramenta de segurança.",
  SECURITY_MONITORING_UNAVAILABLE: "O monitoramento está temporariamente indisponível.",
  TRQ_BEC_MONITORING_UNAVAILABLE: "A telemetria do TRQ-BEC está temporariamente indisponível.",
  ACCESS_STORE_WRITE_FAILED: "A conta não pôde ser registrada no controle de acesso. Tente novamente mais tarde.",
  ENTREPRENEUR_ACCESS_REQUIRED: "Esta ação está disponível somente para uma conta de empreendedor autorizada.",
  COMMUNITY_FIRESTORE_WRITE_FAILED: "O backend não conseguiu publicar esta informação no Firestore. Tente novamente.",
  COMMUNITY_PUBLISHER_UNAVAILABLE: "A publicação no Feed, de pontos e de feiras está temporariamente indisponível.",
  AVATAR_MEDIA_REFERENCE_REQUIRED: "Escolha a foto novamente pelo perfil do LiberRotas.",
  AVATAR_MEDIA_NOT_READY: "A foto ainda está sendo processada. Aguarde e tente salvar novamente.",
  AVATAR_MEDIA_NOT_OWNED: "A foto selecionada não pertence a esta conta.",
  AVATAR_MEDIA_REFERENCE_INVALID: "A foto selecionada não é um avatar válido do LiberRotas.",
  LIVE_FAIR_START_INVALID: "O início da feira não pode estar mais de 30 minutos no passado.",
  LIVE_FAIR_END_INVALID: "O horário final da feira precisa estar no futuro.",
  LIVE_FAIR_MANAGER_ACCESS_REQUIRED: "Esta ação está disponível somente para empreendedor ou instituição autorizada.",
  LIVE_FAIR_NOT_FOUND: "Esta feira não existe mais.",
  LIVE_FAIR_NOT_OWNED: "Somente quem publicou a feira pode encerrá-la ou excluí-la.",
  LIVE_FAIR_NOT_ACTIVE: "Esta feira já foi encerrada ou não está ativa.",
  CURATED_PLACE_ALREADY_EXISTS: "Você já possui um ponto publicado. Exclua o ponto atual antes de publicar outro.",
  CURATED_PLACE_NOT_FOUND: "Este ponto não existe mais no mapa.",
  CURATED_PLACE_NOT_OWNED: "Somente quem publicou o ponto pode excluí-lo.",
  ENTREPRENEUR_CLAIM_REQUIRED: "Seu perfil é de empreendedor, mas a permissão TRQ-BEC ainda não foi ativada no Firebase.",
  MERCHANT_ACCOUNT_INACTIVE: "Sua permissão de empreendedor foi reconhecida, mas a conta comercial ainda precisa ser aprovada no TRQ-BEC.",
  MERCHANT_PUBLIC_PROFILE_NOT_FOUND: "Este perfil não possui catálogo comercial ativo.",
  PRODUCT_NOT_ACTIVE_OR_NOT_OWNED: "O produto não existe, não está ativo ou pertence a outro empreendedor.",
  PRODUCT_NOT_ACTIVE_OR_OUT_OF_STOCK: "O produto está inativo ou sem estoque no backend.",
  OFFER_LIMIT_EXCEEDS_STOCK: "O estoque do produto é menor que o limite informado para a oferta.",
  DISCOUNT_INVALID_FOR_AUTHORITATIVE_PRICE: "O desconto precisa ser menor que o preço do produto selecionado.",
  OFFER_VALIDITY_TOO_SHORT: "A oferta precisa permanecer válida por pelo menos 30 segundos.",
  OFFER_VALIDITY_TOO_LONG: "A validade da oferta não pode ultrapassar 8 horas.",
  OFFER_EXPIRED: "Esta oferta expirou.",
  OFFER_NOT_FOUND: "Esta oferta não existe mais ou não pertence à sua conta.",
  OFFER_NOT_ACTIVE: "Esta oferta não está ativa.",
  OFFER_QR_NOT_AVAILABLE: "O QR não está disponível porque a oferta terminou, ficou sem estoque ou foi excluída.",
  OFFER_QR_QUANTITY_INVALID: "Informe uma quantidade válida para esta venda.",
  OFFER_QR_QUANTITY_EXCEEDS_AVAILABLE: "A quantidade escolhida é maior que o estoque ou o saldo disponível da oferta.",
  QR_QUANTITY_BINDING_REQUIRED: "Este QR não possui autorização válida para a quantidade informada.",
  QR_QUANTITY_BINDING_INVALID: "A quantidade deste QR foi alterada ou não pôde ser autenticada.",
  OFFER_REVOCATION_FAILED: "Não foi possível excluir a oferta agora. Atualize a vitrine e tente novamente.",
  OFFER_EXHAUSTED: "Esta oferta não possui mais unidades disponíveis.",
  OFFER_ALREADY_REDEEMED_BY_USER: "Você já resgatou esta oferta.",
  TOKEN_NOT_REDEEMABLE: "Este QR Code já foi resgatado, encerrado ou não está mais disponível.",
  TOKEN_REFERENCE_UNKNOWN: "Este QR Code não pertence a uma oferta disponível.",
  QR_BINDING_MISMATCH: "Os dados deste QR Code não correspondem à oferta emitida.",
  OPERATION_EXPIRED: "A confirmação demorou demais e expirou. Leia o QR Code novamente.",
  RECENT_AUTHENTICATION_REQUIRED: "Por segurança, saia e entre novamente antes de concluir esta operação.",
  DEVICE_NOT_ACTIVE: "Este dispositivo está no período de segurança e será liberado automaticamente após 10 minutos.",
  DEVICE_APPROVAL_REQUIRED: "Este dispositivo está no período de segurança e será liberado automaticamente após 10 minutos.",
  DEVICE_APPROVAL_INVALID: "Este link de confirmação é inválido ou já foi utilizado. Solicite um novo e-mail nesta tela.",
  DEVICE_APPROVAL_EXPIRED: "Este link de confirmação expirou. Solicite um novo e-mail nesta tela.",
  DEVICE_APPROVAL_INVALID_OR_EXPIRED: "Este link de confirmação é inválido, expirou ou já foi utilizado. Solicite um novo e-mail nesta tela.",
  DEVICE_APPROVAL_NOT_PENDING: "Este dispositivo não está aguardando confirmação. Atualize a lista para conferir o status.",
  DEVICE_NOT_ENROLLED: "Este dispositivo ainda não está ativo. Aguarde o fim do período de segurança e tente novamente.",
  DEVICE_NOT_FOUND: "Este dispositivo não foi encontrado na sua conta. Atualize a lista.",
  PENDING_DEVICE_LIMIT_REACHED: "Há muitos dispositivos aguardando confirmação. Confirme os aparelhos reconhecidos ou use Alterar senha e desconectar todos.",
  APPROVAL_RESEND_COOLDOWN: "Aguarde um minuto antes de reenviar o e-mail de confirmação.",
  SESSION_REVOCATION_UNAVAILABLE: "Não foi possível desconectar todas as sessões agora. Tente novamente antes de usar o link de alteração de senha.",
  SESSION_REVOCATION_FAILED: "Não foi possível concluir a desconexão de todos os acessos. Tente novamente antes de usar o link de alteração de senha.",
  DEVICE_REVOCATION_FAILED: "Não foi possível revogar todos os dispositivos. Tente novamente antes de usar o link de alteração de senha.",
  VISITOR_CLAIM_REQUIRED: "Este resgate exige uma conta com perfil de visitante.",
  SELF_REDEMPTION_FORBIDDEN: "O empreendedor não pode resgatar a própria oferta.",
  RATE_LIMIT_EXCEEDED: "Muitas tentativas em pouco tempo. Aguarde e tente novamente.",
  OPERATION_IN_PROGRESS: "Esta confirmação ainda está em andamento. Aguarde um instante.",
  CHALLENGE_STORE_UNAVAILABLE: "O serviço de segurança temporária está indisponível. Tente novamente.",
  REPLAY_STORE_UNAVAILABLE: "A proteção contra repetição está indisponível. Nenhum resgate foi concluído.",
  MESSAGE_BODY_INVALID: "Digite uma mensagem válida antes de enviar.",
  MESSAGE_RECIPIENT_NOT_FOUND: "Este perfil não está disponível para receber mensagens.",
  MESSAGE_RECIPIENT_NOT_AVAILABLE: "Este perfil não está disponível para receber mensagens.",
  MESSAGE_SELF_FORBIDDEN: "Você não pode enviar uma mensagem para o próprio perfil.",
  MESSAGE_CONVERSATION_FORBIDDEN: "Esta conversa não está disponível para sua conta.",
  MESSAGE_BLOCKED: "A conversa está bloqueada e não aceita novas mensagens.",
  MESSAGE_DELIVERY_BLOCKED: "A conversa está bloqueada e não aceita novas mensagens.",
  CONVERSATION_NOT_FOUND: "Esta conversa não existe ou não está disponível para sua conta.",
  CONVERSATION_CLOSED: "Esta conversa foi encerrada e não aceita novas mensagens.",
  SUPPORT_REQUEST_NOT_FOUND: "Este atendimento não foi encontrado.",
  SUPPORT_REQUEST_CLOSED: "Este atendimento foi encerrado e não aceita novas mensagens.",
  SUPPORT_REQUEST_NOT_RESOLVABLE: "Este atendimento já foi encerrado ou não pode ser resolvido agora.",
  SEARCH_QUERY_INVALID: "Digite pelo menos dois caracteres para pesquisar.",
  PUBLIC_PROFILE_SYNC_FAILED: "Não foi possível sincronizar o perfil público no backend.",
  PUBLIC_PROFILE_FIRESTORE_SYNC_FAILED: "O perfil foi validado, mas não pôde ser publicado agora. Tente novamente.",
  PUBLIC_PROFILE_STORE_UNAVAILABLE: "O serviço de perfis está temporariamente indisponível. Tente novamente.",
  DISPLAY_NAME_ALREADY_IN_USE: "Este nome público já está sendo usado. Escolha outro nome.",
  DISPLAY_NAME_RESERVED: "Este nome é reservado pelo LiberRotas. Escolha outro nome público.",
  DISPLAY_NAME_INVALID: "Informe um nome público válido com pelo menos 3 caracteres.",
  BATCH_CLIENT_REQUEST_ID_REUSED: "Esta confirmação já foi usada para outra alteração. Feche a caixa, confira a seleção e tente novamente.",
  BATCH_IDEMPOTENCY_CLAIM_FAILED: "Não foi possível proteger esta alteração contra repetição. Nenhum lote foi confirmado; tente novamente.",
  BATCH_IDEMPOTENCY_COMMIT_FAILED: "Não foi possível confirmar esta alteração com segurança. Atualize a lista antes de tentar novamente.",
  PRODUCT_BATCH_IDS_INVALID: "Selecione produtos válidos, sem repetições, para fazer a exclusão em massa.",
  PRODUCT_BATCH_NOT_FOUND_OR_FINAL: "Um dos produtos selecionados não existe ou não pertence a esta conta. Atualize a lista.",
  PRODUCT_BATCH_ARCHIVE_FAILED: "Não foi possível excluir os produtos selecionados. Nenhum deles foi alterado; tente novamente.",
  PRODUCT_BATCH_ACTIVATE_ITEMS_INVALID: "Informe um estoque inteiro maior que zero para cada produto selecionado.",
  PRODUCT_BATCH_NOT_FOUND_OR_NOT_OWNED: "Um dos produtos selecionados não existe, foi excluído ou pertence a outra conta. Atualize a lista.",
  PRODUCT_BATCH_ACTIVATE_FAILED: "Não foi possível ativar os produtos selecionados. Nenhum deles foi alterado; tente novamente.",
  OFFER_BATCH_IDS_INVALID: "Selecione ofertas válidas, sem repetições, para fazer a alteração em massa.",
  OFFER_BATCH_NOT_FOUND_OR_FINAL: "Uma das ofertas selecionadas terminou, foi excluída ou não pertence a esta conta. Atualize a lista.",
  OFFER_BATCH_TOKEN_CHANGED: "Uma das ofertas foi atualizada em outro aparelho. Atualize a lista antes de tentar novamente.",
  OFFER_BATCH_CHANGED_RETRY: "Uma das ofertas mudou durante a confirmação. Nenhuma alteração parcial foi mantida; atualize a lista.",
  OFFER_BATCH_TOKEN_INVALID: "Uma das ofertas não possui um QR válido para esta alteração. Atualize a lista ou emita outra oferta.",
  OFFER_BATCH_DISCOUNT_INVALID: "O novo desconto deixaria uma das ofertas inválida. Revise o aumento informado.",
  OFFER_BATCH_DISCOUNT_TYPE_MISMATCH: "Selecione somente ofertas do mesmo tipo de desconto para aumentá-las juntas.",
  OFFER_BATCH_DISCOUNT_LIMIT_EXCEEDED: "O aumento ultrapassa o limite permitido para pelo menos uma oferta. Informe um valor menor.",
  OFFER_BATCH_ACTION_FAILED: "Não foi possível alterar as ofertas selecionadas. Nenhuma alteração parcial foi mantida; tente novamente.",
};

export class TrqBecServiceError extends Error {
  constructor(public readonly userMessage: string, public readonly code: string) {
    super(userMessage);
    this.name = "TrqBecServiceError";
  }
}

async function getFirebaseIdToken(forceRefresh = false) {
  const user = auth.currentUser;
  if (!user) throw new TrqBecServiceError(FRIENDLY_MESSAGES.AUTH_REQUIRED, "AUTH_REQUIRED");
  return user.getIdToken(forceRefresh);
}

function getFirebaseUid() {
  const user = auth.currentUser;
  if (!user) throw new TrqBecServiceError(FRIENDLY_MESSAGES.AUTH_REQUIRED, "AUTH_REQUIRED");
  return user.uid;
}

function optionalDeviceMetadata(value: string | null | undefined, maxLength: number): string | undefined {
  const normalized = value?.replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim() || "";
  return normalized ? normalized.slice(0, maxLength) : undefined;
}

function getDevicePlatform(): DevicePlatform {
  const current = Platform.OS;
  return current === "android" || current === "ios" || current === "web"
    || current === "windows" || current === "macos"
    ? current
    : "unknown";
}

function getCurrentDeviceMetadata() {
  const platform = getDevicePlatform();
  const defaultName = platform === "web" ? "Navegador web" : Device.modelName || "Dispositivo";
  const appVersion = optionalDeviceMetadata(Constants.nativeAppVersion || Constants.expoConfig?.version, 40);
  return {
    device_name: optionalDeviceMetadata(Device.deviceName || defaultName, 80),
    platform,
    model_name: optionalDeviceMetadata(Device.modelName || Device.osName, 120),
    app_version: appVersion && /^[A-Za-z0-9._+()-]+$/.test(appVersion) ? appVersion : undefined,
  };
}

async function clearRejectedFirebaseSession(): Promise<void> {
  const currentUser = auth.currentUser;
  if (!currentUser) return;
  if (rejectedSessionCleanup) return rejectedSessionCleanup;

  rejectedSessionCleanup = (async () => {
    try {
      await signOut(auth);
    } catch (error) {
      console.warn("Não foi possível encerrar localmente a sessão revogada.", error);
    }
  })().finally(() => {
    rejectedSessionCleanup = null;
  });

  return rejectedSessionCleanup;
}

function parseDeviceEnrollment(value: unknown, expectedKeyId: string): CurrentDeviceEnrollment {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TrqBecServiceError("O backend devolveu um cadastro de dispositivo inválido.", "DEVICE_RESPONSE_INVALID");
  }
  const enrollment = value as Record<string, unknown>;
  const notificationStatuses: DeviceNotificationStatus[] = ["NOT_REQUIRED", "SENT", "NOT_CONFIGURED", "FAILED", "PENDING"];
  if (
    enrollment.device_key_id !== expectedKeyId
    || (enrollment.status !== "ENROLLED" && enrollment.status !== "ALREADY_ENROLLED")
    || (enrollment.device_status !== "ACTIVE" && enrollment.device_status !== "PENDING_APPROVAL")
    || typeof enrollment.key_ref !== "string"
    || typeof enrollment.is_new_device !== "boolean"
    || typeof enrollment.is_additional_device !== "boolean"
    || !notificationStatuses.includes(enrollment.notification_status as DeviceNotificationStatus)
  ) {
    throw new TrqBecServiceError("O backend devolveu um cadastro de dispositivo inválido.", "DEVICE_RESPONSE_INVALID");
  }
  return enrollment as CurrentDeviceEnrollment;
}

function getErrorMessage(data: ApiErrorPayload | null, status: number) {
  const detailCode = typeof data?.detail === "string" ? data.detail : undefined;
  const code = data?.code || detailCode || `HTTP_${status}`;
  const backendMessage = typeof data?.message === "string" && data.message !== code ? data.message : undefined;
  return {
    code,
    message: FRIENDLY_MESSAGES[code] || backendMessage || `O backend recusou a solicitação (HTTP ${status}).`,
  };
}

const { requestAuthenticated, requestPublic } = createTrqBecHttpClient({
  baseUrl: API_URL,
  timeoutMs: REQUEST_TIMEOUT_MS,
  getIdToken: getFirebaseIdToken,
  mapError: (data, status) => getErrorMessage(data as ApiErrorPayload | null, status),
  onRejectedSession: clearRejectedFirebaseSession,
  createError: (message, code) => new TrqBecServiceError(message, code),
  isServiceError: (error) => error instanceof TrqBecServiceError,
});
const directoryApi = createDirectoryApi(requestAuthenticated);
const messagingNormalizers = createMessagingNormalizers(
  getStablePublicAvatarUrl,
  (message, code) => new TrqBecServiceError(message, code),
);
const messagingApi = createMessagingApi({
  requestAuthenticated,
  normalizers: messagingNormalizers,
  createError: (message, code) => new TrqBecServiceError(message, code),
});
const communityApi = createCommunityApi({
  requestAuthenticated,
  messagingNormalizers,
  createClientMessageId: messagingApi.createClientMessageId,
  createError: (message, code) => new TrqBecServiceError(message, code),
});
const institutionsApi = createInstitutionsApi(requestAuthenticated);
const marketplaceApi = createMarketplaceApi({
  requestAuthenticated,
  enrollDevice,
  createError: (message, code) => new TrqBecServiceError(message, code),
});
const trqBecApi = createTrqBecApi({
  requestAuthenticated,
  enrollDevice,
  getOwnerUid: getFirebaseUid,
  decodeBase64Url: base64UrlToBytes,
  signDeviceProof,
  createError: (message, code) => new TrqBecServiceError(message, code),
  isServiceError: (error): error is TrqBecServiceError => error instanceof TrqBecServiceError,
  getFriendlyMessage: (code) => FRIENDLY_MESSAGES[code],
});

async function performDeviceEnrollment(allowRevokedKeyRotation = true) {
  const ownerUid = getFirebaseUid();
  const identity = await getOrCreateDeviceIdentity(ownerUid);
  try {
    const response = await requestAuthenticated<unknown>("POST", "/v1/trq-bec/devices/enroll", {
      device_key_id: identity.keyId,
      public_key_b64u: identity.publicKeyB64u,
      algorithm: identity.algorithm,
      storage_profile: identity.storageProfile,
      ...getCurrentDeviceMetadata(),
    });
    const enrollment = parseDeviceEnrollment(response, identity.keyId);
    return { enrollment, identity };
  } catch (error) {
    if (
      allowRevokedKeyRotation
      && error instanceof TrqBecServiceError
      && error.code === "DEVICE_KEY_REVOKED"
    ) {
      await removeDeviceIdentity(ownerUid);
      return performDeviceEnrollment(false);
    }
    throw error;
  }
}

async function enrollDevice() {
  return (await performDeviceEnrollment()).identity;
}

/** Cadastra o aparelho autenticado sem aceitar e-mail, UID ou função do frontend. */
export async function enrollCurrentDevice(): Promise<CurrentDeviceEnrollment> {
  return (await performDeviceEnrollment()).enrollment;
}

export async function getCurrentDeviceKeyId(): Promise<string> {
  return (await getOrCreateDeviceIdentity(getFirebaseUid())).keyId;
}

export function getTrqBecApiUrl() {
  return API_URL;
}

/**
 * Avatares novos ficam no armazenamento do LiberRotas. Para exibicao, use a
 * URL estavel do perfil, que continua valida depois da troca da imagem.
 */
export function getStablePublicAvatarUrl(firebaseUid: string, avatarUri?: string | null) {
  const mediaPrefix = API_URL ? `${API_URL}/v1/public/media/` : "";
  if (!avatarUri || !mediaPrefix || !avatarUri.startsWith(mediaPrefix)) {
    return avatarUri || undefined;
  }
  const cleanUid = firebaseUid.trim();
  return cleanUid
    ? `${API_URL}/v1/public/profile/${encodeURIComponent(cleanUid)}/avatar?variant=thumbnail`
    : avatarUri;
}

function parseAccessSession(value: unknown): AccessSession {
  const roles: AccessRole[] = ["admin", "support", "security", "institution", "entrepreneur", "visitor"];
  const states: AccessState[] = ["AUTHORIZED", "PENDING", "SUSPENDED", "DENIED"];
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TrqBecServiceError("O backend devolveu uma decisão de acesso inválida.", "ACCESS_RESPONSE_INVALID");
  }

  const response = value as Record<string, unknown>;
  const role = response.role === null || roles.includes(response.role as AccessRole)
    ? response.role as AccessRole | null
    : undefined;
  const permissions = Array.isArray(response.permissions)
    && response.permissions.length <= 100
    && response.permissions.every((permission) => typeof permission === "string" && permission.length > 0)
    ? [...new Set(response.permissions as string[])]
    : null;
  const state = states.includes(response.access_state as AccessState)
    ? response.access_state as AccessState
    : null;
  const reason = typeof response.reason === "string" && response.reason.length >= 3 && response.reason.length <= 80
    ? response.reason
    : null;

  if (!state || role === undefined || !permissions || !reason) {
    throw new TrqBecServiceError("O backend devolveu uma decisão de acesso inválida.", "ACCESS_RESPONSE_INVALID");
  }
  if (state === "AUTHORIZED") {
    if (!role || response.panel !== role || !permissions.includes(`${role}.panel.access`)) {
      throw new TrqBecServiceError("O backend devolveu permissões de painel inconsistentes.", "ACCESS_RESPONSE_INVALID");
    }
  } else if (role !== null || response.panel !== "access_pending" || permissions.length !== 0) {
    throw new TrqBecServiceError("O backend devolveu uma decisão de acesso inconsistente.", "ACCESS_RESPONSE_INVALID");
  }

  return {
    access_state: state,
    role,
    panel: response.panel as AccessPanel,
    permissions,
    reason,
  };
}

/** Resolve a função somente no backend; não recebe role ou destino do cliente. */
export async function resolveAuthenticatedAccess(): Promise<AccessSession> {
  const response = await requestAuthenticated<unknown>("GET", "/v1/access/me", undefined, true);
  return parseAccessSession(response);
}

function parseEmailVerificationQueueResult(value: unknown): EmailVerificationQueueResult {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TrqBecServiceError(
      "O backend devolveu um estado inválido para a verificação de e-mail.",
      "EMAIL_VERIFICATION_RESPONSE_INVALID",
    );
  }
  const response = value as Record<string, unknown>;
  if (
    (response.status !== "QUEUED"
      && response.status !== "ALREADY_VERIFIED"
      && response.status !== "NOT_REQUIRED")
    || (response.role !== "entrepreneur" && response.role !== "visitor")
  ) {
    throw new TrqBecServiceError(
      "O backend devolveu um estado inválido para a verificação de e-mail.",
      "EMAIL_VERIFICATION_RESPONSE_INVALID",
    );
  }
  return response as EmailVerificationQueueResult;
}

/** Conclui somente o cadastro público escolhido na tela de criação da conta. */
export async function registerPublicAccount(
  input: PublicRegistrationInput,
): Promise<EmailVerificationQueueResult> {
  const response = await requestAuthenticated<unknown>(
    "POST",
    "/v1/access/public-registration",
    {
      role: input.role,
      display_name: input.displayName.trim(),
      ...(input.role === "entrepreneur"
        ? { establishment_name: (input.establishmentName || input.displayName).trim() }
        : {}),
    },
    true,
  );
  return parseEmailVerificationQueueResult(response);
}

export async function resendPublicEmailVerification(): Promise<EmailVerificationQueueResult> {
  const response = await requestAuthenticated<unknown>(
    "POST",
    "/v1/access/email-verification/resend",
    undefined,
    true,
  );
  return parseEmailVerificationQueueResult(response);
}

function parseOptionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function parseAccountDevice(value: unknown): AccountDevice {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TrqBecServiceError("O backend devolveu um dispositivo inválido.", "DEVICE_RESPONSE_INVALID");
  }
  const device = value as Record<string, unknown>;
  const platforms: DevicePlatform[] = ["android", "ios", "web", "windows", "macos", "linux", "unknown"];
  const statuses: AccountDeviceStatus[] = ["ACTIVE", "PENDING_APPROVAL", "REVOKED"];
  const notificationStatuses: DeviceNotificationStatus[] = ["NOT_REQUIRED", "SENT", "NOT_CONFIGURED", "FAILED", "PENDING"];

  if (
    typeof device.device_key_id !== "string"
    || typeof device.key_ref !== "string"
    || typeof device.storage_profile !== "string"
    || typeof device.created_at !== "string"
    || !platforms.includes(device.platform as DevicePlatform)
    || !statuses.includes(device.status as AccountDeviceStatus)
    || !notificationStatuses.includes(device.notification_status as DeviceNotificationStatus)
  ) {
    throw new TrqBecServiceError("O backend devolveu um dispositivo inválido.", "DEVICE_RESPONSE_INVALID");
  }

  return {
    device_key_id: device.device_key_id,
    key_ref: device.key_ref,
    device_name: parseOptionalString(device.device_name),
    platform: device.platform as DevicePlatform,
    model_name: parseOptionalString(device.model_name),
    app_version: parseOptionalString(device.app_version),
    storage_profile: device.storage_profile,
    status: device.status as AccountDeviceStatus,
    created_at: device.created_at,
    last_seen_at: parseOptionalString(device.last_seen_at),
    revoked_at: parseOptionalString(device.revoked_at),
    approval_expires_at: parseOptionalString(device.approval_expires_at),
    approval_last_sent_at: parseOptionalString(device.approval_last_sent_at),
    approved_at: parseOptionalString(device.approved_at),
    notification_status: device.notification_status as DeviceNotificationStatus,
  };
}

export async function listAccountDevices(): Promise<AccountDevice[]> {
  const response = await requestAuthenticated<{ devices?: unknown }>("GET", "/v1/account/devices");
  if (!Array.isArray(response.devices) || response.devices.length > 100) {
    throw new TrqBecServiceError("O backend devolveu uma lista de dispositivos inválida.", "DEVICE_RESPONSE_INVALID");
  }
  return response.devices.map(parseAccountDevice);
}

function normalizeApprovalToken(value: string): string {
  const token = value.trim();
  if (token.length < 32 || token.length > 128 || !/^[A-Za-z0-9_-]+$/.test(token)) {
    throw new TrqBecServiceError("O link de confirmação é inválido. Solicite um novo e-mail.", "DEVICE_APPROVAL_INVALID");
  }
  return token;
}

export async function approveAccountDevice(approvalToken: string): Promise<ApproveDeviceResult> {
  const response = await requestAuthenticated<unknown>("POST", "/v1/account/devices/approve", {
    approval_token: normalizeApprovalToken(approvalToken),
  });
  if (
    !response || typeof response !== "object" || Array.isArray(response)
    || (response as Record<string, unknown>).status !== "DEVICE_APPROVED"
    || typeof (response as Record<string, unknown>).device_key_id !== "string"
    || (response as Record<string, unknown>).device_status !== "ACTIVE"
  ) {
    throw new TrqBecServiceError("O backend não confirmou a ativação do dispositivo.", "DEVICE_RESPONSE_INVALID");
  }
  return response as ApproveDeviceResult;
}

export async function resendAccountDeviceApproval(deviceKeyId: string): Promise<ResendDeviceApprovalResult> {
  const normalizedKeyId = deviceKeyId.trim();
  if (!normalizedKeyId || normalizedKeyId.length > 200) {
    throw new TrqBecServiceError("O dispositivo selecionado é inválido.", "DEVICE_KEY_INVALID");
  }
  const response = await requestAuthenticated<unknown>("POST", "/v1/account/devices/resend-approval", {
    device_key_id: normalizedKeyId,
  });
  if (
    !response || typeof response !== "object" || Array.isArray(response)
    || (response as Record<string, unknown>).device_key_id !== normalizedKeyId
    || (response as Record<string, unknown>).device_status !== "PENDING_APPROVAL"
    || !["PENDING", "SENT", "NOT_CONFIGURED", "FAILED"].includes(String((response as Record<string, unknown>).notification_status))
  ) {
    throw new TrqBecServiceError("O backend não confirmou o reenvio da aprovação.", "DEVICE_RESPONSE_INVALID");
  }
  return response as ResendDeviceApprovalResult;
}

export async function revokeAllAccountDevices(): Promise<RevokeAllDevicesResult> {
  const response = await requestAuthenticated<unknown>("POST", "/v1/account/devices/revoke-all");
  if (
    !response || typeof response !== "object" || Array.isArray(response)
    || (response as Record<string, unknown>).status !== "ALL_DEVICES_REVOKED"
    || typeof (response as Record<string, unknown>).revoked_devices !== "number"
    || (response as Record<string, unknown>).sessions_revoked !== true
  ) {
    throw new TrqBecServiceError("O backend não confirmou a desconexão de todos os dispositivos.", "DEVICE_RESPONSE_INVALID");
  }
  return response as RevokeAllDevicesResult;
}

type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export const syncPublicDirectoryProfile = directoryApi.syncPublicDirectoryProfile;
export const loadOwnPublicDirectoryProfile = directoryApi.loadOwnPublicDirectoryProfile;
export const loadPublicDirectoryProfile = directoryApi.loadPublicDirectoryProfile;
export const createClientMessageId = messagingApi.createClientMessageId;
export const listMessageConversations = messagingApi.listMessageConversations;
export const getMessageConversation = messagingApi.getMessageConversation;
export const sendPrivateMessage = messagingApi.sendPrivateMessage;
export const replyToMessageConversation = messagingApi.replyToMessageConversation;
export const listPostComments = communityApi.listPostComments;
export const createPostComment = communityApi.createPostComment;
export const updatePostComment = communityApi.updatePostComment;
export const deletePostComment = communityApi.deletePostComment;
export const setPostCommentLiked = communityApi.setPostCommentLiked;

export const markMessageConversationRead = messagingApi.markMessageConversationRead;
export const listBlockedProfiles = messagingApi.listBlockedProfiles;
export const blockMessageProfile = messagingApi.blockMessageProfile;
export const unblockMessageProfile = messagingApi.unblockMessageProfile;
export const createSupportRequest = messagingApi.createSupportRequest;
export const listSupportRequests = messagingApi.listSupportRequests;
export const getSupportRequest = messagingApi.getSupportRequest;
export const replySupportRequest = messagingApi.replySupportRequest;
export const resolveSupportRequest = messagingApi.resolveSupportRequest;

export async function createPublicInstitutionApplication(
  input: PublicInstitutionApplicationInput,
): Promise<{ application_id: string; status: "NEW"; created_at: string }> {
  return requestPublic("/v1/public/institution-applications", {
    organization_type: input.organizationType,
    organization_name: input.organizationName.trim(),
    contact_name: input.contactName.trim(),
    email: input.email.trim().toLowerCase(),
    ...(input.phone?.trim() ? { phone: input.phone.trim() } : {}),
    ...(input.registrationNumber?.trim() ? { registration_number: input.registrationNumber.trim() } : {}),
    city: input.city.trim(),
    state: input.state.trim().toUpperCase(),
    ...(input.websiteOrSocial?.trim() ? { website_or_social: input.websiteOrSocial.trim() } : {}),
    description: input.description.trim(),
    privacy_accepted: true,
  });
}

export async function listInstitutionApplications(
  status?: InstitutionApplicationStatus,
): Promise<InstitutionApplication[]> {
  const statusFilter = status ? `&status=${encodeURIComponent(status)}` : "";
  const response = await requestAuthenticated<{ applications: InstitutionApplication[] }>(
    "GET",
    `/v1/support/institution-applications?limit=200${statusFilter}`,
  );
  return response.applications || [];
}

export async function updateInstitutionApplicationStatus(
  applicationId: string,
  status: Exclude<InstitutionApplicationStatus, "NEW">,
  supportNotes?: string,
): Promise<InstitutionApplication> {
  return requestAuthenticated<InstitutionApplication>(
    "PATCH",
    `/v1/support/institution-applications/${encodeURIComponent(applicationId)}`,
    {
      status,
      support_notes: supportNotes?.trim() || null,
    },
  );
}

export const searchGlobalDirectory = directoryApi.searchGlobalDirectory;

export type CreateManagedInstitutionInput = {
  email: string;
  name: string;
  description?: string;
  city?: string;
};

function createManagedInstitutionAt(path: string, input: CreateManagedInstitutionInput): Promise<ManagedInstitution> {
  return requestAuthenticated<ManagedInstitution>("POST", path, {
    email: input.email.trim().toLowerCase(),
    name: input.name.trim(),
    description: input.description?.trim() || null,
    city: input.city?.trim() || null,
  });
}

export async function createManagedInstitution(input: CreateManagedInstitutionInput): Promise<ManagedInstitution> {
  return createManagedInstitutionAt("/v1/admin/institutions", input);
}

/** O suporte pode somente criar a conta institucional; gestão e listagem específica continuam com o administrador. */
export async function createSupportInstitution(input: CreateManagedInstitutionInput): Promise<ManagedInstitution> {
  return createManagedInstitutionAt("/v1/support/institutions", input);
}

export async function listManagedInstitutions(): Promise<ManagedInstitution[]> {
  const response = await requestAuthenticated<{ institutions: ManagedInstitution[] }>("GET", "/v1/admin/institutions");
  return response.institutions;
}

export async function listAdminAccounts(): Promise<ManagedAccountSummary[]> {
  const response = await requestAuthenticated<{ accounts: ManagedAccountSummary[] }>("GET", "/v1/admin/accounts?limit=100");
  return response.accounts;
}

export type CreateStaffAccountInput = {
  email: string;
  displayName: string;
  role: Extract<AccessRole, "admin" | "support" | "security">;
};

export async function createStaffAccount(
  input: CreateStaffAccountInput,
): Promise<ManagedAccountSummary> {
  return requestAuthenticated<ManagedAccountSummary>(
    "POST",
    "/v1/admin/staff-accounts",
    {
      email: input.email.trim().toLowerCase(),
      display_name: input.displayName.trim(),
      role: input.role,
    },
    true,
  );
}

export async function listStaffAccounts(): Promise<ManagedAccountSummary[]> {
  const response = await requestAuthenticated<{ accounts: ManagedAccountSummary[] }>(
    "GET",
    "/v1/admin/staff-accounts?limit=100",
  );
  return response.accounts;
}

export async function validateStaffAccount(
  firebaseUid: string,
  reason: string,
): Promise<ManagedAccountSummary> {
  return requestAuthenticated<ManagedAccountSummary>(
    "POST",
    `/v1/admin/staff-accounts/${encodeURIComponent(firebaseUid)}/validate`,
    { reason: reason.trim() },
    true,
  );
}

export async function loadAdminOperationsSummary(): Promise<AdminOperationsSummary> {
  return requestAuthenticated<AdminOperationsSummary>("GET", "/v1/admin/operations/summary");
}

export async function listSupportAccounts(): Promise<ManagedAccountSummary[]> {
  const response = await requestAuthenticated<{ accounts: ManagedAccountSummary[] }>("GET", "/v1/support/accounts?limit=100");
  return response.accounts;
}

export async function loadSecurityAccessOverview(): Promise<{
  accounts: ManagedAccountSummary[];
  recentEvents: AccessAuditEvent[];
}> {
  const response = await requestAuthenticated<{
    accounts: ManagedAccountSummary[];
    recent_events: AccessAuditEvent[];
  }>("GET", "/v1/security/accounts?limit=100&events_limit=50");
  return { accounts: response.accounts, recentEvents: response.recent_events };
}

export async function updateManagedAccountStatus(
  firebaseUid: string,
  status: "ACTIVE" | "SUSPENDED",
  reason: string,
): Promise<ManagedAccountSummary> {
  return requestAuthenticated<ManagedAccountSummary>(
    "POST",
    `/v1/security/accounts/${encodeURIComponent(firebaseUid)}/status`,
    { status, reason: reason.trim() },
    true,
  );
}

export async function loadSecurityMonitoringSummary(): Promise<SecurityMonitoringSummary> {
  return requestAuthenticated<SecurityMonitoringSummary>("GET", "/v1/security/monitoring/summary?events_limit=10");
}

export async function loadTrqBecSecurityStatus(): Promise<TrqBecSecurityStatus> {
  return requestAuthenticated<TrqBecSecurityStatus>("GET", "/v1/security/trq-bec/status");
}

export const setInstitutionBadgePolicy = institutionsApi.setInstitutionBadgePolicy;
export const setInstitutionMemberBadge = institutionsApi.setInstitutionMemberBadge;
export const applyInstitutionEventBadges = institutionsApi.applyInstitutionEventBadges;

export const activateInstitutionFundedEvent = institutionsApi.activateInstitutionFundedEvent;
export const closeInstitutionGroup = institutionsApi.closeInstitutionGroup;
export const createInstitutionFundedEvent = institutionsApi.createInstitutionFundedEvent;
export const createInstitutionGroup = institutionsApi.createInstitutionGroup;
export const endInstitutionFundedEvent = institutionsApi.endInstitutionFundedEvent;
export const inviteInstitutionSeller = institutionsApi.inviteInstitutionSeller;
export const leaveInstitutionMembership = institutionsApi.leaveInstitutionMembership;
export const listEntrepreneurFundedEvents = institutionsApi.listEntrepreneurFundedEvents;
export const listEntrepreneurInstitutionMemberships = institutionsApi.listEntrepreneurInstitutionMemberships;
export const listInstitutionFundedEvents = institutionsApi.listInstitutionFundedEvents;
export const listInstitutionGroupMemberships = institutionsApi.listInstitutionGroupMemberships;
export const listInstitutionGroups = institutionsApi.listInstitutionGroups;
export const loadEntrepreneurFundedEventReport = institutionsApi.loadEntrepreneurFundedEventReport;
export const loadInstitutionFundedEventReport = institutionsApi.loadInstitutionFundedEventReport;
export const loadInstitutionProfile = institutionsApi.loadInstitutionProfile;
export const loadInstitutionReportsSummary = institutionsApi.loadInstitutionReportsSummary;
export const loadInstitutionSalesReport = institutionsApi.loadInstitutionSalesReport;
export const removeInstitutionGroupMember = institutionsApi.removeInstitutionGroupMember;
export const respondInstitutionInvitation = institutionsApi.respondInstitutionInvitation;
export const setEntrepreneurFundedEventProductAllocations = institutionsApi.setEntrepreneurFundedEventProductAllocations;
export const setInstitutionFundedEventSellerAllocations = institutionsApi.setInstitutionFundedEventSellerAllocations;
export const updateInstitutionProfile = institutionsApi.updateInstitutionProfile;

export type MediaAssetStatus =
  | "pending"
  | "uploaded"
  | "processing"
  | "ready"
  | "rejected"
  | "quarantined"
  | "deleted"
  | "orphaned";

export type MediaAssetResponse = {
  media_id: string;
  status: MediaAssetStatus;
  download_url: string | null;
  download_expires_in: number | null;
};

export type MediaUploadAuthorizationInput = {
  entity_type: string;
  entity_id: string | null;
  media_role: string;
  original_filename: string;
  content_type: "image/jpeg" | "image/png" | "image/webp";
  size_bytes: number;
  client_request_id: string;
};

export type MediaUploadAuthorizationResponse = {
  media_id: string;
  object_key: string;
  upload_url: string;
  method: "PUT";
  expires_in: number;
  required_headers: Record<string, string>;
};

function normalizeMediaAsset(value: unknown): MediaAssetResponse {
  const item = asRecord(value);
  const mediaId = asString(item.media_id);
  const status = asString(item.status).toLowerCase();
  const allowedStatuses: MediaAssetStatus[] = [
    "pending",
    "uploaded",
    "processing",
    "ready",
    "rejected",
    "quarantined",
    "deleted",
    "orphaned",
  ];
  if (!mediaId || !allowedStatuses.includes(status as MediaAssetStatus)) {
    throw new TrqBecServiceError("O backend devolveu uma referência de imagem inválida.", "MEDIA_RESPONSE_INVALID");
  }

  const downloadExpiresIn = typeof item.download_expires_in === "number"
    && Number.isFinite(item.download_expires_in)
    && item.download_expires_in > 0
    ? Math.floor(item.download_expires_in)
    : null;
  return {
    media_id: mediaId,
    status: status as MediaAssetStatus,
    download_url: asNullableString(item.download_url),
    download_expires_in: downloadExpiresIn,
  };
}

export async function requestMediaUploadAuthorization(
  input: MediaUploadAuthorizationInput,
): Promise<MediaUploadAuthorizationResponse> {
  const response = await requestAuthenticated<unknown>("POST", "/v1/media/uploads", input);
  const item = asRecord(response);
  const mediaId = asString(item.media_id);
  const objectKey = asString(item.object_key);
  const uploadUrl = asString(item.upload_url);
  const method = asString(item.method).toUpperCase();
  const expiresIn = typeof item.expires_in === "number" && Number.isFinite(item.expires_in)
    ? Math.floor(item.expires_in)
    : 0;
  const rawHeaders = asRecord(item.required_headers);
  const requiredHeaders = Object.fromEntries(
    Object.entries(rawHeaders).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
  );

  if (
    !mediaId
    || !objectKey
    || !uploadUrl.startsWith("https://")
    || method !== "PUT"
    || expiresIn <= 0
    || Object.keys(requiredHeaders).length !== Object.keys(rawHeaders).length
  ) {
    throw new TrqBecServiceError("O backend devolveu uma autorização de upload inválida.", "MEDIA_UPLOAD_RESPONSE_INVALID");
  }

  return {
    media_id: mediaId,
    object_key: objectKey,
    upload_url: uploadUrl,
    method: "PUT",
    expires_in: expiresIn,
    required_headers: requiredHeaders,
  };
}

export async function confirmMediaUpload(mediaId: string): Promise<MediaAssetResponse> {
  const response = await requestAuthenticated<unknown>(
    "POST",
    `/v1/media/uploads/${encodeURIComponent(mediaId)}/confirm`,
  );
  return normalizeMediaAsset(response);
}

export async function fetchMediaAsset(mediaId: string): Promise<MediaAssetResponse> {
  const response = await requestAuthenticated<unknown>("GET", `/v1/media/${encodeURIComponent(mediaId)}`);
  return normalizeMediaAsset(response);
}

export async function deleteMediaAsset(mediaId: string): Promise<void> {
  await requestAuthenticated<unknown>("DELETE", `/v1/media/${encodeURIComponent(mediaId)}`);
}

export const publishCommunityPost = communityApi.publishCommunityPost;
export const updateCommunityPost = communityApi.updateCommunityPost;
export const deleteCommunityPost = communityApi.deleteCommunityPost;
export const publishCuratedPlace = communityApi.publishCuratedPlace;
export const deleteCuratedPlace = communityApi.deleteCuratedPlace;
export const publishLiveFair = communityApi.publishLiveFair;
export const finishLiveFair = communityApi.finishLiveFair;
export const deleteLiveFair = communityApi.deleteLiveFair;

export async function prepareAccountDeletion(): Promise<AccountDeletionPreparationResponse> {
  return requestAuthenticated("DELETE", "/v1/account", undefined, true);
}

export const batchActivateMarketplaceProducts = marketplaceApi.batchActivateMarketplaceProducts;
export const batchArchiveMarketplaceProducts = marketplaceApi.batchArchiveMarketplaceProducts;
export const batchUpdateLiveOffers = marketplaceApi.batchUpdateLiveOffers;
export const createMarketplaceProduct = marketplaceApi.createMarketplaceProduct;
export const deleteOwnLiveOffer = marketplaceApi.deleteOwnLiveOffer;
export const getOwnLiveOfferQr = marketplaceApi.getOwnLiveOfferQr;
export const getPublicMerchantCatalog = marketplaceApi.getPublicMerchantCatalog;
export const listOwnLiveOffers = marketplaceApi.listOwnLiveOffers;
export const listOwnMarketplaceProducts = marketplaceApi.listOwnMarketplaceProducts;
export const listPublicCatalogFeed = marketplaceApi.listPublicCatalogFeed;
export const loadOwnPurchases = marketplaceApi.loadOwnPurchases;
export const updateLiveOfferStatus = marketplaceApi.updateLiveOfferStatus;
export const updateMarketplaceProductStock = marketplaceApi.updateMarketplaceProductStock;

export const createCombinedCouponQr = trqBecApi.createCombinedCouponQr;
export const issueLiveOffer = trqBecApi.issueLiveOffer;
export const previewCouponQr = trqBecApi.previewCouponQr;
export const previewCouponQrGroup = trqBecApi.previewCouponQrGroup;
export const redeemCouponQr = trqBecApi.redeemCouponQr;
export const redeemCouponQrGroup = trqBecApi.redeemCouponQrGroup;
