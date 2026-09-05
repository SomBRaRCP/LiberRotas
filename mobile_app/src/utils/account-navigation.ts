import type { Href } from "expo-router";
import type { AccessDestination } from "@/context/app-context";
import type { AccessRole } from "@/security/trq-bec/service";

const PROFILE_DESTINATION = "/(tabs)/perfil" as Href;

/**
 * Retorno seguro para telas privadas.
 *
 * Visitante e empreendedor voltam ao próprio Perfil. As funções internas
 * retornam ao painel que o backend já autorizou; nunca escolhem a função pela
 * rota aberta no navegador.
 */
export function getAuthenticatedHomeDestination(
  role: AccessRole | null | undefined,
  accessDestination: AccessDestination,
): Href {
  if (role === "visitor" || role === "entrepreneur") return PROFILE_DESTINATION;
  return accessDestination as Href;
}

export function getAuthenticatedHomeLabel(role: AccessRole | null | undefined) {
  return role === "visitor" || role === "entrepreneur" ? "Perfil" : "Painel";
}
