import { Redirect, router, type Href } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { BrandHeader } from "@/components/brand-header";
import { AccountTypeSelector, AppButton, CheckOption, FormField, LoadingScreen } from "@/components/ui";
import { colors } from "@/constants/theme";
import { AccountType, useApp } from "@/context/app-context";

/**
 * Tela de cadastro e coleta de dados do usuário.
 *
 * Os states guardam temporariamente cada campo e o array de interesses. Ao
 * concluir, os dados formam um UserProfile e são enviados ao AppProvider, que
 * cria o usuário no Firebase Authentication. O uid gerado pelo Firebase passa
 * a ser o id oficial do perfil no app e no Firestore.
 */
const interestOptions = ["Artesanato", "Gastronomia", "Guias locais"];

export default function RegisterScreen() {
  const { accessDestination, hasFirebaseSession, isHydrated, isResolvingAccess, register } = useApp();
  const insets = useSafeAreaInsets();
  const [accountType, setAccountType] = useState<AccountType>("visitor");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [city, setCity] = useState("");
  const [address, setAddress] = useState("");
  const [category, setCategory] = useState("");
  const [password, setPassword] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [error, setError] = useState("");

  if (!isHydrated || isResolvingAccess) return <LoadingScreen />;
  if (hasFirebaseSession) return <Redirect href={accessDestination as Href} />;

  // Atualização funcional usa o valor mais recente do array de interesses.
  function toggleInterest(item: string) {
    setInterests((current) => (current.includes(item) ? current.filter((value) => value !== item) : [...current, item]));
  }

  // Validação mínima evita salvar um perfil incompleto no dispositivo.
  async function handleRegister() {
    const entrepreneurWithoutCategory = accountType === "entrepreneur" && !category.trim();
    if (!name.trim() || !email.includes("@") || !city.trim() || entrepreneurWithoutCategory) {
      setError(
        accountType === "entrepreneur"
          ? "Preencha nome, e-mail, cidade e categoria do empreendimento."
          : "Preencha nome, e-mail e cidade.",
      );
      return;
    }
    try {
      const destination = await register(
        {
          id: "",
          role: accountType,
          name,
          email,
          city,
          address: accountType === "entrepreneur" ? address : undefined,
          category: accountType === "entrepreneur" ? category : "Visitante LiberRotas",
          interests,
        },
        password,
      );
      router.replace(destination as Href);
    } catch (registrationError) {
      setError(registrationError instanceof Error ? registrationError.message : "Não foi possível criar a conta.");
    }
  }

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <BrandHeader subtitle="escolha seu tipo de perfil" title="Criar conta" />
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.flex}>
        <ScrollView
          contentContainerStyle={[styles.content, { paddingBottom: Math.max(42, insets.bottom + 24) }]}
          keyboardDismissMode={Platform.OS === "ios" ? "interactive" : "on-drag"}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
          style={styles.scroll}
        >
          <Text style={styles.heading}>{accountType === "entrepreneur" ? "Cadastre sua vitrine" : "Conte sobre você"}</Text>
          <Text style={styles.lead}>
            {accountType === "entrepreneur"
              ? "Apresente seu empreendimento para visitantes e parceiros locais."
              : "Personalize sua experiência e encontre atividades do seu interesse."}
          </Text>
          <View style={styles.form}>
            <Text style={styles.sectionLabel}>Tipo de perfil</Text>
            <AccountTypeSelector onChange={setAccountType} value={accountType} />
            <FormField
              label="Nome público único"
              onChangeText={setName}
              placeholder="Nome usado na pesquisa"
              value={name}
            />
            <Text style={styles.addressHint}>
              Escolha um nome que ainda não esteja em uso. Maiúsculas, acentos e espaços não criam nomes diferentes.
            </Text>
            <FormField
              autoCapitalize="none"
              keyboardType="email-address"
              label="E-mail"
              onChangeText={setEmail}
              placeholder="voce@email.com"
              value={email}
            />
            <FormField label="Cidade" onChangeText={setCity} placeholder="Curitiba - PR" value={city} />
            {accountType === "entrepreneur" ? (
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
                  Informe somente um endereço que você deseja tornar público. Não use seu endereço residencial se não quiser divulgá-lo.
                </Text>
                <FormField
                  label="Categoria do empreendimento"
                  onChangeText={setCategory}
                  placeholder="Turismo comunitário"
                  value={category}
                />
              </>
            ) : null}
            <Text style={styles.sectionLabel}>
              {accountType === "entrepreneur" ? "Áreas de atuação" : "Interesses"}
            </Text>
            <View style={styles.options}>
              {/* map transforma cada opção do array em um componente selecionável. */}
              {interestOptions.map((item) => (
                <CheckOption key={item} label={item} onPress={() => toggleInterest(item)} selected={interests.includes(item)} />
              ))}
            </View>
            <FormField label="Senha" onChangeText={setPassword} placeholder="Mínimo de 6 caracteres" secureTextEntry value={password} />
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <AppButton onPress={handleRegister}>Concluir cadastro</AppButton>
            <AppButton onPress={() => router.back()} variant="secondary">Voltar</AppButton>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.cream, flex: 1 },
  flex: { backgroundColor: colors.background, flex: 1 },
  scroll: { flex: 1 },
  content: { flexGrow: 1, padding: 24 },
  heading: { color: colors.primaryDark, fontSize: 28, fontWeight: "900" },
  lead: { color: colors.textMuted, fontSize: 14, lineHeight: 20, marginTop: 6 },
  form: { gap: 12, marginTop: 20 },
  sectionLabel: { color: colors.primaryDark, fontSize: 14, fontWeight: "800", marginTop: 4 },
  options: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  addressField: { minHeight: 72, paddingTop: 14 },
  addressHint: { color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: -6 },
  error: { color: colors.danger, fontSize: 12 },
});
