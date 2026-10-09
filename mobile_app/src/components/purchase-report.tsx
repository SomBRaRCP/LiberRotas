import { StyleSheet, Text, View } from "react-native";
import { colors, radius } from "@/constants/theme";
import { formatPurchaseMoney, type VisitorPurchasesReport } from "@/features/marketplace/purchases";

export function PurchaseReport({ report }: { report: VisitorPurchasesReport }) {
  if (!report.total_purchases) {
    return <Text style={styles.description}>Você ainda não tem compras confirmadas. Ao resgatar uma oferta pelo QR Code, ela aparecerá aqui.</Text>;
  }

  return <View style={styles.list}>
    <Text style={styles.description}>
      {report.total_purchases} {report.total_purchases === 1 ? "compra confirmada" : "compras confirmadas"} · {report.total_units} {report.total_units === 1 ? "produto comprado" : "produtos comprados"}
    </Text>
    {report.totals.map((total) => <View key={total.currency} style={styles.summary}>
      <Text style={styles.currency}>Resumo · {total.currency}</Text>
      <View style={styles.amounts}>
        <View style={styles.amountBlock}>
          <Text style={styles.label}>{total.amounts_unavailable_count ? "Gasto com valor registrado" : "Total gasto"}</Text>
          <Text style={styles.spent}>{formatPurchaseMoney(total.spent_amount_minor, total.currency)}</Text>
        </View>
        <View style={styles.amountBlock}>
          <Text style={styles.label}>Você economizou</Text>
          <Text style={styles.saved}>{formatPurchaseMoney(total.saved_amount_minor, total.currency)}</Text>
        </View>
      </View>
      {total.amounts_unavailable_count ? <Text style={styles.description}>
        {total.amounts_unavailable_count} {total.amounts_unavailable_count === 1 ? "compra antiga sem valor gasto disponível" : "compras antigas sem valor gasto disponível"}. O gasto dessas compras não está incluído no resumo.
      </Text> : null}
    </View>)}
    <Text style={styles.historyTitle}>Onde você comprou</Text>
    {report.items.map((purchase) => <View key={purchase.redemption_id} style={styles.card}>
      <Text style={styles.merchant}>{purchase.establishment_name || purchase.merchant_name}</Text>
      {purchase.establishment_name && purchase.establishment_name !== purchase.merchant_name ? <Text style={styles.description}>Vendedor: {purchase.merchant_name}</Text> : null}
      <Text style={styles.product}>{purchase.product_title}</Text>
      <Text style={styles.description}>
        {new Date(purchase.purchased_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })} · {purchase.quantity} {purchase.quantity === 1 ? "unidade" : "unidades"}
      </Text>
      <View style={styles.amounts}>
        <View style={styles.amountBlock}>
          <Text style={styles.label}>Valor gasto</Text>
          <Text style={styles.value}>{purchase.final_amount_minor === null ? "Indisponível" : formatPurchaseMoney(purchase.final_amount_minor, purchase.currency)}</Text>
        </View>
        <View style={styles.amountBlock}>
          <Text style={styles.label}>Economia</Text>
          <Text style={styles.savedValue}>{formatPurchaseMoney(purchase.saved_amount_minor, purchase.currency)}</Text>
        </View>
      </View>
    </View>)}
  </View>;
}

const styles = StyleSheet.create({
  list: { gap: 12 },
  summary: { backgroundColor: colors.cream, borderRadius: radius.medium, padding: 16, gap: 10 },
  currency: { color: colors.primaryDark, fontSize: 13, fontWeight: "800" },
  amounts: { flexDirection: "row", flexWrap: "wrap", gap: 16 },
  amountBlock: { flexGrow: 1, flexBasis: 125, gap: 4 },
  label: { color: colors.textMuted, fontSize: 12 },
  spent: { color: colors.primaryDark, fontSize: 23, fontWeight: "900" },
  saved: { color: colors.success, fontSize: 23, fontWeight: "900" },
  description: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  historyTitle: { color: colors.primaryDark, fontSize: 14, fontWeight: "800", marginTop: 4 },
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: radius.medium, padding: 14, gap: 7 },
  merchant: { color: colors.primaryDark, fontSize: 15, fontWeight: "800" },
  product: { color: colors.text, fontSize: 14, fontWeight: "600" },
  value: { color: colors.primaryDark, fontSize: 16, fontWeight: "800" },
  savedValue: { color: colors.success, fontSize: 16, fontWeight: "800" },
});
