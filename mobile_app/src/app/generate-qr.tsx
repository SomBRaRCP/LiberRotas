import { Ionicons } from "@expo/vector-icons";
import { Redirect, router, type Href } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { LocalClock } from "@/components/local-clock";
import { MediaImagePicker } from "@/components/media-image-picker";
import { PaginationControls } from "@/components/pagination-controls";
import { PublicEntityMediaImage } from "@/components/public-entity-media-image";
import { SaleQrModal } from "@/components/sale-qr-modal";
import { showStaffAlert } from "@/components/staff-panel-ui";
import { AppButton, FormField, LoadingScreen } from "@/components/ui";
import { colors, radius, shadow } from "@/constants/theme";
import { useProfileState, useSessionState } from "@/context/app-context";
import { useTrustedClock } from "@/context/trusted-clock-context";
import type {
  CouponQrResult,
  LiveOfferBatchUpdateInput,
  MarketplaceProduct,
  OfferDiscountType,
  OfferPreview,
} from "@/security/trq-bec/contracts";
import {
  batchActivateMarketplaceProducts,
  batchArchiveMarketplaceProducts,
  batchUpdateLiveOffers,
  createClientMessageId,
  createMarketplaceProduct,
  getTrqBecApiUrl,
  getOwnLiveOfferQr,
  issueLiveOffer,
  listOwnLiveOffers,
  listOwnMarketplaceProducts,
  TrqBecServiceError,
  updateLiveOfferStatus,
  updateMarketplaceProductStock,
} from "@/security/trq-bec/service";
import { profileSharePath, shareLiberRotasItem } from "@/utils/share";
import { getAuthenticatedHomeDestination } from "@/utils/account-navigation";
import { formatRemainingTime, hasTimeEnded } from "@/utils/time";
import { uploadImage, type PreparedImageUpload } from "@/services/media-upload";
import { clampPage, HISTORY_PAGE_SIZE, paginateItems } from "@/utils/pagination";

type MarketplaceModalState =
  | { kind: "ACTIVATE_PRODUCTS" }
  | { kind: "ARCHIVE_PRODUCTS" }
  | { kind: "CANCEL_OFFERS" }
  | { kind: "CLOSE_SINGLE_OFFER"; offer: OfferPreview }
  | { kind: "INCREASE_DISCOUNT"; discountType: OfferDiscountType }
  | { kind: "EXTEND_VALIDITY" }
  | null;

type OfferDraft = {
  discountType: OfferDiscountType;
  discountValue: string;
  maximumRedemptions: string;
  validityHours: string;
};

const DEFAULT_OFFER_VALIDITY_HOURS = "8";
const MAX_OFFER_VALIDITY_HOURS = 8;
const MAX_OFFER_PRODUCTS_PER_ISSUE = 25;

function formatMoney(valueMinor: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(valueMinor / 100);
}

function formatProductStatus(status: MarketplaceProduct["status"]) {
  if (status === "ACTIVE") return "Ativo";
  if (status === "PAUSED") return "Pausado";
  return "Arquivado";
}

function parseMoneyToMinor(value: string) {
  const compact = value.trim().replace(/\s/g, "");
  const normalized = compact.includes(",") ? compact.replace(/\./g, "").replace(",", ".") : compact;
  const amount = Number(normalized);
  return Number.isFinite(amount) ? Math.round(amount * 100) : 0;
}

function errorMessage(error: unknown) {
  if (error instanceof TrqBecServiceError) return error.userMessage;
  if (error instanceof Error && error.message) return error.message;
  return "Ocorreu um erro ao conversar com o TRQ-BEC.";
}

function defaultOfferDraft(product: MarketplaceProduct): OfferDraft {
  return {
    discountType: "PERCENT",
    discountValue: "20",
    maximumRedemptions: String(product.stock_quantity),
    validityHours: DEFAULT_OFFER_VALIDITY_HOURS,
  };
}

/**
 * Gestão comercial mínima da Fase 1.
 *
 * Produto, preço, estoque, desconto e disponibilidade vêm do backend. O app
 * apenas envia comandos e exibe o QR retornado pelo backend para cada venda.
 */
export default function GenerateQrScreen() {
  const {
    accessDestination,
    accessSession,
    deviceApprovalRequired,
    hasFirebaseSession,
    hasPermission,
    isAuthenticated,
    isHydrated,
    isResolvingAccess,
    logout,
  } = useSessionState();
  const { profile } = useProfileState();
  const { nowMs } = useTrustedClock();
  const canManageMarketplace = accessSession?.role === "entrepreneur"
    && !deviceApprovalRequired
    && hasPermission("marketplace.manage");
  const [products, setProducts] = useState<MarketplaceProduct[]>([]);
  const [offers, setOffers] = useState<OfferPreview[]>([]);
  const [qrQuantityTexts, setQrQuantityTexts] = useState<Record<string, string>>({});
  const [qrResult, setQrResult] = useState<CouponQrResult | null>(null);
  const [generatingQrOfferId, setGeneratingQrOfferId] = useState("");
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [selectedOfferProductIds, setSelectedOfferProductIds] = useState<string[]>([]);
  const [offerDrafts, setOfferDrafts] = useState<Record<string, OfferDraft>>({});
  const [selectedOfferIds, setSelectedOfferIds] = useState<string[]>([]);
  const [stockDrafts, setStockDrafts] = useState<Record<string, string>>({});
  const [productTitle, setProductTitle] = useState("");
  const [productDescription, setProductDescription] = useState("");
  const [productPrice, setProductPrice] = useState("");
  const [productStock, setProductStock] = useState("");
  const [newProductImage, setNewProductImage] = useState<PreparedImageUpload | null>(null);
  const [productImageDrafts, setProductImageDrafts] = useState<Record<string, PreparedImageUpload | null>>({});
  const [marketplaceModal, setMarketplaceModal] = useState<MarketplaceModalState>(null);
  const [batchDiscountValue, setBatchDiscountValue] = useState("5");
  const [batchExtensionMinutes, setBatchExtensionMinutes] = useState("60");
  const [productBatchFeedback, setProductBatchFeedback] = useState("");
  const [offerBatchFeedback, setOfferBatchFeedback] = useState("");
  const [offersPage, setOffersPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState<{ message: string; requiresRecentLogin: boolean } | null>(null);
  const marketplaceRequestId = useRef(0);
  const productBatchRequestRef = useRef<{ signature: string; requestId: string } | null>(null);
  const offerBatchRequestRef = useRef<{ signature: string; requestId: string } | null>(null);

  const loadMarketplace = useCallback(async () => {
    if (!isAuthenticated || !canManageMarketplace) return;
    const requestId = ++marketplaceRequestId.current;
    setIsLoading(true);
    setLoadError("");
    const [productsResult, offersResult] = await Promise.allSettled([
      listOwnMarketplaceProducts(),
      listOwnLiveOffers(),
    ]);
    if (requestId !== marketplaceRequestId.current) return;
    const problems: string[] = [];

    if (productsResult.status === "fulfilled") {
      const nextProducts = productsResult.value;
      setProducts(nextProducts);
      setSelectedProductIds((current) => current.filter((productId) => (
        nextProducts.some((product) => product.product_id === productId)
      )));
      setSelectedOfferProductIds((current) => current.filter((productId) => (
        nextProducts.some((product) => (
          product.product_id === productId
          && product.status === "ACTIVE"
          && product.stock_quantity > 0
        ))
      )));
      setStockDrafts(Object.fromEntries(nextProducts.map((product) => [product.product_id, String(product.stock_quantity)])));
    } else {
      problems.push(`Produtos: ${errorMessage(productsResult.reason)}`);
    }

    if (offersResult.status === "fulfilled") {
      const nextOffers = offersResult.value;
      setOffers(nextOffers);
      setSelectedOfferIds((current) => current.filter((offerId) => (
        nextOffers.some((offer) => offer.offer_id === offerId && (offer.status === "ACTIVE" || offer.status === "PAUSED"))
      )));
    } else problems.push(`Ofertas: ${errorMessage(offersResult.reason)}`);

    setLoadError(problems.join("\n"));
    setIsLoading(false);
  }, [canManageMarketplace, isAuthenticated]);

  useEffect(() => {
    const task = setTimeout(() => {
      loadMarketplace();
    }, 0);
    return () => clearTimeout(task);
  }, [loadMarketplace]);

  if (!isHydrated || isResolvingAccess) return <LoadingScreen />;
  if (!hasFirebaseSession) return <Redirect href={"/login" as Href} />;
  if (!isAuthenticated || accessSession?.access_state !== "AUTHORIZED") {
    return <Redirect href={"/access-pending" as Href} />;
  }
  if (accessSession.role !== "entrepreneur") return <Redirect href={accessDestination as Href} />;
  if (deviceApprovalRequired) return <Redirect href={"/account/devices" as Href} />;
  if (!canManageMarketplace) return <Redirect href={"/access-pending" as Href} />;

  const selectedProductsForBatch = products.filter((product) => selectedProductIds.includes(product.product_id));
  const issuableProducts = products.filter((product) => product.status === "ACTIVE" && product.stock_quantity > 0);
  const selectedProductsForOffer = issuableProducts.filter((product) => (
    selectedOfferProductIds.includes(product.product_id)
  ));
  const selectedOffersForBatch = offers.filter((offer) => selectedOfferIds.includes(offer.offer_id));
  const visibleProducts = products.filter((product) => product.status !== "ARCHIVED");
  const safeOffersPage = clampPage(offersPage, offers.length);
  const paginatedOffers = paginateItems(offers, safeOffersPage);

  function toggleProductForOffer(product: MarketplaceProduct) {
    if (selectedOfferProductIds.includes(product.product_id)) {
      setSelectedOfferProductIds((current) => current.filter((productId) => productId !== product.product_id));
      return;
    }
    if (selectedOfferProductIds.length >= MAX_OFFER_PRODUCTS_PER_ISSUE) {
      showStaffAlert("Limite de produtos", `Selecione no máximo ${MAX_OFFER_PRODUCTS_PER_ISSUE} produtos por emissão.`);
      return;
    }
    setOfferDrafts((current) => (
      current[product.product_id]
        ? current
        : { ...current, [product.product_id]: defaultOfferDraft(product) }
    ));
    setSelectedOfferProductIds((current) => [...current, product.product_id]);
    setActionError(null);
  }

  function selectAllProductsForOffer() {
    const nextProducts = issuableProducts.slice(0, MAX_OFFER_PRODUCTS_PER_ISSUE);
    setOfferDrafts((current) => {
      const next = { ...current };
      nextProducts.forEach((product) => {
        next[product.product_id] ??= defaultOfferDraft(product);
      });
      return next;
    });
    setSelectedOfferProductIds(nextProducts.map((product) => product.product_id));
    if (issuableProducts.length > MAX_OFFER_PRODUCTS_PER_ISSUE) {
      showStaffAlert(
        "Seleção limitada",
        `Foram selecionados os primeiros ${MAX_OFFER_PRODUCTS_PER_ISSUE} produtos. Emita essas ofertas e depois selecione os demais.`,
      );
    }
  }

  function updateOfferDraft(product: MarketplaceProduct, update: Partial<OfferDraft>) {
    setOfferDrafts((current) => ({
      ...current,
      [product.product_id]: {
        ...(current[product.product_id] ?? defaultOfferDraft(product)),
        ...update,
      },
    }));
    setActionError(null);
  }

  function toggleProductForBatch(productId: string) {
    if (selectedProductIds.includes(productId)) {
      setSelectedProductIds((current) => current.filter((currentId) => currentId !== productId));
      setProductBatchFeedback("");
      return;
    }
    if (selectedProductIds.length >= 25) {
      setProductBatchFeedback("Selecione no máximo 25 produtos por operação.");
      return;
    }
    setSelectedProductIds((current) => [...current, productId]);
    setProductBatchFeedback("");
  }

  function selectAllProducts() {
    setSelectedProductIds(visibleProducts.slice(0, 25).map((product) => product.product_id));
    setProductBatchFeedback(
      visibleProducts.length > 25
        ? "Foram selecionados os primeiros 25 produtos. Conclua a operação e selecione os demais depois."
        : "",
    );
  }

  function toggleOfferForBatch(offerId: string) {
    if (!selectedOfferIds.includes(offerId) && selectedOfferIds.length >= 25) {
      setOfferBatchFeedback("Selecione no máximo 25 ofertas por operação.");
      return;
    }
    setSelectedOfferIds((current) => (
      current.includes(offerId)
        ? current.filter((currentId) => currentId !== offerId)
        : [...current, offerId]
    ));
    setOfferBatchFeedback("");
  }

  async function createProduct() {
    const priceMinor = parseMoneyToMinor(productPrice);
    const stockQuantity = Number(productStock);
    if (productTitle.trim().length < 2 || priceMinor <= 0 || !Number.isInteger(stockQuantity) || stockQuantity < 0) {
      showStaffAlert("Dados incompletos", "Informe nome, preço maior que zero e estoque inteiro igual ou maior que zero.");
      return;
    }

    setIsSaving(true);
    try {
      const createdProduct = await createMarketplaceProduct({
        title: productTitle.trim(),
        description: productDescription.trim(),
        priceMinor,
        stockQuantity,
      });
      let imageWarning = "";
      if (newProductImage) {
        try {
          await uploadImage(newProductImage, {
            entityType: "product",
            entityId: createdProduct.product_id,
            mediaRole: "product_image",
          });
        } catch (error) {
          imageWarning = ` O produto foi salvo, mas a imagem falhou: ${errorMessage(error)} Use o seletor no cartão do produto para tentar novamente.`;
          setProductImageDrafts((current) => ({ ...current, [createdProduct.product_id]: newProductImage }));
        }
      }
      setProductTitle("");
      setProductDescription("");
      setProductPrice("");
      setProductStock("");
      setNewProductImage(null);
      await loadMarketplace();
      showStaffAlert("Produto cadastrado", `Preço e estoque foram gravados no backend autoritativo.${imageWarning}`);
    } catch (error) {
      showStaffAlert("Produto não cadastrado", errorMessage(error));
    } finally {
      setIsSaving(false);
    }
  }

  async function saveProductImage(product: MarketplaceProduct) {
    const image = productImageDrafts[product.product_id];
    if (!image) return;
    setIsSaving(true);
    try {
      await uploadImage(image, {
        entityType: "product",
        entityId: product.product_id,
        mediaRole: "product_image",
      });
      setProductImageDrafts((current) => ({ ...current, [product.product_id]: null }));
      showStaffAlert("Imagem publicada", "A nova imagem processada já aparece na vitrine do produto.");
    } catch (error) {
      showStaffAlert("Imagem não publicada", errorMessage(error));
    } finally {
      setIsSaving(false);
    }
  }

  async function saveStock(product: MarketplaceProduct) {
    const stockQuantity = Number(stockDrafts[product.product_id]);
    if (!Number.isInteger(stockQuantity) || stockQuantity < 0) {
      showStaffAlert("Estoque inválido", "Use um número inteiro igual ou maior que zero.");
      return;
    }
    setIsSaving(true);
    try {
      await updateMarketplaceProductStock(product.product_id, stockQuantity);
      await loadMarketplace();
    } catch (error) {
      showStaffAlert("Estoque não atualizado", errorMessage(error));
    } finally {
      setIsSaving(false);
    }
  }

  async function issueSelectedOffers() {
    if (selectedProductsForOffer.length === 0) {
      showStaffAlert("Selecione os produtos", "Marque pelo menos um produto com estoque antes de emitir as ofertas.");
      return;
    }

    const preparedOffers = selectedProductsForOffer.map((product) => {
      const draft = offerDrafts[product.product_id] ?? defaultOfferDraft(product);
      const discount = draft.discountType === "FIXED_AMOUNT"
        ? parseMoneyToMinor(draft.discountValue)
        : Number(draft.discountValue);
      return {
        product,
        draft,
        discount,
        maximumRedemptions: Number(draft.maximumRedemptions),
        validityHours: Number(draft.validityHours),
      };
    });
    const invalidOffer = preparedOffers.find(({ product, draft, discount, maximumRedemptions, validityHours }) => (
      !Number.isInteger(discount)
      || discount <= 0
      || (draft.discountType === "PERCENT" && discount > 90)
      || (draft.discountType === "FIXED_AMOUNT" && discount >= product.price_minor)
      || !Number.isInteger(maximumRedemptions)
      || maximumRedemptions < 1
      || maximumRedemptions > product.stock_quantity
      || !Number.isInteger(validityHours)
      || validityHours < 1
      || validityHours > MAX_OFFER_VALIDITY_HOURS
    ));
    if (invalidOffer) {
      showStaffAlert(
        `Revise ${invalidOffer.product.title}`,
        `Use desconto válido, quantidade entre 1 e o estoque registrado (${invalidOffer.product.stock_quantity}) e validade entre 1 e ${MAX_OFFER_VALIDITY_HOURS} horas.`,
      );
      return;
    }

    setIsSaving(true);
    setActionError(null);
    const issuedProductIds: string[] = [];
    const issuedQrs: CouponQrResult[] = [];
    const failures: { product: MarketplaceProduct; error: unknown }[] = [];
    try {
      for (const prepared of preparedOffers) {
        try {
          const issuedQr = await issueLiveOffer({
            productId: prepared.product.product_id,
            discountType: prepared.draft.discountType,
            discountValue: prepared.discount,
            maximumRedemptions: prepared.maximumRedemptions,
            validUntil: new Date(nowMs + prepared.validityHours * 60 * 60_000).toISOString(),
          });
          issuedQrs.push(issuedQr);
          issuedProductIds.push(prepared.product.product_id);
        } catch (error) {
          failures.push({ product: prepared.product, error });
          if (error instanceof TrqBecServiceError && error.code === "RECENT_AUTHENTICATION_REQUIRED") break;
        }
      }

      setSelectedOfferProductIds((current) => current.filter((productId) => !issuedProductIds.includes(productId)));
      await loadMarketplace();
      if (issuedProductIds.length > 0) {
        if (issuedQrs.length === 1 && failures.length === 0) setQrResult(issuedQrs[0]);
        else showStaffAlert(
          issuedProductIds.length === 1 ? "Oferta emitida" : "Ofertas emitidas",
          `${issuedProductIds.length} oferta(s) foram publicadas. Use Gerar QR para venda em Ofertas emitidas.`,
        );
      }
      if (failures.length > 0) {
        const firstFailure = failures[0];
        const message = `${firstFailure.product.title}: ${errorMessage(firstFailure.error)}`;
        setActionError({
          message: failures.length > 1 ? `${message}\nMais ${failures.length - 1} oferta(s) não foram emitidas.` : message,
          requiresRecentLogin: firstFailure.error instanceof TrqBecServiceError
            && firstFailure.error.code === "RECENT_AUTHENTICATION_REQUIRED",
        });
        showStaffAlert(
          issuedProductIds.length > 0 ? "Emissão parcialmente concluída" : "Ofertas não emitidas",
          message,
        );
      }
    } finally {
      setIsSaving(false);
    }
  }

  async function generateSaleQr(offer: OfferPreview) {
    if (isSaving || !canManageMarketplace) return;
    const quantity = Number(qrQuantityTexts[offer.offer_id] ?? "1");
    const maximum = Math.min(offer.remaining_redemptions, 1_000);
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > maximum) {
      showStaffAlert("Revise a quantidade", `Informe entre 1 e ${maximum} unidade(s) para esta venda.`);
      return;
    }
    setIsSaving(true);
    setGeneratingQrOfferId(offer.offer_id);
    setActionError(null);
    try {
      const result = await getOwnLiveOfferQr(offer.offer_id, quantity);
      if (result.offer.status !== "ACTIVE") {
        throw new Error("Reative a oferta antes de gerar o QR para vender.");
      }
      setQrResult(result);
    } catch (error) {
      const message = errorMessage(error);
      setActionError({
        message,
        requiresRecentLogin: error instanceof TrqBecServiceError && error.code === "RECENT_AUTHENTICATION_REQUIRED",
      });
      showStaffAlert("QR não gerado", message);
      await loadMarketplace();
    } finally {
      setGeneratingQrOfferId("");
      setIsSaving(false);
    }
  }

  async function restartAuthentication() {
    setIsSaving(true);
    try {
      await logout();
      router.replace("/");
    } catch (error) {
      const message = errorMessage(error);
      setActionError({ message, requiresRecentLogin: true });
      showStaffAlert("Não foi possível sair", message);
    } finally {
      setIsSaving(false);
    }
  }

  async function changeOfferStatus(offer: OfferPreview, status: "ACTIVE" | "PAUSED" | "CANCELLED") {
    setIsSaving(true);
    try {
      await updateLiveOfferStatus(offer.offer_id, status);
      await loadMarketplace();
    } catch (error) {
      showStaffAlert("Oferta não atualizada", errorMessage(error));
    } finally {
      setIsSaving(false);
    }
  }

  function confirmOfferClosure(offer: OfferPreview) {
    setMarketplaceModal({ kind: "CLOSE_SINGLE_OFFER", offer });
  }

  function openDiscountBatchModal() {
    const discountTypes = new Set(selectedOffersForBatch.map((offer) => offer.discount_type));
    if (discountTypes.size !== 1) {
      setOfferBatchFeedback("Selecione somente ofertas do mesmo tipo de desconto: percentual ou valor fixo.");
      return;
    }
    const selectedDiscountType = selectedOffersForBatch[0]?.discount_type;
    if (!selectedDiscountType) {
      setOfferBatchFeedback("Não foi possível identificar o tipo de desconto das ofertas selecionadas.");
      return;
    }
    setBatchDiscountValue("5");
    setOfferBatchFeedback("");
    setMarketplaceModal({ kind: "INCREASE_DISCOUNT", discountType: selectedDiscountType });
  }

  async function archiveSelectedProducts() {
    if (selectedProductIds.length === 0) return;
    const signature = [...selectedProductIds].sort().join("|");
    if (productBatchRequestRef.current?.signature !== signature) {
      productBatchRequestRef.current = {
        signature,
        requestId: createClientMessageId("product-batch"),
      };
    }
    setIsSaving(true);
    setProductBatchFeedback("");
    try {
      const result = await batchArchiveMarketplaceProducts(
        selectedProductIds,
        productBatchRequestRef.current.requestId,
      );
      productBatchRequestRef.current = null;
      setSelectedProductIds([]);
      setMarketplaceModal(null);
      await loadMarketplace();
      showStaffAlert(
        "Produtos excluídos",
        `${result.archived_count} produto(s) foram excluídos do gerenciador e do catálogo.`,
      );
    } catch (error) {
      setProductBatchFeedback(errorMessage(error));
      setMarketplaceModal(null);
    } finally {
      setIsSaving(false);
    }
  }

  async function activateSelectedProducts() {
    if (selectedProductIds.length === 0) return;
    const items = selectedProductsForBatch.map((product) => ({
      productId: product.product_id,
      stockQuantity: Number(stockDrafts[product.product_id]),
    }));
    if (items.some((item) => !Number.isInteger(item.stockQuantity) || item.stockQuantity <= 0)) {
      setProductBatchFeedback("Para ativar, informe um estoque inteiro maior que zero em cada produto selecionado.");
      setMarketplaceModal(null);
      return;
    }
    const signature = JSON.stringify({
      action: "ACTIVATE",
      items: [...items].sort((left, right) => left.productId.localeCompare(right.productId)),
    });
    if (productBatchRequestRef.current?.signature !== signature) {
      productBatchRequestRef.current = {
        signature,
        requestId: createClientMessageId("product-activate-batch"),
      };
    }
    setIsSaving(true);
    setProductBatchFeedback("");
    try {
      const result = await batchActivateMarketplaceProducts(
        items,
        productBatchRequestRef.current.requestId,
      );
      productBatchRequestRef.current = null;
      setSelectedProductIds([]);
      setMarketplaceModal(null);
      await loadMarketplace();
      showStaffAlert(
        "Estoque ativado",
        `${result.activated_count} produto(s) foram ativados e já podem participar de ofertas e descontos.`,
      );
    } catch (error) {
      setProductBatchFeedback(errorMessage(error));
      setMarketplaceModal(null);
    } finally {
      setIsSaving(false);
    }
  }

  async function runOfferBatch(input: LiveOfferBatchUpdateInput) {
    const signature = JSON.stringify({
      ...input,
      offerIds: [...input.offerIds].sort(),
    });
    if (offerBatchRequestRef.current?.signature !== signature) {
      offerBatchRequestRef.current = {
        signature,
        requestId: createClientMessageId("offer-batch"),
      };
    }
    setIsSaving(true);
    setOfferBatchFeedback("");
    try {
      const result = await batchUpdateLiveOffers(input, offerBatchRequestRef.current.requestId);
      offerBatchRequestRef.current = null;
      setSelectedOfferIds([]);
      setMarketplaceModal(null);
      await loadMarketplace();
      showStaffAlert(
        input.action === "DELETE" ? "Ofertas excluídas" : "Ofertas atualizadas",
        input.action === "DELETE"
          ? `${result.updated_count} oferta(s) excluída(s) com segurança.`
          : `${result.updated_count} oferta(s) atualizada(s). O QR atualizado fica disponível em Perfil > Vitrine > Ofertas.`,
      );
    } catch (error) {
      setOfferBatchFeedback(errorMessage(error));
      setMarketplaceModal(null);
    } finally {
      setIsSaving(false);
    }
  }

  async function submitMarketplaceModal() {
    if (!marketplaceModal) return;
    if (marketplaceModal.kind === "ACTIVATE_PRODUCTS") {
      await activateSelectedProducts();
      return;
    }
    if (marketplaceModal.kind === "ARCHIVE_PRODUCTS") {
      await archiveSelectedProducts();
      return;
    }
    if (marketplaceModal.kind === "CLOSE_SINGLE_OFFER") {
      const offer = marketplaceModal.offer;
      setMarketplaceModal(null);
      await changeOfferStatus(offer, "CANCELLED");
      return;
    }
    if (marketplaceModal.kind === "CANCEL_OFFERS") {
      await runOfferBatch({ action: "DELETE", offerIds: selectedOfferIds });
      return;
    }
    if (marketplaceModal.kind === "EXTEND_VALIDITY") {
      const extensionMinutes = Number(batchExtensionMinutes);
      if (!Number.isInteger(extensionMinutes) || extensionMinutes < 1 || extensionMinutes > 360) {
        setOfferBatchFeedback("Informe um aumento inteiro entre 1 e 360 minutos.");
        setMarketplaceModal(null);
        return;
      }
      await runOfferBatch({ action: "EXTEND_VALIDITY", offerIds: selectedOfferIds, extensionMinutes });
      return;
    }

    const discountDelta = marketplaceModal.discountType === "FIXED_AMOUNT"
      ? parseMoneyToMinor(batchDiscountValue)
      : Number(batchDiscountValue);
    if (!Number.isInteger(discountDelta) || discountDelta <= 0) {
      setOfferBatchFeedback(
        marketplaceModal.discountType === "PERCENT"
          ? "Informe um aumento percentual inteiro maior que zero."
          : "Informe um aumento em reais maior que zero.",
      );
      setMarketplaceModal(null);
      return;
    }
    const exceedsLimit = selectedOffersForBatch.some((offer) => (
      marketplaceModal.discountType === "PERCENT"
        ? offer.discount_value + discountDelta > 90
        : offer.discount_value + discountDelta >= offer.original_amount_minor
    ));
    if (exceedsLimit) {
      setOfferBatchFeedback(
        marketplaceModal.discountType === "PERCENT"
          ? "O aumento faria pelo menos uma oferta ultrapassar o limite de 90%."
          : "O aumento faria o desconto alcançar ou superar o preço de pelo menos um produto.",
      );
      setMarketplaceModal(null);
      return;
    }
    await runOfferBatch({
      action: "INCREASE_DISCOUNT",
      offerIds: selectedOfferIds,
      discountType: marketplaceModal.discountType,
      discountDelta,
    });
  }

  const modalTitle = marketplaceModal?.kind === "ACTIVATE_PRODUCTS"
    ? "Ativar estoque selecionado?"
    : marketplaceModal?.kind === "ARCHIVE_PRODUCTS"
      ? "Excluir produtos selecionados?"
    : marketplaceModal?.kind === "CANCEL_OFFERS"
      ? "Excluir ofertas selecionadas?"
      : marketplaceModal?.kind === "CLOSE_SINGLE_OFFER"
        ? "Encerrar oferta agora?"
        : marketplaceModal?.kind === "INCREASE_DISCOUNT"
          ? "Aumentar desconto"
          : marketplaceModal?.kind === "EXTEND_VALIDITY"
            ? "Aumentar tempo das ofertas"
            : "Confirmar operação";
  const modalMessage = marketplaceModal?.kind === "ACTIVATE_PRODUCTS"
    ? `${selectedProductsForBatch.length} produto(s) serão ativados com os estoques informados em cada cartão.`
    : marketplaceModal?.kind === "ARCHIVE_PRODUCTS"
      ? `${selectedProductsForBatch.length} produto(s) serão excluídos do gerenciador e do catálogo. Esta ação não pode ser desfeita.`
    : marketplaceModal?.kind === "CANCEL_OFFERS"
      ? `${selectedOffersForBatch.length} oferta(s) serão excluídas da vitrine. O backend revogará os QRs e preservará o histórico de auditoria.`
      : marketplaceModal?.kind === "CLOSE_SINGLE_OFFER"
        ? "O QR deixará de aceitar resgates imediatamente. A oferta continuará visível no Feed com o status de encerrada."
        : marketplaceModal?.kind === "INCREASE_DISCOUNT"
          ? "O backend validará os novos valores e rotacionará os QRs. Os QRs anteriores deixarão de funcionar."
          : marketplaceModal?.kind === "EXTEND_VALIDITY"
            ? "O prazo será acrescentado à validade atual. O backend rotacionará os QRs e aplicará o limite de segurança."
            : "";
  const modalConfirmLabel = marketplaceModal?.kind === "ACTIVATE_PRODUCTS"
    ? "Ativar estoque"
    : marketplaceModal?.kind === "ARCHIVE_PRODUCTS"
      ? "Excluir selecionados"
    : marketplaceModal?.kind === "CANCEL_OFFERS"
      ? "Excluir selecionadas"
      : marketplaceModal?.kind === "CLOSE_SINGLE_OFFER"
        ? "Encerrar oferta"
        : "Confirmar alteração";

  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
      <View style={styles.header}>
        <Pressable
          accessibilityLabel="Abrir meu perfil"
          onPress={() => router.replace(getAuthenticatedHomeDestination(accessSession.role, accessDestination))}
          style={styles.backButton}
        >
          <Ionicons color={colors.primaryDark} name="person-circle-outline" size={22} />
          <Text style={styles.backButtonText}>Perfil</Text>
        </Pressable>
        <View style={styles.headerText}>
          <Text style={styles.headerTitle}>Produtos e ofertas ao vivo</Text>
          <Text style={styles.headerSubtitle}>Fase 1 autoritativa TRQ-BEC</Text>
        </View>
        <LocalClock />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.apiStatus}>
          <Ionicons color={getTrqBecApiUrl() ? colors.success : colors.danger} name="server-outline" size={20} />
          <View style={styles.flex}>
            <Text style={styles.sectionTitle}>Backend comercial</Text>
            <Text style={styles.hint}>{getTrqBecApiUrl() || "URL não configurada no .env.local"}</Text>
          </View>
        </View>

        {loadError ? (
          <View style={styles.errorCard}>
            <Text style={styles.errorText}>{loadError}</Text>
            <AppButton disabled={isLoading} onPress={loadMarketplace} variant="secondary">Tentar novamente</AppButton>
          </View>
        ) : null}

        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>1. Cadastrar produto</Text>
          <Text style={styles.hint}>O preço e o estoque serão gravados no PostgreSQL pelo backend.</Text>
          <FormField label="Nome do produto" onChangeText={setProductTitle} value={productTitle} />
          <FormField label="Descrição" multiline onChangeText={setProductDescription} value={productDescription} />
          <View style={styles.fieldRow}>
            <FormField containerStyle={styles.fieldColumn} keyboardType="decimal-pad" label="Preço (R$)" onChangeText={setProductPrice} value={productPrice} />
            <FormField containerStyle={styles.fieldColumn} keyboardType="number-pad" label="Estoque" onChangeText={setProductStock} value={productStock} />
          </View>
          <MediaImagePicker
            disabled={isSaving}
            hint="Opcional. O backend gera somente thumbnail e display; a imagem não é gravada no PostgreSQL."
            label="Imagem do produto"
            onChange={setNewProductImage}
            value={newProductImage}
          />
          <AppButton disabled={isSaving} onPress={createProduct}>Salvar produto no backend</AppButton>
        </View>

        <View style={styles.sectionCard}>
          <View style={styles.sectionHeadingRow}>
            <View style={styles.flex}>
              <Text style={styles.sectionTitle}>2. Gerenciar produtos e estoque</Text>
              <Text style={styles.hint}>
                {isLoading
                  ? "Carregando..."
                  : `${visibleProducts.length} produto(s) cadastrado(s) · ${selectedProductIds.length} selecionado(s)`}
              </Text>
            </View>
            <Pressable accessibilityLabel="Atualizar produtos" disabled={isLoading} onPress={loadMarketplace} style={styles.refreshButton}>
              <Ionicons color={colors.primary} name="refresh" size={20} />
            </Pressable>
          </View>
          <View style={styles.productList}>
            {visibleProducts.length === 0 && !isLoading ? (
              <Text style={styles.emptyText}>Cadastre o primeiro produto acima.</Text>
            ) : null}
            {visibleProducts.map((product) => {
              const selectedForBatch = selectedProductIds.includes(product.product_id);
              return (
                <View
                  key={product.product_id}
                  style={[styles.productCard, selectedForBatch && styles.batchSelected]}
                >
                  <PublicEntityMediaImage
                    contentFit="cover"
                    entityId={product.product_id}
                    entityType="product"
                    fallback={null}
                    mediaRole="product_image"
                    style={styles.productMediaPreview}
                    variant="thumbnail"
                  />
                  <View style={styles.selectionRow}>
                    <Pressable
                      accessibilityLabel={`Selecionar ${product.title} para ação em bloco`}
                      accessibilityRole="checkbox"
                      accessibilityState={{ checked: selectedForBatch, disabled: isSaving }}
                      disabled={isSaving}
                      onPress={() => toggleProductForBatch(product.product_id)}
                      style={styles.checkboxButton}
                    >
                      <Ionicons
                        color={selectedForBatch ? colors.primary : colors.textMuted}
                        name={selectedForBatch ? "checkbox" : "square-outline"}
                        size={24}
                      />
                    </Pressable>
                    <Text style={styles.checkboxLabel}>Incluir nas ações em bloco</Text>
                  </View>
                  <View style={styles.productMain}>
                    <Ionicons color={colors.primary} name="cube-outline" size={22} />
                    <View style={styles.flex}>
                      <Text style={styles.productTitle}>{product.title}</Text>
                      <Text style={styles.hint}>
                        {formatMoney(product.price_minor)} · {formatProductStatus(product.status)} · estoque atual {product.stock_quantity}
                      </Text>
                    </View>
                  </View>
                  <View style={styles.stockRow}>
                    <FormField
                      containerStyle={styles.fieldColumn}
                      keyboardType="number-pad"
                      label="Estoque autoritativo"
                      onChangeText={(value) => setStockDrafts((current) => ({ ...current, [product.product_id]: value }))}
                      value={stockDrafts[product.product_id] ?? String(product.stock_quantity)}
                    />
                    <AppButton
                      disabled={isSaving}
                      onPress={() => saveStock(product)}
                      variant="secondary"
                    >
                      Atualizar
                    </AppButton>
                  </View>
                  <Text style={styles.hint}>Use estoque zero para indicar que as unidades terminaram.</Text>
                  <MediaImagePicker
                    disabled={isSaving}
                    hint="A vitrine usa automaticamente a versão processada mais recente."
                    label="Atualizar imagem"
                    onChange={(image) => setProductImageDrafts((current) => ({ ...current, [product.product_id]: image }))}
                    value={productImageDrafts[product.product_id] || null}
                  />
                  <AppButton
                    disabled={isSaving || !productImageDrafts[product.product_id]}
                    onPress={() => void saveProductImage(product)}
                    variant="secondary"
                  >
                    Enviar imagem do produto
                  </AppButton>
                  <AppButton
                    accessibilityLabel={`Compartilhar produto ${product.title}`}
                    onPress={() => void shareLiberRotasItem({
                      kind: "product",
                      title: product.title,
                      description: `${formatMoney(product.price_minor)} · ${product.description}`,
                      path: profileSharePath(profile.id, { tab: "products", itemId: product.product_id }),
                    })}
                    variant="secondary"
                  >
                    Compartilhar produto
                  </AppButton>
                </View>
              );
            })}
          </View>
          {visibleProducts.length > 0 ? (
            <View style={styles.batchActionPanel}>
              <Text style={styles.batchPanelTitle}>Ações em bloco</Text>
              <Text style={styles.safeDeleteHint}>
                Marque os produtos acima e informe o estoque individual de cada um antes de ativar.
              </Text>
              <View style={styles.batchButtonGrid}>
                <AppButton
                  disabled={isSaving || selectedProductIds.length === Math.min(visibleProducts.length, 25)}
                  onPress={selectAllProducts}
                  variant="secondary"
                >
                  Selecionar todos
                </AppButton>
                <AppButton
                  disabled={isSaving || selectedProductIds.length === 0}
                  onPress={() => { setSelectedProductIds([]); setProductBatchFeedback(""); }}
                  variant="secondary"
                >
                  Limpar seleção
                </AppButton>
              </View>
              <AppButton
                disabled={isSaving || selectedProductIds.length === 0}
                onPress={() => setMarketplaceModal({ kind: "ACTIVATE_PRODUCTS" })}
              >
                Ativar estoque selecionado ({selectedProductIds.length})
              </AppButton>
              <Text style={styles.safeDeleteHint}>
                Excluir retira definitivamente os produtos do seu gerenciador e do catálogo.
              </Text>
              <AppButton
                disabled={isSaving || selectedProductIds.length === 0}
                onPress={() => setMarketplaceModal({ kind: "ARCHIVE_PRODUCTS" })}
                variant="danger"
              >
                Excluir selecionados ({selectedProductIds.length})
              </AppButton>
              {productBatchFeedback ? (
                <View style={styles.errorCard}>
                  <Text style={styles.errorText}>{productBatchFeedback}</Text>
                </View>
              ) : null}
            </View>
          ) : null}
        </View>

        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>3. Emitir oferta ao vivo</Text>
          <Text style={styles.hint}>
            Selecione um ou mais produtos. Cada cupom começa com todo o estoque registrado e validade sugerida de 8 horas.
          </Text>
          <Text style={styles.hint}>
            Ao emitir uma única oferta, o QR abre nesta tela. Para novas vendas, escolha a quantidade em Ofertas emitidas e toque em Gerar QR para venda.
          </Text>
          {issuableProducts.length > 0 ? (
            <View style={styles.batchButtonGrid}>
              <AppButton
                disabled={isSaving || selectedOfferProductIds.length === Math.min(issuableProducts.length, MAX_OFFER_PRODUCTS_PER_ISSUE)}
                onPress={selectAllProductsForOffer}
                variant="secondary"
              >
                Selecionar todos
              </AppButton>
              <AppButton
                disabled={isSaving || selectedOfferProductIds.length === 0}
                onPress={() => { setSelectedOfferProductIds([]); setActionError(null); }}
                variant="secondary"
              >
                Limpar seleção
              </AppButton>
            </View>
          ) : null}
          <View style={styles.offerProductList}>
            {issuableProducts.length === 0 ? (
              <Text style={styles.emptyText}>Nenhum produto ativo possui estoque. Ative o estoque na seção 2.</Text>
            ) : null}
            {issuableProducts.map((product) => {
              const selectedForOffer = selectedOfferProductIds.includes(product.product_id);
              const draft = offerDrafts[product.product_id] ?? defaultOfferDraft(product);
              return (
                <View
                  key={`offer-form:${product.product_id}`}
                  style={[styles.offerProductCard, selectedForOffer && styles.productSelected]}
                >
                  <Pressable
                    accessibilityLabel={`Selecionar ${product.title} para emitir oferta`}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: selectedForOffer, disabled: isSaving }}
                    disabled={isSaving}
                    onPress={() => toggleProductForOffer(product)}
                    style={styles.offerProductHeader}
                  >
                    <Ionicons
                      color={selectedForOffer ? colors.primary : colors.textMuted}
                      name={selectedForOffer ? "checkbox" : "square-outline"}
                      size={26}
                    />
                    <View style={styles.flex}>
                      <Text style={styles.productTitle}>{product.title}</Text>
                      <Text style={styles.hint}>
                        {formatMoney(product.price_minor)} · estoque registrado: {product.stock_quantity}
                      </Text>
                    </View>
                  </Pressable>
                  {selectedForOffer ? (
                    <View style={styles.offerDraftFields}>
                      <Text style={styles.offerConfigTitle}>Configurações do cupom</Text>
                      <View style={styles.choiceRow}>
                        <Pressable
                          onPress={() => updateOfferDraft(product, { discountType: "PERCENT" })}
                          style={[styles.choice, draft.discountType === "PERCENT" && styles.choiceSelected]}
                        >
                          <Text style={[styles.choiceText, draft.discountType === "PERCENT" && styles.choiceTextSelected]}>
                            Percentual
                          </Text>
                        </Pressable>
                        <Pressable
                          onPress={() => updateOfferDraft(product, { discountType: "FIXED_AMOUNT" })}
                          style={[styles.choice, draft.discountType === "FIXED_AMOUNT" && styles.choiceSelected]}
                        >
                          <Text style={[styles.choiceText, draft.discountType === "FIXED_AMOUNT" && styles.choiceTextSelected]}>
                            Valor fixo
                          </Text>
                        </Pressable>
                      </View>
                      <FormField
                        keyboardType="decimal-pad"
                        label={draft.discountType === "PERCENT" ? "Desconto (%)" : "Desconto (R$)"}
                        onChangeText={(value) => updateOfferDraft(product, { discountValue: value })}
                        value={draft.discountValue}
                      />
                      <View style={styles.fieldRow}>
                        <FormField
                          containerStyle={styles.fieldColumn}
                          keyboardType="number-pad"
                          label={`Quantidade da oferta (máx. ${product.stock_quantity})`}
                          onChangeText={(value) => updateOfferDraft(product, { maximumRedemptions: value })}
                          value={draft.maximumRedemptions}
                        />
                        <FormField
                          containerStyle={styles.fieldColumn}
                          keyboardType="number-pad"
                          label="Validade (horas)"
                          onChangeText={(value) => updateOfferDraft(product, { validityHours: value })}
                          value={draft.validityHours}
                        />
                      </View>
                    </View>
                  ) : null}
                </View>
              );
            })}
          </View>
          <AppButton disabled={isSaving || selectedOfferProductIds.length === 0} onPress={issueSelectedOffers}>
            {isSaving
              ? "Emitindo ofertas..."
              : `Emitir ${selectedOfferProductIds.length || ""} oferta(s) selecionada(s)`}
          </AppButton>
          {actionError ? (
            <View style={styles.errorCard}>
              <Text style={styles.errorTitle}>Não foi possível concluir a ação</Text>
              <Text style={styles.errorText}>{actionError.message}</Text>
              {actionError.requiresRecentLogin ? (
                <AppButton onPress={restartAuthentication} variant="secondary">Sair e entrar novamente</AppButton>
              ) : null}
            </View>
          ) : null}
        </View>

        <View style={styles.sectionCard}>
          <View style={styles.sectionHeadingRow}>
            <View style={styles.flex}>
              <Text style={styles.sectionTitle}>Ofertas emitidas</Text>
              <Text style={styles.hint}>{selectedOfferIds.length} oferta(s) selecionada(s)</Text>
            </View>
          </View>
          {offerBatchFeedback ? (
            <View style={styles.errorCard}>
              <Text style={styles.errorText}>{offerBatchFeedback}</Text>
            </View>
          ) : null}
          {offers.length === 0 ? <Text style={styles.emptyText}>Nenhuma oferta emitida.</Text> : null}
          {paginatedOffers.map((offer) => {
            const timeEnded = hasTimeEnded(offer.expires_at * 1_000, nowMs);
            const canSelectForBatch = !timeEnded && (offer.status === "ACTIVE" || offer.status === "PAUSED");
            const selectedForBatch = selectedOfferIds.includes(offer.offer_id);
            const canGenerateQr = !timeEnded && offer.status === "ACTIVE" && offer.remaining_redemptions > 0;
            return (
              <View key={offer.offer_id} style={[styles.offerCard, selectedForBatch && styles.batchSelected]}>
                <View style={styles.selectionRow}>
                  <Pressable
                    accessibilityLabel={`Selecionar oferta de ${offer.product_title}`}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: selectedForBatch, disabled: !canSelectForBatch }}
                    disabled={!canSelectForBatch || isSaving}
                    onPress={() => toggleOfferForBatch(offer.offer_id)}
                    style={[styles.checkboxButton, !canSelectForBatch && styles.disabledControl]}
                  >
                    <Ionicons
                      color={selectedForBatch ? colors.primary : colors.textMuted}
                      name={selectedForBatch ? "checkbox" : "square-outline"}
                      size={24}
                    />
                  </Pressable>
                  <View style={styles.flex}>
                    <Text style={styles.productTitle}>{offer.product_title}</Text>
                    <Text style={styles.hint}>{canSelectForBatch ? "Selecionar para ação em lote" : "Oferta encerrada"}</Text>
                  </View>
                </View>
                <Text style={styles.hint}>
                  {timeEnded ? "EXPIRADA" : offer.status} · {offer.remaining_redemptions} restante(s) · {formatMoney(offer.final_amount_minor)}
                </Text>
                <Text style={styles.hint}>
                  {offer.discount_type === "PERCENT"
                    ? `${offer.discount_value}% de desconto`
                    : `${formatMoney(offer.discount_value)} de desconto fixo`}
                </Text>
                {!timeEnded && (offer.status === "ACTIVE" || offer.status === "PAUSED") ? (
                  <Text style={styles.hint}>Tempo restante {formatRemainingTime(offer.expires_at * 1_000, nowMs)}</Text>
                ) : null}
                {canGenerateQr ? (
                  <FormField
                    accessibilityLabel={`Quantidade para vender ${offer.product_title}`}
                    editable={!isSaving}
                    keyboardType="number-pad"
                    label="Quantidade para esta venda"
                    maxLength={4}
                    onChangeText={(value) => setQrQuantityTexts((current) => ({
                      ...current, [offer.offer_id]: value.replace(/\D/g, ""),
                    }))}
                    value={qrQuantityTexts[offer.offer_id] ?? "1"}
                  />
                ) : null}
                {!timeEnded && offer.status === "PAUSED" ? (
                  <Text style={styles.hint}>Reative a oferta para gerar o QR para venda.</Text>
                ) : null}
                <View style={styles.actionRow}>
                  {canGenerateQr ? (
                    <AppButton
                      accessibilityLabel={`Gerar QR para vender ${offer.product_title}`}
                      disabled={isSaving}
                      onPress={() => void generateSaleQr(offer)}
                    >
                      {generatingQrOfferId === offer.offer_id ? "Gerando QR..." : "Gerar QR para venda"}
                    </AppButton>
                  ) : null}
                  <AppButton
                    accessibilityLabel={`Compartilhar oferta ${offer.product_title}`}
                    onPress={() => void shareLiberRotasItem({
                      kind: "offer",
                      title: offer.product_title,
                      description: `${formatMoney(offer.final_amount_minor)} · ${offer.remaining_redemptions} resgate(s) disponível(is)`,
                      path: profileSharePath(profile.id, { tab: "offers", itemId: offer.offer_id }),
                    })}
                    variant="secondary"
                  >
                    Compartilhar
                  </AppButton>
                  {!timeEnded && offer.status === "ACTIVE" ? (
                    <AppButton disabled={isSaving} onPress={() => changeOfferStatus(offer, "PAUSED")} variant="secondary">Pausar</AppButton>
                  ) : !timeEnded && offer.status === "PAUSED" ? (
                    <AppButton disabled={isSaving} onPress={() => changeOfferStatus(offer, "ACTIVE")} variant="secondary">Reativar</AppButton>
                  ) : null}
                  {!timeEnded && (offer.status === "ACTIVE" || offer.status === "PAUSED") ? (
                    <AppButton disabled={isSaving} onPress={() => confirmOfferClosure(offer)} variant="danger">Encerrar oferta</AppButton>
                  ) : null}
                </View>
              </View>
            );
          })}
          <PaginationControls
            label="ofertas emitidas"
            onPageChange={setOffersPage}
            page={safeOffersPage}
            pageSize={HISTORY_PAGE_SIZE}
            totalItems={offers.length}
          />
          {offers.some((offer) => !hasTimeEnded(offer.expires_at * 1_000, nowMs) && (offer.status === "ACTIVE" || offer.status === "PAUSED")) ? (
            <View style={styles.batchActionPanel}>
              <Text style={styles.safeDeleteHint}>
                Excluir selecionadas revoga os QRs e retira as ofertas do Feed, preservando auditoria e resgates anteriores.
              </Text>
              <View style={styles.batchButtonGrid}>
                <AppButton
                  disabled={isSaving || selectedOfferIds.length === 0}
                  onPress={() => setMarketplaceModal({ kind: "CANCEL_OFFERS" })}
                  variant="danger"
                >
                  Excluir selecionadas
                </AppButton>
                <AppButton
                  disabled={isSaving || selectedOfferIds.length === 0}
                  onPress={openDiscountBatchModal}
                  variant="secondary"
                >
                  Aumentar desconto
                </AppButton>
                <AppButton
                  disabled={isSaving || selectedOfferIds.length === 0}
                  onPress={() => { setBatchExtensionMinutes("60"); setOfferBatchFeedback(""); setMarketplaceModal({ kind: "EXTEND_VALIDITY" }); }}
                  variant="secondary"
                >
                  Aumentar tempo
                </AppButton>
              </View>
            </View>
          ) : null}
        </View>
      </ScrollView>

      <SaleQrModal result={qrResult} nowMs={nowMs} onChange={setQrResult} onInventoryChanged={loadMarketplace} />

      <Modal
        animationType="fade"
        onRequestClose={() => { if (!isSaving) setMarketplaceModal(null); }}
        transparent
        visible={marketplaceModal !== null}
      >
        <View style={styles.modalOverlay}>
          <View accessibilityViewIsModal style={styles.modalCard}>
            <View style={styles.modalIcon}>
              <Ionicons
                color={marketplaceModal?.kind === "ARCHIVE_PRODUCTS" || marketplaceModal?.kind === "CANCEL_OFFERS" || marketplaceModal?.kind === "CLOSE_SINGLE_OFFER"
                  ? colors.danger
                  : colors.primary}
                name={marketplaceModal?.kind === "INCREASE_DISCOUNT"
                  ? "pricetag-outline"
                  : marketplaceModal?.kind === "EXTEND_VALIDITY"
                    ? "time-outline"
                    : marketplaceModal?.kind === "ACTIVATE_PRODUCTS"
                      ? "power-outline"
                      : "warning-outline"}
                size={28}
              />
            </View>
            <Text style={styles.modalTitle}>{modalTitle}</Text>
            <Text style={styles.modalMessage}>{modalMessage}</Text>

            {marketplaceModal?.kind === "INCREASE_DISCOUNT" ? (
              <FormField
                keyboardType="decimal-pad"
                label={marketplaceModal.discountType === "PERCENT"
                  ? "Aumento em pontos percentuais"
                  : "Aumento do desconto (R$)"}
                onChangeText={setBatchDiscountValue}
                value={batchDiscountValue}
              />
            ) : null}
            {marketplaceModal?.kind === "EXTEND_VALIDITY" ? (
              <FormField
                keyboardType="number-pad"
                label="Minutos adicionais"
                onChangeText={setBatchExtensionMinutes}
                value={batchExtensionMinutes}
              />
            ) : null}

            <View style={styles.modalActions}>
              <AppButton
                disabled={isSaving}
                onPress={() => setMarketplaceModal(null)}
                style={styles.modalActionButton}
                variant="secondary"
              >
                Cancelar
              </AppButton>
              <AppButton
                disabled={isSaving}
                onPress={submitMarketplaceModal}
                style={styles.modalActionButton}
                variant={marketplaceModal?.kind === "ARCHIVE_PRODUCTS" || marketplaceModal?.kind === "CANCEL_OFFERS" || marketplaceModal?.kind === "CLOSE_SINGLE_OFFER"
                  ? "danger"
                  : "primary"}
              >
                {isSaving ? "Processando..." : modalConfirmLabel}
              </AppButton>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.cream, flex: 1 },
  header: { alignItems: "center", backgroundColor: colors.cream, flexDirection: "row", gap: 12, minHeight: 72, paddingHorizontal: 18 },
  backButton: { alignItems: "center", backgroundColor: colors.surface, borderRadius: 22, flexDirection: "row", gap: 6, minHeight: 44, paddingHorizontal: 12 },
  backButtonText: { color: colors.primaryDark, fontSize: 12, fontWeight: "900" },
  headerText: { flex: 1 },
  headerTitle: { color: colors.primary, fontSize: 18, fontWeight: "800" },
  headerSubtitle: { color: colors.textMuted, fontSize: 10, marginTop: 2 },
  content: { backgroundColor: colors.surfaceMuted, gap: 14, padding: 16, paddingBottom: 40 },
  flex: { flex: 1 },
  apiStatus: { alignItems: "center", backgroundColor: colors.surface, borderRadius: radius.medium, flexDirection: "row", gap: 12, padding: 14 },
  sectionCard: { backgroundColor: colors.surface, borderRadius: radius.large, gap: 12, padding: 16, ...shadow },
  sectionTitle: { color: colors.primaryDark, fontSize: 17, fontWeight: "900" },
  hint: { color: colors.textMuted, fontSize: 11, lineHeight: 16 },
  errorCard: { backgroundColor: "#FFF0EE", borderColor: "#F4B8B0", borderRadius: radius.medium, borderWidth: 1, gap: 10, padding: 14 },
  errorTitle: { color: colors.danger, fontSize: 14, fontWeight: "800" },
  errorText: { color: colors.danger, fontSize: 12, lineHeight: 18 },
  fieldRow: { flexDirection: "row", gap: 10 },
  fieldColumn: { flex: 1, minWidth: 0 },
  sectionHeadingRow: { alignItems: "center", flexDirection: "row", gap: 10 },
  refreshButton: { alignItems: "center", backgroundColor: colors.cream, borderRadius: 20, height: 40, justifyContent: "center", width: 40 },
  productList: { gap: 10 },
  productCard: { borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, gap: 10, padding: 12 },
  productMediaPreview: { backgroundColor: colors.cream, borderRadius: radius.small, height: 150, width: "100%" },
  productSelected: { backgroundColor: "#F2F6FF", borderColor: colors.primary, borderWidth: 2 },
  offerProductList: { gap: 12 },
  offerProductCard: { borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, gap: 10, padding: 12 },
  offerProductHeader: { alignItems: "center", flexDirection: "row", gap: 10, minHeight: 44 },
  offerDraftFields: { borderTopColor: colors.border, borderTopWidth: 1, gap: 10, paddingTop: 12 },
  offerConfigTitle: { color: colors.primaryDark, fontSize: 12, fontWeight: "900" },
  batchSelected: { backgroundColor: "#FFF8E8", borderColor: colors.accent },
  productMain: { alignItems: "center", flexDirection: "row", gap: 10 },
  productTitle: { color: colors.primaryDark, fontSize: 14, fontWeight: "800" },
  stockRow: { alignItems: "center", flexDirection: "row", gap: 10 },
  selectionRow: { alignItems: "center", flexDirection: "row", gap: 8 },
  checkboxButton: { alignItems: "center", justifyContent: "center", minHeight: 38, minWidth: 38 },
  checkboxLabel: { color: colors.textMuted, flex: 1, fontSize: 11, fontWeight: "700" },
  disabledControl: { opacity: 0.45 },
  batchActionPanel: { backgroundColor: colors.cream, borderRadius: radius.medium, gap: 10, padding: 12 },
  batchPanelTitle: { color: colors.primaryDark, fontSize: 14, fontWeight: "900" },
  safeDeleteHint: { color: colors.primaryDark, fontSize: 11, lineHeight: 16 },
  batchButtonGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choiceRow: { flexDirection: "row", gap: 8 },
  choice: { backgroundColor: colors.cream, borderRadius: radius.pill, flex: 1, padding: 10 },
  choiceSelected: { backgroundColor: colors.primary },
  choiceText: { color: colors.primary, fontSize: 12, fontWeight: "700", textAlign: "center" },
  choiceTextSelected: { color: colors.surface },
  offerCard: { borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, gap: 6, padding: 12 },
  actionRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 4 },
  emptyText: { color: colors.textMuted, fontSize: 12, fontStyle: "italic" },
  modalOverlay: { alignItems: "center", backgroundColor: "rgba(2, 24, 68, 0.62)", flex: 1, justifyContent: "center", padding: 20 },
  modalCard: { backgroundColor: colors.surface, borderRadius: radius.large, gap: 12, maxWidth: 520, padding: 20, width: "100%", ...shadow },
  modalIcon: { alignItems: "center", alignSelf: "center", backgroundColor: colors.cream, borderRadius: 28, height: 56, justifyContent: "center", width: 56 },
  modalTitle: { color: colors.primaryDark, fontSize: 19, fontWeight: "900", textAlign: "center" },
  modalMessage: { color: colors.textMuted, fontSize: 13, lineHeight: 20, textAlign: "center" },
  modalActions: { flexDirection: "row", gap: 10, marginTop: 4 },
  modalActionButton: { flex: 1 },
});
