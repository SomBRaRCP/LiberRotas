import { Ionicons } from "@expo/vector-icons";
import { useEffect, useRef, useState } from "react";
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, type Href } from "expo-router";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { BrandHeader } from "@/components/brand-header";
import { ImageViewerModal } from "@/components/image-viewer-modal";
import { EntrepreneurFundedEvents } from "@/components/entrepreneur-funded-events";
import { EntrepreneurInstitutionMemberships } from "@/components/entrepreneur-institution-memberships";
import { showStaffAlert } from "@/components/staff-panel-ui";
import { AppButton, CheckOption, FormField } from "@/components/ui";
import { colors } from "@/constants/theme";
import { useApp } from "@/context/app-context";
import { loadOwnPrivateProfile, saveOwnPixKey } from "@/services/cloud-data";
import {
  getPublicMediaUrl,
  prepareImageForUpload,
  uploadImage,
} from "@/services/media-upload";
import { createClientMessageId, createSupportRequest } from "@/security/trq-bec/service";
import { profileSharePath, shareLiberRotasItem } from "@/utils/share";

/**
 * Perfil editável para os dois papéis do aplicativo.
 *
 * Os dados públicos são inicializados pelo AppProvider. A chave Pix usa um
 * documento privado separado e vinculado ao UID autenticado. Somente o botão
 * Salvar persiste as alterações. O botão Sair encerra a sessão atual.
 */
const interestOptions = ["Artesanato", "Gastronomia", "Guias locais"];

type PrivatePixState = {
  profileId: string;
  pixKey: string;
  error: string;
};

export default function ProfileScreen() {
  const { accessSession, deleteAccount, hasPermission, logout, profile, updateProfile } = useApp();
  const canManageProfile = hasPermission("profile.manage");
  const isEntrepreneur = accessSession?.role === "entrepreneur";
  const canManagePrivatePix = isEntrepreneur && canManageProfile;
  const [name, setName] = useState(profile.name);
  const [email, setEmail] = useState(profile.email);
  const [city, setCity] = useState(profile.city);
  const [address, setAddress] = useState(profile.address || "");
  const [privatePixState, setPrivatePixState] = useState<PrivatePixState | null>(null);
  const [category, setCategory] = useState(profile.category);
  const [interests, setInterests] = useState(profile.interests);
  const [avatarUri, setAvatarUri] = useState(profile.avatarUri);
  const [pendingAvatarAsset, setPendingAvatarAsset] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [isAvatarViewerVisible, setIsAvatarViewerVisible] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleteModalVisible, setIsDeleteModalVisible] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [isSupportModalVisible, setIsSupportModalVisible] = useState(false);
  const [supportSubject, setSupportSubject] = useState("");
  const [supportMessage, setSupportMessage] = useState("");
  const [supportError, setSupportError] = useState("");
  const [supportConversationId, setSupportConversationId] = useState("");
  const [isSendingSupport, setIsSendingSupport] = useState(false);
  const supportClientMessageIdRef = useRef("");
  const currentPrivatePixState = privatePixState?.profileId === profile.id ? privatePixState : null;
  const pixKey = currentPrivatePixState?.pixKey || "";
  const pixLoadError = currentPrivatePixState?.error || "";
  const isPixLoading = canManagePrivatePix && currentPrivatePixState === null;
  const canDeleteAccount = deleteConfirmation.trim() === "EXCLUIR CONTA" && deletePassword.length >= 6 && !isDeleting;

  useEffect(() => {
    let isActive = true;
    if (!canManagePrivatePix) return undefined;

    loadOwnPrivateProfile()
      .then((privateProfile) => {
        if (isActive) {
          setPrivatePixState({ profileId: profile.id, pixKey: privateProfile.pixKey, error: "" });
        }
      })
      .catch((error) => {
        console.warn("Não foi possível carregar a chave Pix privada.", error);
        if (isActive) {
          setPrivatePixState({
            profileId: profile.id,
            pixKey: "",
            error: "Não foi possível carregar sua chave Pix. Reabra o perfil e tente novamente.",
          });
        }
      });

    return () => {
      isActive = false;
    };
  }, [canManagePrivatePix, profile.id]);

  // Inclusão/remoção imutável das caixas de seleção de interesse.
  function toggleInterest(item: string) {
    setInterests((current) => (current.includes(item) ? current.filter((value) => value !== item) : [...current, item]));
  }

  async function chooseAvatar(source: "camera" | "library") {
    const permission =
      source === "camera"
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();

    if (Platform.OS !== "web" && !permission.granted) {
      showStaffAlert(
        "Permissão necessária",
        source === "camera" ? "Permita o acesso à câmera para trocar sua foto." : "Permita o acesso à galeria para escolher sua foto.",
      );
      return;
    }

    const result =
      source === "camera"
        ? await ImagePicker.launchCameraAsync({ allowsEditing: true, aspect: [1, 1], mediaTypes: ["images"], quality: 0.85 })
        : await ImagePicker.launchImageLibraryAsync({ allowsEditing: true, aspect: [1, 1], mediaTypes: ["images"], quality: 0.85 });

    if (result.canceled) return;
    try {
      setPendingAvatarAsset(result.assets[0]);
      setAvatarUri(result.assets[0].uri);
    } catch (error) {
      console.warn("Não foi possível salvar a foto de perfil.", error);
      showStaffAlert("Falha ao salvar foto", "Não foi possível copiar a imagem para o dispositivo.");
    }
  }

  // updateProfile centraliza a escrita no AsyncStorage dentro do contexto.
  async function saveProfile() {
    if (!canManageProfile) {
      showStaffAlert("Acesso não autorizado", "O backend não liberou a edição deste perfil.");
      return;
    }
    setSaveError("");
    setIsSaving(true);
    try {
      if (canManagePrivatePix) await saveOwnPixKey(pixKey);
      let nextAvatarUri = avatarUri;

      if (pendingAvatarAsset) {
        const preparedAvatar = await prepareImageForUpload(pendingAvatarAsset);
        const uploadedAvatar = await uploadImage(preparedAvatar, {
          entityType: "user",
          entityId: profile.id,
          mediaRole: "avatar",
        });
        if (uploadedAvatar.status !== "ready") {
          throw new Error("O backend ainda nao concluiu o processamento da foto. Tente novamente.");
        }
        nextAvatarUri = getPublicMediaUrl(uploadedAvatar.media_id);

        // Um novo clique em Salvar reaproveita a imagem pronta se a atualizacao
        // do perfil falhar depois do upload.
        setPendingAvatarAsset(null);
        setAvatarUri(nextAvatarUri);
      }
      await updateProfile({
        id: profile.id,
        role: accessSession?.role === "entrepreneur" ? "entrepreneur" : "visitor",
        name,
        email,
        city,
        address: isEntrepreneur ? address : undefined,
        category: isEntrepreneur ? category : "Visitante LiberRotas",
        interests,
        avatarUri: nextAvatarUri,
        createdAtMs: profile.createdAtMs,
      });
      showStaffAlert("Perfil salvo", "Seus dados públicos e privados foram atualizados.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Não foi possível atualizar o perfil.";
      setSaveError(message);
      showStaffAlert("Revise o perfil", message);
    } finally {
      setIsSaving(false);
    }
  }

  // replace limpa a pilha para que a área protegida não reapareça ao voltar.
  async function handleLogout() {
    await logout();
    router.replace("/");
  }

  function openDeleteConfirmation() {
    setDeleteConfirmation("");
    setDeletePassword("");
    setDeleteError("");
    setIsDeleteModalVisible(true);
  }

  function closeDeleteConfirmation() {
    if (isDeleting) return;
    setIsDeleteModalVisible(false);
    setDeleteConfirmation("");
    setDeletePassword("");
    setDeleteError("");
  }

  async function handleDeleteAccount() {
    if (!canDeleteAccount) return;
    setDeleteError("");
    setIsDeleting(true);
    try {
      await deleteAccount(deletePassword);
      setIsDeleteModalVisible(false);
      router.replace("/");
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : "Não foi possível excluir a conta.");
    } finally {
      setIsDeleting(false);
    }
  }

  function openSupportContact() {
    supportClientMessageIdRef.current = createClientMessageId("support");
    setSupportSubject("");
    setSupportMessage("");
    setSupportError("");
    setSupportConversationId("");
    setIsSupportModalVisible(true);
  }

  function closeSupportContact() {
    if (isSendingSupport) return;
    setIsSupportModalVisible(false);
  }

  async function sendSupportRequest() {
    if (isSendingSupport) return;
    if (!supportClientMessageIdRef.current) {
      setSupportError("Reabra o formulário de suporte e tente novamente.");
      return;
    }
    setSupportError("");
    setIsSendingSupport(true);
    try {
      const result = await createSupportRequest({
        clientMessageId: supportClientMessageIdRef.current,
        subject: supportSubject,
        content: supportMessage,
      });
      setSupportConversationId(result.request.request_id);
      setSupportMessage("");
    } catch (error) {
      setSupportError(error instanceof Error ? error.message : "Não foi possível enviar o atendimento.");
    } finally {
      setIsSendingSupport(false);
    }
  }

  function openSupportConversation() {
    if (!supportConversationId) return;
    setIsSupportModalVisible(false);
    router.push(`/messages/${encodeURIComponent(supportConversationId)}` as Href);
  }

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <BrandHeader
        subtitle={isEntrepreneur ? "vitrine do empreendimento" : "preferências pessoais"}
        title={isEntrepreneur ? "Perfil empreendedor" : "Meu perfil"}
      />
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.flex}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={[styles.cover, !isEntrepreneur && styles.visitorCover]}>
            <Text style={styles.coverEyebrow}>{isEntrepreneur ? "VITRINE LOCAL" : "EXPLORADOR LIBERROTAS"}</Text>
            <Text adjustsFontSizeToFit minimumFontScale={0.85} numberOfLines={1} style={styles.coverText}>
              {isEntrepreneur ? "Sua vitrine local" : "Descubra o turismo local"}
            </Text>
            <Pressable
              accessibilityHint="Abre a foto em tamanho maior com controles de zoom"
              accessibilityLabel="Ampliar minha foto de perfil"
              accessibilityRole="imagebutton"
              disabled={!avatarUri}
              onPress={() => setIsAvatarViewerVisible(true)}
              style={[styles.avatar, !isEntrepreneur && styles.visitorAvatar]}
            >
              {avatarUri ? (
                <Image contentFit="cover" source={{ uri: avatarUri }} style={styles.avatarImage} />
              ) : (
                <Text style={[styles.avatarText, !isEntrepreneur && styles.visitorAvatarText]}>
                  {name.slice(0, 2).toUpperCase() || "FT"}
                </Text>
              )}
            </Pressable>
          </View>
          <View style={styles.profileIntro}>
            <Text style={styles.activeLabel}>{isEntrepreneur ? "CONTA EMPREENDEDOR" : "CONTA VISITANTE"}</Text>
            <Text style={styles.name}>{name || "Seu nome"}</Text>
            <Text style={styles.description}>
              {isEntrepreneur ? `Empreendimento: ${category || "Categoria local"}` : `Visitante de ${city || "sua cidade"}`}
            </Text>
          </View>
          <View style={styles.photoActions}>
            <Pressable onPress={() => chooseAvatar("camera")} style={styles.photoButton}>
              <Ionicons color={colors.primary} name="camera-outline" size={18} />
              <Text style={styles.photoButtonText}>Tirar foto</Text>
            </Pressable>
            <Pressable onPress={() => chooseAvatar("library")} style={styles.photoButton}>
              <Ionicons color={colors.primary} name="image-outline" size={18} />
              <Text style={styles.photoButtonText}>Escolher foto</Text>
            </Pressable>
            <Pressable
              accessibilityLabel="Abrir minha Vitrine"
              onPress={() => router.push(`/profile/${encodeURIComponent(profile.id)}` as Href)}
              style={[styles.photoButton, styles.showcaseButton]}
            >
              <Ionicons color={colors.surface} name="storefront-outline" size={18} />
              <Text style={[styles.photoButtonText, styles.showcaseButtonText]}>Vitrine</Text>
            </Pressable>
          </View>
          <View style={styles.roleCard}>
            <Text style={styles.roleCardTitle}>
              {isEntrepreneur ? "Recursos do empreendedor" : "Sua experiência LiberRotas"}
            </Text>
            <Text style={styles.roleCardText}>
              {isEntrepreneur
                ? "Divulgue sua atividade, acompanhe cupons e mantenha os dados públicos da sua vitrine atualizados."
                : "Salve feiras, organize seus interesses e encontre benefícios oferecidos pelos empreendedores locais."}
            </Text>
            <Pressable accessibilityRole="button" onPress={openSupportContact} style={styles.supportButton}>
              <Ionicons color={colors.surface} name="help-buoy-outline" size={19} />
              <View style={styles.supportButtonTextGroup}>
                <Text style={styles.supportButtonTitle}>Entrar em contato com o SUPORTE</Text>
                <Text style={styles.supportButtonSubtitle}>Abra um atendimento privado com a equipe LiberRotas</Text>
              </View>
              <Ionicons color={colors.surface} name="chevron-forward" size={18} />
            </Pressable>
            <Pressable
              accessibilityLabel={`Compartilhar perfil ${profile.name}`}
              accessibilityRole="button"
              onPress={() => void shareLiberRotasItem({
                kind: "profile",
                title: profile.name,
                description: `${profile.category} · ${profile.city}`,
                path: profileSharePath(profile.id),
              })}
              style={styles.shareProfileButton}
            >
              <Ionicons color={colors.primary} name="share-social-outline" size={19} />
              <Text style={styles.shareProfileButtonText}>Compartilhar perfil</Text>
            </Pressable>
            <Pressable
              accessibilityHint="Mostra os aparelhos conectados e as opções de senha"
              accessibilityLabel="Segurança da minha conta"
              accessibilityRole="button"
              onPress={() => router.push("/account/devices" as Href)}
              style={styles.accountSecurityButton}
            >
              <Ionicons color={colors.primary} name="shield-checkmark-outline" size={19} />
              <Text style={styles.accountSecurityButtonText}>Segurança da minha conta</Text>
              <Ionicons color={colors.primary} name="chevron-forward-outline" size={18} />
            </Pressable>
          </View>
          {isEntrepreneur ? <EntrepreneurInstitutionMemberships /> : null}
          {isEntrepreneur ? <EntrepreneurFundedEvents /> : null}
          <View style={styles.form}>
            <FormField label="Nome público único" onChangeText={setName} value={name} />
            <Text style={styles.addressHint}>
              Este nome identifica seu perfil na pesquisa. Não pode ser igual ao nome público de outra conta.
            </Text>
            <FormField autoCapitalize="none" keyboardType="email-address" label="E-mail" onChangeText={setEmail} value={email} />
            <FormField label="Cidade" onChangeText={setCity} value={city} />
            {isEntrepreneur ? (
              <>
                <FormField
                  autoComplete="street-address"
                  label="Endereço completo do empreendimento (opcional)"
                  maxLength={240}
                  multiline
                  numberOfLines={2}
                  onChangeText={setAddress}
                  placeholder="Rua, número, bairro, cidade - UF"
                  style={styles.addressField}
                  textAlignVertical="top"
                  value={address}
                />
                <Text style={styles.addressHint}>
                  Este endereço ficará visível no perfil. Informe somente o local que você deseja divulgar publicamente.
                </Text>
                <FormField
                  autoCapitalize="none"
                  autoCorrect={false}
                  editable={!isPixLoading && !pixLoadError}
                  label="Chave Pix (opcional e privada)"
                  maxLength={140}
                  onChangeText={(value) => setPrivatePixState({ profileId: profile.id, pixKey: value, error: "" })}
                  placeholder={isPixLoading ? "Carregando chave Pix..." : "CPF, CNPJ, e-mail, telefone ou chave aleatória"}
                  value={pixKey}
                />
                <Text style={styles.addressHint}>
                  Outros usuários do app não podem consultar esta chave. Ela não aparece no perfil público, no Feed ou para visitantes.
                </Text>
                {pixLoadError ? <Text style={styles.error}>{pixLoadError}</Text> : null}
                <FormField label="Categoria do empreendimento" onChangeText={setCategory} value={category} />
              </>
            ) : null}
            <Text style={styles.sectionLabel}>{isEntrepreneur ? "Áreas de atuação" : "Meus interesses"}</Text>
            <View style={styles.options}>
              {/* Cada opção recebe selected a partir do array local. */}
              {interestOptions.map((item) => (
                <CheckOption key={item} label={item} onPress={() => toggleInterest(item)} selected={interests.includes(item)} />
              ))}
            </View>
            {saveError ? <Text style={styles.error}>{saveError}</Text> : null}
            <AppButton disabled={isSaving || isDeleting} onPress={openDeleteConfirmation} variant="danger">
              EXCLUIR CONTA
            </AppButton>
            <AppButton
              disabled={!canManageProfile || isSaving || isPixLoading || Boolean(pixLoadError)}
              onPress={saveProfile}
              style={styles.saveProfileButton}
            >
              {isSaving ? "Salvando..." : "Salvar perfil"}
            </AppButton>
            <AppButton onPress={handleLogout}>SAIR</AppButton>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
      <Modal
        animationType="fade"
        onRequestClose={closeDeleteConfirmation}
        statusBarTranslucent
        transparent
        visible={isDeleteModalVisible}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : undefined}
          style={styles.modalBackdrop}
        >
          <View accessibilityViewIsModal style={styles.modalCard}>
            <View style={styles.modalIcon}>
              <Ionicons color={colors.surface} name="trash-outline" size={26} />
            </View>
            <Text style={styles.modalTitle}>EXCLUIR CONTA</Text>
            <Text style={styles.modalWarning}>
              Esta ação é permanente. Seu perfil, chave Pix privada, publicações, pontos e feiras serão removidos.
              {isEntrepreneur ? " Produtos, ofertas e cupons ativos serão encerrados." : ""}
            </Text>
            <Text style={styles.modalRetention}>
              Registros técnicos de segurança e transações já concluídas podem ser preservados para integridade e prevenção de fraude.
            </Text>
            <FormField
              autoCapitalize="characters"
              autoCorrect={false}
              editable={!isDeleting}
              label="Digite EXCLUIR CONTA para confirmar"
              maxLength={13}
              onChangeText={setDeleteConfirmation}
              value={deleteConfirmation}
            />
            <FormField
              autoCapitalize="none"
              autoCorrect={false}
              editable={!isDeleting}
              label="Senha atual"
              onChangeText={setDeletePassword}
              secureTextEntry
              value={deletePassword}
            />
            {deleteError ? <Text style={styles.modalError}>{deleteError}</Text> : null}
            <View style={styles.modalActions}>
              <AppButton
                disabled={isDeleting}
                onPress={closeDeleteConfirmation}
                style={styles.modalActionButton}
                variant="secondary"
              >
                Cancelar
              </AppButton>
              <AppButton
                disabled={!canDeleteAccount}
                onPress={handleDeleteAccount}
                style={styles.modalActionButton}
                variant="danger"
              >
                {isDeleting ? "Excluindo..." : "EXCLUIR CONTA"}
              </AppButton>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
      <Modal
        animationType="fade"
        onRequestClose={closeSupportContact}
        statusBarTranslucent
        transparent
        visible={isSupportModalVisible}
      >
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.modalBackdrop}>
          <View accessibilityViewIsModal style={styles.modalCard}>
            <View style={[styles.modalIcon, styles.supportModalIcon]}>
              <Ionicons color={colors.surface} name="headset-outline" size={26} />
            </View>
            <Text style={[styles.modalTitle, styles.supportModalTitle]}>Entrar em contato com o SUPORTE</Text>
            {supportConversationId ? (
              <>
                <Text style={styles.supportSuccess}>
                  Seu atendimento foi enviado. Somente você e a equipe autorizada de suporte podem acompanhar esta conversa.
                </Text>
                <View style={styles.modalActions}>
                  <AppButton onPress={closeSupportContact} style={styles.modalActionButton} variant="secondary">
                    Fechar
                  </AppButton>
                  <AppButton onPress={openSupportConversation} style={styles.modalActionButton}>
                    Abrir conversa
                  </AppButton>
                </View>
              </>
            ) : (
              <>
                <Text style={styles.modalWarning}>
                  Explique o problema sem informar senha, chave Pix, código de autenticação ou outros dados sigilosos.
                </Text>
                <FormField
                  editable={!isSendingSupport}
                  label="Assunto"
                  maxLength={120}
                  onChangeText={setSupportSubject}
                  placeholder="Ex.: dificuldade para publicar produto"
                  value={supportSubject}
                />
                <FormField
                  editable={!isSendingSupport}
                  label="Mensagem"
                  maxLength={2_000}
                  multiline
                  numberOfLines={5}
                  onChangeText={setSupportMessage}
                  placeholder="Descreva o que aconteceu e o que você já tentou."
                  style={styles.supportMessageField}
                  textAlignVertical="top"
                  value={supportMessage}
                />
                <Text style={styles.supportCounter}>{supportMessage.length}/2000</Text>
                {supportError ? <Text style={styles.modalError}>{supportError}</Text> : null}
                <View style={styles.modalActions}>
                  <AppButton disabled={isSendingSupport} onPress={closeSupportContact} style={styles.modalActionButton} variant="secondary">
                    Cancelar
                  </AppButton>
                  <AppButton
                    disabled={isSendingSupport || supportSubject.trim().length < 3 || !supportMessage.trim()}
                    onPress={sendSupportRequest}
                    style={styles.modalActionButton}
                  >
                    {isSendingSupport ? "Enviando..." : "Enviar"}
                  </AppButton>
                </View>
              </>
            )}
          </View>
        </KeyboardAvoidingView>
      </Modal>
      <ImageViewerModal
        accessibilityLabel={`Foto de perfil de ${name || "usuário"}`}
        onClose={() => setIsAvatarViewerVisible(false)}
        uri={avatarUri}
        visible={isAvatarViewerVisible}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.cream, flex: 1 },
  flex: { backgroundColor: colors.background, flex: 1 },
  content: { paddingBottom: 36 },
  cover: {
    alignItems: "center",
    backgroundColor: colors.accentSoft,
    height: 176,
    justifyContent: "flex-start",
    paddingHorizontal: 24,
    paddingTop: 38,
    position: "relative",
  },
  visitorCover: { backgroundColor: colors.primary },
  coverEyebrow: { color: colors.surface, fontSize: 11, fontWeight: "800", letterSpacing: 1.4 },
  coverText: { color: colors.surface, fontSize: 25, fontWeight: "900", marginTop: 8, maxWidth: 330, textAlign: "center" },
  avatar: { alignItems: "center", backgroundColor: "#FFD5B8", borderColor: colors.surface, borderRadius: 58, borderWidth: 8, bottom: -58, height: 116, justifyContent: "center", overflow: "hidden", position: "absolute", width: 116 },
  avatarImage: { height: "100%", width: "100%" },
  visitorAvatar: { backgroundColor: colors.cream },
  avatarText: { color: colors.accent, fontSize: 24, fontWeight: "900" },
  visitorAvatarText: { color: colors.primary },
  profileIntro: { paddingHorizontal: 24, paddingTop: 72 },
  activeLabel: { color: colors.accent, fontSize: 11, fontWeight: "800" },
  name: { color: colors.primaryDark, fontSize: 28, fontWeight: "900" },
  description: { color: colors.textMuted, fontSize: 14, marginTop: 3 },
  photoActions: { flexDirection: "row", gap: 10, paddingHorizontal: 24, paddingTop: 14 },
  photoButton: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 999, borderWidth: 1, flex: 1, flexDirection: "row", gap: 6, justifyContent: "center", minHeight: 42 },
  photoButtonText: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  showcaseButton: { backgroundColor: colors.primary, borderColor: colors.primary },
  showcaseButtonText: { color: colors.surface },
  roleCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, marginHorizontal: 24, marginTop: 18, padding: 16 },
  roleCardTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "800" },
  roleCardText: { color: colors.textMuted, fontSize: 12, lineHeight: 17, marginTop: 6 },
  supportButton: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 14, flexDirection: "row", gap: 10, marginTop: 14, minHeight: 58, paddingHorizontal: 14, paddingVertical: 10 },
  supportButtonTextGroup: { flex: 1 },
  supportButtonTitle: { color: colors.surface, fontSize: 13, fontWeight: "900" },
  supportButtonSubtitle: { color: colors.surface, fontSize: 10, lineHeight: 14, marginTop: 2, opacity: 0.8 },
  shareProfileButton: { alignItems: "center", backgroundColor: colors.background, borderColor: colors.primary, borderRadius: 14, borderWidth: 1, flexDirection: "row", gap: 8, justifyContent: "center", marginTop: 10, minHeight: 46, paddingHorizontal: 14 },
  shareProfileButtonText: { color: colors.primary, fontSize: 12, fontWeight: "900" },
  accountSecurityButton: { alignItems: "center", backgroundColor: colors.background, borderColor: colors.primary, borderRadius: 14, borderWidth: 1, flexDirection: "row", gap: 8, justifyContent: "center", marginTop: 10, minHeight: 46, paddingHorizontal: 14 },
  accountSecurityButtonText: { color: colors.primary, flex: 1, fontSize: 12, fontWeight: "900", textAlign: "center" },
  form: { gap: 12, padding: 24 },
  addressField: { minHeight: 72, paddingTop: 14 },
  addressHint: { color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: -6 },
  error: { color: colors.danger, fontSize: 12 },
  sectionLabel: { color: colors.primaryDark, fontSize: 14, fontWeight: "800", marginTop: 4 },
  options: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 6 },
  saveProfileButton: { backgroundColor: colors.success },
  modalBackdrop: {
    alignItems: "center",
    backgroundColor: "rgba(0, 20, 50, 0.72)",
    flex: 1,
    justifyContent: "center",
    padding: 20,
  },
  modalCard: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: 22,
    borderWidth: 1,
    gap: 12,
    maxWidth: 520,
    padding: 22,
    width: "100%",
  },
  modalIcon: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: colors.danger,
    borderRadius: 28,
    height: 56,
    justifyContent: "center",
    width: 56,
  },
  modalTitle: { color: colors.danger, fontSize: 22, fontWeight: "900", textAlign: "center" },
  modalWarning: { color: colors.text, fontSize: 14, lineHeight: 20, textAlign: "center" },
  modalRetention: { color: colors.textMuted, fontSize: 11, lineHeight: 16, textAlign: "center" },
  modalError: { color: colors.danger, fontSize: 12, lineHeight: 17, textAlign: "center" },
  modalActions: { flexDirection: "row", gap: 10, marginTop: 2 },
  modalActionButton: { flex: 1, minHeight: 48 },
  supportModalIcon: { backgroundColor: colors.primary },
  supportModalTitle: { color: colors.primaryDark },
  supportMessageField: { minHeight: 118, paddingTop: 14 },
  supportCounter: { color: colors.textMuted, fontSize: 10, marginTop: -8, textAlign: "right" },
  supportSuccess: { color: colors.success, fontSize: 13, fontWeight: "700", lineHeight: 19, textAlign: "center" },
});
