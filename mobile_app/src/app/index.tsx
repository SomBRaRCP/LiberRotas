import { Ionicons } from "@expo/vector-icons";
import { Redirect, router, type Href, useLocalSearchParams } from "expo-router";
import { ComponentProps, useState } from "react";
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { AppButton, CheckOption, FormField, LoadingScreen } from "@/components/ui";
import { colors, radius, shadow } from "@/constants/theme";
import { useApp } from "@/context/app-context";
import {
  createPublicInstitutionApplication,
  TrqBecServiceError,
  type PublicInstitutionApplicationInput,
} from "@/security/trq-bec/service";
import { normalizeSafeReturnTo } from "@/utils/share";

type IconName = ComponentProps<typeof Ionicons>["name"];

type FeatureCard = {
  description: string;
  detailLead?: string;
  detailParagraphs?: string[];
  highlights?: string[];
  icon: IconName;
  registrationAvailable?: boolean;
  title: string;
};

const steps: FeatureCard[] = [
  {
    icon: "search-outline",
    title: "Descubra",
    description: "Encontre empreendedores, produtos, publicações, cupons, feiras e locais em um único feed.",
    detailLead: "O LiberRotas reúne descobertas locais em um só caminho, para você não precisar procurar cada iniciativa em uma página diferente.",
    detailParagraphs: [
      "No Feed, você encontra publicações da comunidade, produtos, ofertas, feiras e pontos de interesse. A pesquisa ajuda a localizar um perfil ou conteúdo específico.",
      "Cada resultado leva ao perfil responsável. Assim, você consegue entender quem publicou, conhecer sua atuação e conferir outras experiências oferecidas pela mesma pessoa ou organização.",
    ],
    highlights: ["Pesquisa unificada", "Perfis responsáveis pelo conteúdo", "Produtos, feiras, ofertas e locais no mesmo aplicativo"],
  },
  {
    icon: "people-outline",
    title: "Conecte-se",
    description: "Conheça o perfil de quem publica, envie mensagens e acompanhe iniciativas da comunidade.",
    detailLead: "Conectar-se significa conhecer as pessoas e organizações por trás de cada experiência local.",
    detailParagraphs: [
      "Os perfis públicos apresentam a atividade, a cidade e os conteúdos compartilhados. Quando permitido, você pode iniciar uma conversa privada sem expor dados pessoais no Feed.",
      "Empreendedores também podem participar de grupos de instituições autorizadas. As permissões do backend garantem que cada conta veja somente as funções liberadas para o seu perfil.",
    ],
    highlights: ["Perfis públicos identificados", "Mensagens privadas entre contas", "Grupos e iniciativas com acesso controlado"],
  },
  {
    icon: "qr-code-outline",
    title: "Viva a experiência",
    description: "Use cupons, valide ofertas por QR Code e encontre feiras e empreendimentos no mapa.",
    detailLead: "Depois de descobrir e conhecer um perfil, o aplicativo ajuda você a chegar à experiência e utilizar benefícios disponíveis.",
    detailParagraphs: [
      "O mapa apresenta feiras e pontos locais. As ofertas mostram preço, desconto, validade e disponibilidade confirmados pelo backend, sem confiar em valores calculados somente no celular.",
      "No resgate por QR Code, o visitante confere a oferta antes de confirmar. Cada uso é validado online para evitar repetição e manter estoque e histórico consistentes.",
    ],
    highlights: ["Feiras e empreendimentos no mapa", "Ofertas com validade e estoque", "QR Code confirmado pelo backend"],
  },
];

const accountProfiles: FeatureCard[] = [
  {
    icon: "person-outline",
    title: "Visitantes",
    description: "Exploram o feed, descobrem produtos e feiras, usam cupons, salvam interesses e conversam com perfis.",
    detailLead: "A conta de Visitante é indicada para quem deseja conhecer, acompanhar e aproveitar experiências da comunidade.",
    detailParagraphs: [
      "Ao criar o perfil, a pessoa informa nome público, cidade e interesses. Depois pode pesquisar conteúdos, salvar locais e ofertas, comentar publicações e conversar com outros perfis.",
      "Visitantes podem ler e resgatar ofertas autorizadas, mas não administram produtos, estoque, grupos institucionais ou funções internas da plataforma.",
    ],
    highlights: ["Cadastro público pelo aplicativo", "Feed, mapa, favoritos e mensagens", "Leitura e resgate de ofertas por QR Code"],
    registrationAvailable: true,
  },
  {
    icon: "storefront-outline",
    title: "Empreendedores",
    description: "Criam uma vitrine, divulgam produtos, emitem ofertas, participam de grupos e compartilham feiras ao vivo.",
    detailLead: "A conta de Empreendedor transforma o perfil em uma vitrine para produtos, serviços e experiências locais.",
    detailParagraphs: [
      "O empreendedor pode cadastrar produtos com preço e estoque, publicar imagens, criar ofertas temporárias e apresentar feiras no mapa. Os dados comerciais importantes ficam no backend autoritativo.",
      "Também pode receber convites de instituições, participar de grupos e acompanhar relatórios permitidos. Algumas operações protegidas dependem de conta e dispositivo aprovados.",
    ],
    highlights: ["Vitrine pública com produtos", "Ofertas e QR Code com estoque controlado", "Feiras, grupos e parcerias institucionais"],
    registrationAvailable: true,
  },
  {
    icon: "business-outline",
    title: "Instituições",
    description: "Organizam grupos de empreendedores, promovem eventos e acompanham relatórios autorizados de seus afiliados.",
    detailLead: "Instituições representam empresas, associações, ONGs e iniciativas autorizadas a organizar ações coletivas no LiberRotas.",
    detailParagraphs: [
      "Essas contas podem manter um perfil institucional, criar grupos, convidar empreendedores e organizar eventos financiados com regras e períodos definidos.",
      "Os relatórios mostram somente informações agregadas e autorizadas dos afiliados. A instituição não recebe senha, chave Pix, comprador individual ou dados privados que não sejam necessários para sua atuação.",
      "Por segurança, Instituição não é uma opção do cadastro público. A organização usa o botão existente abaixo destes cartões para enviar seus dados ao Suporte e aguardar análise.",
    ],
    highlights: ["Conta criada após análise", "Grupos e convites de filiação", "Eventos financiados e relatórios agregados"],
  },
];

const benefits: FeatureCard[] = [
  {
    icon: "megaphone-outline",
    title: "Mais visibilidade local",
    description: "Produtos, histórias, feiras e oportunidades chegam a pessoas interessadas na região.",
  },
  {
    icon: "map-outline",
    title: "Informação em um só lugar",
    description: "Feed, mapa, perfis, vitrines e cupons trabalham juntos para facilitar cada descoberta.",
  },
  {
    icon: "shield-checkmark-outline",
    title: "Acessos responsáveis",
    description: "Cada conta recebe apenas as funções e permissões confirmadas pelo sistema.",
  },
  {
    icon: "heart-outline",
    title: "Economia que aproxima",
    description: "A plataforma valoriza relações locais, colaboração e o trabalho de quem movimenta a comunidade.",
  },
];

function FeatureGrid({
  cards,
  compact,
  highlighted = false,
  onSelect,
}: {
  cards: FeatureCard[];
  compact: boolean;
  highlighted?: boolean;
  onSelect?: (card: FeatureCard) => void;
}) {
  return (
    <View style={[styles.cardGrid, compact && styles.cardGridCompact]}>
      {cards.map((card) => {
        const cardStyle = [
          styles.featureCard,
          highlighted && styles.featureCardHighlighted,
          compact && styles.featureCardCompact,
        ];
        const content = (
          <>
            <View style={[styles.cardIcon, highlighted && styles.cardIconHighlighted]}>
              <Ionicons color={highlighted ? colors.surface : colors.primary} name={card.icon} size={24} />
            </View>
            <Text style={styles.cardTitle}>{card.title}</Text>
            <Text style={styles.cardDescription}>{card.description}</Text>
          </>
        );
        return onSelect ? (
          <Pressable
            accessibilityHint="Abre uma explicação detalhada em uma caixa sobreposta"
            accessibilityLabel={`Saiba mais sobre ${card.title}`}
            accessibilityRole="button"
            key={card.title}
            onPress={() => onSelect(card)}
            style={({ pressed }) => [cardStyle, pressed && styles.pressed]}
          >
            {content}
          </Pressable>
        ) : (
          <View key={card.title} style={cardStyle}>
            {content}
          </View>
        );
      })}
    </View>
  );
}

function FeatureDetailModal({
  card,
  onClose,
  onRegister,
}: {
  card: FeatureCard | null;
  onClose: () => void;
  onRegister: () => void;
}) {
  if (!card) return null;

  return (
    <Modal animationType="fade" onRequestClose={onClose} transparent visible>
      <SafeAreaView style={styles.modalBackdrop}>
        <View accessibilityViewIsModal style={styles.detailModalCard}>
          <View style={styles.detailModalHeader}>
            <View style={styles.detailModalIcon}>
              <Ionicons color={colors.surface} name={card.icon} size={26} />
            </View>
            <View style={styles.modalHeaderCopy}>
              <Text style={styles.detailModalEyebrow}>SAIBA MAIS</Text>
              <Text style={styles.modalTitle}>{card.title}</Text>
            </View>
            <Pressable
              accessibilityLabel={`Fechar explicação sobre ${card.title}`}
              accessibilityRole="button"
              onPress={onClose}
              style={styles.modalClose}
            >
              <Ionicons color={colors.primaryDark} name="close" size={24} />
            </Pressable>
          </View>

          <ScrollView contentContainerStyle={styles.detailModalContent} showsVerticalScrollIndicator={false}>
            {card.detailLead ? <Text style={styles.detailModalLead}>{card.detailLead}</Text> : null}
            {card.detailParagraphs?.map((paragraph) => (
              <Text key={paragraph} style={styles.detailModalParagraph}>
                {paragraph}
              </Text>
            ))}
            {card.highlights?.length ? (
              <View style={styles.detailHighlights}>
                {card.highlights.map((highlight) => (
                  <View key={highlight} style={styles.detailHighlightRow}>
                    <Ionicons color={colors.success} name="checkmark-circle" size={19} />
                    <Text style={styles.detailHighlightText}>{highlight}</Text>
                  </View>
                ))}
              </View>
            ) : null}
            {card.registrationAvailable ? (
              <AppButton onPress={onRegister} style={styles.detailRegisterButton}>
                Registre-se
              </AppButton>
            ) : null}
          </ScrollView>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type InstitutionApplicationForm = PublicInstitutionApplicationInput & {
  privacyAccepted: boolean;
};

const emptyInstitutionApplication: InstitutionApplicationForm = {
  organizationType: "COMPANY",
  organizationName: "",
  contactName: "",
  email: "",
  phone: "",
  registrationNumber: "",
  city: "",
  state: "",
  websiteOrSocial: "",
  description: "",
  privacyAccepted: false,
};

function InstitutionApplicationModal({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const [form, setForm] = useState<InstitutionApplicationForm>(emptyInstitutionApplication);
  const [error, setError] = useState("");
  const [protocol, setProtocol] = useState("");
  const [isSending, setIsSending] = useState(false);

  function update<K extends keyof InstitutionApplicationForm>(field: K, value: InstitutionApplicationForm[K]) {
    setForm((current) => ({ ...current, [field]: value }));
    setError("");
  }

  function close() {
    if (isSending) return;
    setForm(emptyInstitutionApplication);
    setError("");
    setProtocol("");
    onClose();
  }

  async function submit() {
    const state = form.state.trim().toUpperCase();
    if (
      form.organizationName.trim().length < 2
      || form.contactName.trim().length < 3
      || !EMAIL_PATTERN.test(form.email.trim())
      || form.city.trim().length < 2
      || !/^[A-Z]{2}$/.test(state)
      || form.description.trim().length < 20
    ) {
      setError("Preencha os campos obrigatórios. A descrição deve ter pelo menos 20 caracteres e a UF deve ter 2 letras.");
      return;
    }
    if (!form.privacyAccepted) {
      setError("Confirme o uso dos dados para que o Suporte possa entrar em contato.");
      return;
    }

    setIsSending(true);
    setError("");
    try {
      const result = await createPublicInstitutionApplication({ ...form, state });
      setProtocol(result.application_id);
    } catch (submitError) {
      setError(
        submitError instanceof TrqBecServiceError
          ? submitError.message
          : "Não foi possível enviar a solicitação. Tente novamente.",
      );
    } finally {
      setIsSending(false);
    }
  }

  return (
    <Modal animationType="fade" onRequestClose={close} transparent visible={visible}>
      <SafeAreaView style={styles.modalBackdrop}>
        <View style={styles.modalCard}>
          <View style={styles.modalHeader}>
            <View style={styles.modalHeaderCopy}>
              <Text style={styles.modalTitle}>Registrar interesse institucional</Text>
              <Text style={styles.modalLead}>
                Envie os dados da empresa ou ONG para análise. O formulário não cria uma conta automaticamente.
              </Text>
            </View>
            <Pressable accessibilityLabel="Fechar formulário" accessibilityRole="button" onPress={close} style={styles.modalClose}>
              <Ionicons color={colors.primaryDark} name="close" size={24} />
            </Pressable>
          </View>

          {protocol ? (
            <View style={styles.applicationSuccess}>
              <Ionicons color={colors.success} name="checkmark-circle-outline" size={48} />
              <Text style={styles.applicationSuccessTitle}>Solicitação enviada ao Suporte</Text>
              <Text style={styles.applicationSuccessText}>
                A equipe analisará os dados e entrará em contato pelo e-mail informado. Isso ainda não cria uma conta institucional.
              </Text>
              <Text selectable style={styles.applicationProtocol}>Protocolo: {protocol}</Text>
              <AppButton onPress={close}>Concluir</AppButton>
            </View>
          ) : (
            <ScrollView contentContainerStyle={styles.applicationForm} keyboardShouldPersistTaps="handled">
              <Text style={styles.formSectionLabel}>Tipo de organização *</Text>
              <View accessibilityRole="radiogroup" style={styles.organizationTypes}>
                {(["COMPANY", "NGO"] as const).map((type) => {
                  const selected = form.organizationType === type;
                  return (
                    <Pressable
                      accessibilityRole="radio"
                      accessibilityState={{ checked: selected }}
                      key={type}
                      onPress={() => update("organizationType", type)}
                      style={[styles.organizationType, selected && styles.organizationTypeSelected]}
                    >
                      <Ionicons
                        color={selected ? colors.surface : colors.primary}
                        name={type === "COMPANY" ? "business-outline" : "heart-outline"}
                        size={20}
                      />
                      <Text style={[styles.organizationTypeText, selected && styles.organizationTypeTextSelected]}>
                        {type === "COMPANY" ? "Empresa" : "ONG"}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
              <FormField label="Nome da empresa ou ONG *" maxLength={160} onChangeText={(value) => update("organizationName", value)} value={form.organizationName} />
              <FormField label="Nome da pessoa responsável *" maxLength={120} onChangeText={(value) => update("contactName", value)} value={form.contactName} />
              <View style={styles.formRow}>
                <FormField autoCapitalize="none" containerStyle={styles.formRowField} keyboardType="email-address" label="E-mail para contato *" maxLength={254} onChangeText={(value) => update("email", value)} value={form.email} />
                <FormField containerStyle={styles.formRowField} keyboardType="phone-pad" label="Telefone/WhatsApp" maxLength={30} onChangeText={(value) => update("phone", value)} value={form.phone} />
              </View>
              <View style={styles.formRow}>
                <FormField containerStyle={styles.formRowField} label="CNPJ ou registro (opcional)" maxLength={30} onChangeText={(value) => update("registrationNumber", value)} value={form.registrationNumber} />
                <FormField autoCapitalize="characters" containerStyle={styles.stateField} label="UF *" maxLength={2} onChangeText={(value) => update("state", value.toUpperCase())} value={form.state} />
              </View>
              <FormField label="Cidade *" maxLength={120} onChangeText={(value) => update("city", value)} value={form.city} />
              <FormField autoCapitalize="none" label="Site ou rede social (opcional)" maxLength={500} onChangeText={(value) => update("websiteOrSocial", value)} value={form.websiteOrSocial} />
              <FormField
                label="Conte sobre a organização e por que deseja participar *"
                maxLength={2_000}
                multiline
                onChangeText={(value) => update("description", value)}
                style={styles.descriptionField}
                textAlignVertical="top"
                value={form.description}
              />
              <Text style={styles.characterCount}>{form.description.length}/2000</Text>
              <CheckOption
                label="Autorizo o uso destes dados somente para análise e contato do LiberRotas."
                onPress={() => update("privacyAccepted", !form.privacyAccepted)}
                selected={form.privacyAccepted}
              />
              {error ? <Text accessibilityRole="alert" style={styles.formError}>{error}</Text> : null}
              <View style={styles.formActions}>
                <AppButton disabled={isSending} onPress={close} style={styles.formAction} variant="secondary">Cancelar</AppButton>
                <AppButton disabled={isSending} onPress={submit} style={styles.formAction}>
                  {isSending ? "Enviando..." : "Enviar ao Suporte"}
                </AppButton>
              </View>
            </ScrollView>
          )}
        </View>
      </SafeAreaView>
    </Modal>
  );
}

export default function HomeScreen() {
  const { width } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const { accessDestination, hasFirebaseSession, isAuthenticated, isHydrated, isResolvingAccess } = useApp();
  const { returnTo } = useLocalSearchParams<{ returnTo?: string | string[] }>();
  const safeReturnTo = normalizeSafeReturnTo(returnTo);
  const compact = width < 760;
  const [isInstitutionFormOpen, setIsInstitutionFormOpen] = useState(false);
  const [selectedFeature, setSelectedFeature] = useState<FeatureCard | null>(null);
  const loginHref = safeReturnTo
    ? ({ pathname: "/login", params: { returnTo: safeReturnTo } } as unknown as Href)
    : ("/login" as Href);

  function openAccess() {
    router.push(loginHref);
  }

  function openRegistration() {
    setSelectedFeature(null);
    router.push("/register" as Href);
  }

  if (!isHydrated || ((isAuthenticated || hasFirebaseSession) && isResolvingAccess)) {
    return <LoadingScreen />;
  }
  if (isAuthenticated || hasFirebaseSession) {
    return <Redirect href={accessDestination as Href} />;
  }

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <ScrollView
        contentContainerStyle={[styles.page, { paddingBottom: Math.max(36, insets.bottom + 24) }]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.navigation}>
          <View style={styles.brand}>
            <View style={styles.brandMark}>
              <Text style={styles.brandMarkText}>LR</Text>
            </View>
            <View>
              <Text style={styles.brandName}>LiberRotas</Text>
              {!compact ? <Text style={styles.brandSubtitle}>conexões que movimentam a comunidade</Text> : null}
            </View>
          </View>
          <Pressable
            accessibilityLabel="Entrar ou registrar uma conta"
            accessibilityRole="button"
            onPress={openAccess}
            style={({ pressed }) => [styles.accessButton, pressed && styles.pressed]}
          >
            <Ionicons color={colors.surface} name="person-circle-outline" size={20} />
            <Text style={styles.accessButtonText}>Entrar/Registrar</Text>
          </Pressable>
        </View>

        <View style={[styles.hero, compact && styles.heroCompact]}>
          <View style={styles.heroCopy}>
            <View style={styles.eyebrow}>
              <Ionicons color={colors.success} name="location-outline" size={16} />
              <Text style={styles.eyebrowText}>TURISMO, COMÉRCIO E EXPERIÊNCIAS LOCAIS</Text>
            </View>
            <Text style={[styles.heroTitle, compact && styles.heroTitleCompact]}>
              Descubra quem faz a cidade acontecer.
            </Text>
            <Text style={styles.heroLead}>
              O LiberRotas aproxima pessoas, empreendedores e instituições para dar visibilidade ao trabalho local,
              facilitar descobertas e transformar encontros em novas oportunidades.
            </Text>
            <View style={styles.heroTags}>
              <View style={styles.heroTag}><Text style={styles.heroTagText}>Feed único</Text></View>
              <View style={styles.heroTag}><Text style={styles.heroTagText}>Feiras ao vivo</Text></View>
              <View style={styles.heroTag}><Text style={styles.heroTagText}>Cupons por QR Code</Text></View>
            </View>
          </View>

          <View style={[styles.heroPanel, compact && styles.heroPanelCompact]}>
            <View style={styles.heroPanelIcon}>
              <Ionicons color={colors.surface} name="compass-outline" size={34} />
            </View>
            <Text style={styles.heroPanelTitle}>Uma rota feita por pessoas</Text>
            <Text style={styles.heroPanelText}>
              Cada produto, publicação, evento e localização leva você ao perfil responsável por aquela experiência.
            </Text>
            <View style={styles.heroPanelLine} />
            <View style={styles.heroPanelMetric}>
              <Text style={styles.heroPanelMetricValue}>3</Text>
              <Text style={styles.heroPanelMetricLabel}>tipos de perfil que colaboram entre si</Text>
            </View>
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionEyebrow}>COMO FUNCIONA</Text>
          <Text style={styles.sectionTitle}>Do primeiro interesse ao encontro local</Text>
          <Text style={styles.sectionLead}>
            O conteúdo circula em um feed comum. Assim, visitantes encontram novidades e quem empreende consegue
            apresentar seu trabalho sem depender de várias páginas separadas.
          </Text>
          <FeatureGrid cards={steps} compact={compact} onSelect={setSelectedFeature} />
        </View>

        <View style={[styles.section, styles.accountsSection]}>
          <Text style={styles.sectionEyebrow}>QUEM PARTICIPA</Text>
          <Text style={styles.sectionTitle}>Contas diferentes, objetivos complementares</Text>
          <Text style={styles.sectionLead}>
            Visitantes e empreendedores podem se registrar. Contas institucionais são criadas somente por equipes
            autorizadas do LiberRotas e recebem recursos específicos para organizar seus grupos.
          </Text>
          <FeatureGrid cards={accountProfiles} compact={compact} highlighted onSelect={setSelectedFeature} />
          <View style={styles.institutionNotice}>
            <Ionicons color={colors.primary} name="information-circle-outline" size={22} />
            <View style={styles.institutionNoticeContent}>
              <Text style={styles.institutionNoticeText}>
                Instituições podem representar associações, organizações e iniciativas locais. Elas não são escolhidas
                livremente no cadastro público.
              </Text>
              <Pressable
                accessibilityLabel="Abrir formulário para registrar uma instituição"
                accessibilityRole="button"
                onPress={() => setIsInstitutionFormOpen(true)}
                style={({ pressed }) => [styles.institutionRegisterButton, pressed && styles.pressed]}
              >
                <Ionicons color={colors.surface} name="document-text-outline" size={18} />
                <Text style={styles.institutionRegisterButtonText}>Registrar Instituição</Text>
              </Pressable>
            </View>
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionEyebrow}>BENEFÍCIOS</Text>
          <Text style={styles.sectionTitle}>Tecnologia a serviço da comunidade</Text>
          <FeatureGrid cards={benefits} compact={compact} />
        </View>

        <View style={[styles.purpose, compact && styles.purposeCompact]}>
          <View style={styles.purposeIcon}>
            <Ionicons color={colors.accent} name="sparkles-outline" size={28} />
          </View>
          <View style={styles.purposeCopy}>
            <Text style={styles.purposeEyebrow}>A INTENÇÃO DO PROJETO</Text>
            <Text style={styles.purposeTitle}>Fortalecer caminhos que já existem.</Text>
            <Text style={styles.purposeText}>
              O LiberRotas nasceu para apoiar a economia local, o turismo comunitário e a colaboração entre pessoas
              que produzem, organizam e valorizam experiências próximas. A tecnologia é o meio; o protagonismo
              continua sendo da comunidade.
            </Text>
          </View>
        </View>

        <View style={[styles.finalCall, compact && styles.finalCallCompact]}>
          <View style={styles.finalCallCopy}>
            <Text style={styles.finalCallTitle}>Pronto para encontrar sua próxima rota?</Text>
            <Text style={styles.finalCallText}>
              Entre na sua conta ou crie um perfil de visitante ou empreendedor.
            </Text>
          </View>
          <Pressable
            accessibilityRole="button"
            onPress={openAccess}
            style={({ pressed }) => [styles.finalCallButton, pressed && styles.pressed]}
          >
            <Text style={styles.finalCallButtonText}>Entrar/Registrar</Text>
            <Ionicons color={colors.primaryDark} name="arrow-forward-outline" size={20} />
          </Pressable>
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerBrand}>LiberRotas</Text>
          <Text style={styles.footerText}>Conexões locais, experiências reais.</Text>
        </View>
      </ScrollView>
      <FeatureDetailModal
        card={selectedFeature}
        onClose={() => setSelectedFeature(null)}
        onRegister={openRegistration}
      />
      <InstitutionApplicationModal onClose={() => setIsInstitutionFormOpen(false)} visible={isInstitutionFormOpen} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.background, flex: 1 },
  page: { backgroundColor: colors.background },
  navigation: {
    alignItems: "center",
    alignSelf: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    maxWidth: 1180,
    paddingHorizontal: 22,
    paddingVertical: 16,
    width: "100%",
  },
  brand: { alignItems: "center", flexDirection: "row", gap: 11 },
  brandMark: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: 18,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  brandMarkText: { color: colors.surface, fontSize: 14, fontWeight: "900" },
  brandName: { color: colors.primaryDark, fontSize: 20, fontWeight: "900" },
  brandSubtitle: { color: colors.textMuted, fontSize: 10, marginTop: 1 },
  accessButton: {
    alignItems: "center",
    backgroundColor: colors.accent,
    borderRadius: radius.pill,
    flexDirection: "row",
    gap: 7,
    minHeight: 44,
    paddingHorizontal: 18,
  },
  accessButtonText: { color: colors.surface, fontSize: 13, fontWeight: "800" },
  pressed: { opacity: 0.72 },
  hero: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: colors.cream,
    borderRadius: 30,
    flexDirection: "row",
    gap: 42,
    maxWidth: 1180,
    overflow: "hidden",
    padding: 52,
    width: "96%",
  },
  heroCompact: { alignItems: "stretch", flexDirection: "column", gap: 28, padding: 26 },
  heroCopy: { flex: 1 },
  eyebrow: {
    alignItems: "center",
    alignSelf: "flex-start",
    backgroundColor: "#E8F6EF",
    borderRadius: radius.pill,
    flexDirection: "row",
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  eyebrowText: { color: colors.success, fontSize: 10, fontWeight: "900", letterSpacing: 0.6 },
  heroTitle: {
    color: colors.primaryDark,
    fontSize: 54,
    fontWeight: "900",
    letterSpacing: -1.5,
    lineHeight: 58,
    marginTop: 20,
    maxWidth: 650,
  },
  heroTitleCompact: { fontSize: 38, letterSpacing: -0.8, lineHeight: 42 },
  heroLead: { color: colors.text, fontSize: 17, lineHeight: 26, marginTop: 18, maxWidth: 660 },
  heroTags: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 24 },
  heroTag: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.pill,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  heroTagText: { color: colors.primary, fontSize: 11, fontWeight: "800" },
  heroPanel: {
    backgroundColor: colors.primaryDark,
    borderRadius: 26,
    maxWidth: 330,
    padding: 28,
    width: "34%",
    ...shadow,
  },
  heroPanelCompact: { maxWidth: undefined, width: "100%" },
  heroPanelIcon: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: 24,
    height: 48,
    justifyContent: "center",
    width: 48,
  },
  heroPanelTitle: { color: colors.surface, fontSize: 21, fontWeight: "900", marginTop: 18 },
  heroPanelText: { color: "#DCE6FF", fontSize: 13, lineHeight: 20, marginTop: 9 },
  heroPanelLine: { backgroundColor: "#31508D", height: 1, marginVertical: 22 },
  heroPanelMetric: { alignItems: "center", flexDirection: "row", gap: 12 },
  heroPanelMetricValue: { color: colors.accentSoft, fontSize: 34, fontWeight: "900" },
  heroPanelMetricLabel: { color: colors.surface, flex: 1, fontSize: 11, lineHeight: 16 },
  section: {
    alignSelf: "center",
    maxWidth: 1120,
    paddingHorizontal: 22,
    paddingTop: 78,
    width: "100%",
  },
  accountsSection: { paddingTop: 86 },
  sectionEyebrow: { color: colors.accent, fontSize: 11, fontWeight: "900", letterSpacing: 1.1 },
  sectionTitle: {
    color: colors.primaryDark,
    fontSize: 34,
    fontWeight: "900",
    letterSpacing: -0.6,
    lineHeight: 40,
    marginTop: 9,
    maxWidth: 760,
  },
  sectionLead: { color: colors.textMuted, fontSize: 15, lineHeight: 23, marginTop: 12, maxWidth: 800 },
  cardGrid: { flexDirection: "row", gap: 16, marginTop: 30 },
  cardGridCompact: { flexDirection: "column" },
  featureCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 22,
    borderWidth: 1,
    flex: 1,
    minHeight: 210,
    padding: 24,
    ...shadow,
  },
  featureCardCompact: { minHeight: 0 },
  featureCardHighlighted: { backgroundColor: "#F4F7FF", borderColor: "#C9D7F5" },
  cardIcon: {
    alignItems: "center",
    backgroundColor: colors.cream,
    borderRadius: 22,
    height: 46,
    justifyContent: "center",
    width: 46,
  },
  cardIconHighlighted: { backgroundColor: colors.primary },
  cardTitle: { color: colors.primaryDark, fontSize: 18, fontWeight: "900", marginTop: 18 },
  cardDescription: { color: colors.textMuted, fontSize: 13, lineHeight: 20, marginTop: 8 },
  institutionNotice: {
    alignItems: "flex-start",
    backgroundColor: colors.cream,
    borderRadius: radius.medium,
    flexDirection: "row",
    gap: 10,
    marginTop: 18,
    padding: 16,
  },
  institutionNoticeText: { color: colors.primaryDark, flex: 1, fontSize: 12, lineHeight: 18 },
  institutionNoticeContent: { alignItems: "flex-start", flex: 1, gap: 13 },
  institutionRegisterButton: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: radius.pill,
    flexDirection: "row",
    gap: 7,
    minHeight: 42,
    paddingHorizontal: 17,
  },
  institutionRegisterButtonText: { color: colors.surface, fontSize: 12, fontWeight: "900" },
  modalBackdrop: { alignItems: "center", backgroundColor: "rgba(7, 29, 69, 0.72)", flex: 1, justifyContent: "center", padding: 16 },
  modalCard: { backgroundColor: colors.background, borderRadius: 24, maxHeight: "94%", maxWidth: 760, overflow: "hidden", width: "100%", ...shadow },
  modalHeader: { alignItems: "flex-start", backgroundColor: colors.cream, flexDirection: "row", gap: 14, padding: 22 },
  modalHeaderCopy: { flex: 1 },
  modalTitle: { color: colors.primaryDark, fontSize: 22, fontWeight: "900" },
  modalLead: { color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 },
  modalClose: { alignItems: "center", backgroundColor: colors.surface, borderRadius: 20, height: 40, justifyContent: "center", width: 40 },
  detailModalCard: {
    backgroundColor: colors.background,
    borderRadius: 24,
    maxHeight: "88%",
    maxWidth: 620,
    overflow: "hidden",
    width: "100%",
    ...shadow,
  },
  detailModalHeader: {
    alignItems: "center",
    backgroundColor: colors.cream,
    flexDirection: "row",
    gap: 14,
    padding: 22,
  },
  detailModalIcon: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: 24,
    height: 48,
    justifyContent: "center",
    width: 48,
  },
  detailModalEyebrow: { color: colors.accent, fontSize: 10, fontWeight: "900", letterSpacing: 1 },
  detailModalContent: { gap: 14, padding: 22 },
  detailModalLead: { color: colors.primaryDark, fontSize: 16, fontWeight: "700", lineHeight: 24 },
  detailModalParagraph: { color: colors.text, fontSize: 14, lineHeight: 22 },
  detailHighlights: {
    backgroundColor: "#F4F7FF",
    borderColor: "#C9D7F5",
    borderRadius: radius.medium,
    borderWidth: 1,
    gap: 10,
    padding: 14,
  },
  detailHighlightRow: { alignItems: "flex-start", flexDirection: "row", gap: 9 },
  detailHighlightText: { color: colors.primaryDark, flex: 1, fontSize: 13, lineHeight: 19 },
  detailRegisterButton: { marginTop: 4 },
  applicationForm: { gap: 12, padding: 22 },
  formSectionLabel: { color: colors.primaryDark, fontSize: 12, fontWeight: "900" },
  organizationTypes: { flexDirection: "row", gap: 10 },
  organizationType: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, flex: 1, flexDirection: "row", gap: 8, justifyContent: "center", minHeight: 50 },
  organizationTypeSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  organizationTypeText: { color: colors.primary, fontSize: 13, fontWeight: "800" },
  organizationTypeTextSelected: { color: colors.surface },
  formRow: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  formRowField: { flex: 1, minWidth: 230 },
  stateField: { minWidth: 110, width: 120 },
  descriptionField: { minHeight: 92 },
  characterCount: { color: colors.textMuted, fontSize: 10, marginTop: -8, textAlign: "right" },
  formError: { backgroundColor: "#FDE8E7", borderRadius: radius.medium, color: colors.danger, fontSize: 12, lineHeight: 18, padding: 12 },
  formActions: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  formAction: { flex: 1, minWidth: 180 },
  applicationSuccess: { alignItems: "center", gap: 13, padding: 32 },
  applicationSuccessTitle: { color: colors.primaryDark, fontSize: 21, fontWeight: "900", textAlign: "center" },
  applicationSuccessText: { color: colors.textMuted, fontSize: 13, lineHeight: 20, maxWidth: 520, textAlign: "center" },
  applicationProtocol: { color: colors.primary, fontSize: 11, fontWeight: "700", textAlign: "center" },
  purpose: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: colors.primaryDark,
    borderRadius: 28,
    flexDirection: "row",
    gap: 24,
    marginTop: 86,
    maxWidth: 1120,
    padding: 36,
    width: "92%",
  },
  purposeCompact: { alignItems: "flex-start", flexDirection: "column", padding: 26 },
  purposeIcon: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: 28,
    height: 56,
    justifyContent: "center",
    width: 56,
  },
  purposeCopy: { flex: 1 },
  purposeEyebrow: { color: colors.accentSoft, fontSize: 10, fontWeight: "900", letterSpacing: 1 },
  purposeTitle: { color: colors.surface, fontSize: 26, fontWeight: "900", marginTop: 7 },
  purposeText: { color: "#DCE6FF", fontSize: 14, lineHeight: 22, marginTop: 9, maxWidth: 870 },
  finalCall: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: colors.accent,
    borderRadius: 26,
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 28,
    maxWidth: 1120,
    padding: 28,
    width: "92%",
  },
  finalCallCompact: { alignItems: "stretch", flexDirection: "column", gap: 20 },
  finalCallCopy: { flex: 1, paddingRight: 16 },
  finalCallTitle: { color: colors.surface, fontSize: 23, fontWeight: "900" },
  finalCallText: { color: "#FFF1E8", fontSize: 13, lineHeight: 19, marginTop: 6 },
  finalCallButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: radius.pill,
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 48,
    paddingHorizontal: 20,
  },
  finalCallButtonText: { color: colors.primaryDark, fontSize: 13, fontWeight: "900" },
  footer: { alignItems: "center", marginTop: 44, paddingHorizontal: 22 },
  footerBrand: { color: colors.primaryDark, fontSize: 16, fontWeight: "900" },
  footerText: { color: colors.textMuted, fontSize: 11, marginTop: 4 },
});
