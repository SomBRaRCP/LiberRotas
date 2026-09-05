export type PinhaisCategory =
  | "pontos_turisticos"
  | "parques"
  | "feiras_livres"
  | "artesanato"
  | "bordados"
  | "gastronomia"
  | "eventos"
  | "comercio_local";

export type PinhaisPlace = {
  id: string;
  ownerId?: string;
  ownerName?: string;
  createdAtMs?: number;
  nome: string;
  categoriaApp: PinhaisCategory;
  categoriasSecundarias?: PinhaisCategory[];
  endereco: string;
  latitude: number;
  longitude: number;
  rating: number | null;
  totalAvaliacoes: number;
  origem: "google_places" | "curadoria_manual" | "seed_pinhais";
  buscaOrigem: string;
  ativo: boolean;
  curadoriaManual: boolean;
  potencialTuristico: number;
  tags: string[];
  resumo: string;
  googlePlaceId?: string;
  googleMapsUri?: string;
  /** Somente pontos com endereço físico verificado devem virar marcadores. */
  mapVerified?: boolean;
  mapPosition: {
    x: number;
    y: number;
  };
};

export type LiveFairStatus = "scheduled" | "live" | "ended";

export type LiveFairEndReason = "manual" | "scheduled";

export type LiveFair = {
  id: string;
  ownerId: string;
  ownerName: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  startsAtMs: number;
  endsAtMs: number;
  createdAtMs: number;
  status: LiveFairStatus;
  endedAtMs?: number;
  endReason?: LiveFairEndReason;
  googleMapsUri: string;
  mapPosition: {
    x: number;
    y: number;
  };
};

/**
 * Calcula o status visual pelo relógio de referência. As telas passam a hora
 * sincronizada; o backend continua sendo a autoridade para encerrar a feira.
 */
export function resolveLiveFairStatus(
  fair: Pick<LiveFair, "status" | "startsAtMs" | "endsAtMs" | "endedAtMs">,
  referenceTimeMs = Date.now(),
): LiveFairStatus {
  if (fair.status === "ended" || fair.endedAtMs || fair.endsAtMs <= referenceTimeMs) return "ended";
  if (fair.startsAtMs > referenceTimeMs) return "scheduled";
  return "live";
}

export const PINHAIS_CENTER = {
  latitude: -25.4325,
  longitude: -49.1931,
} as const;

/**
 * Converte coordenadas reais em uma posicao aproximada dentro do mapa visual
 * de Pinhais. O limite evita que marcadores validos fiquem fora da area util.
 */
export function estimatePinhaisMapPosition(latitude: number, longitude: number) {
  const west = -49.23;
  const east = -49.12;
  const north = -25.405;
  const south = -25.462;
  const x = ((longitude - west) / (east - west)) * 100;
  const y = ((latitude - north) / (south - north)) * 100;

  return {
    x: Math.min(92, Math.max(8, x)),
    y: Math.min(88, Math.max(12, y)),
  };
}

export const PINHAIS_RADIUS_METERS = 9000;

export const pinhaisCategoryLabels: Record<PinhaisCategory, string> = {
  pontos_turisticos: "Turismo",
  parques: "Parques",
  feiras_livres: "Feiras",
  artesanato: "Artesanato",
  bordados: "Bordados",
  gastronomia: "Gastronomia",
  eventos: "Eventos",
  comercio_local: "Comercio local",
};

export const pinhaisCategoryColors: Record<PinhaisCategory, string> = {
  pontos_turisticos: "#2B5CC7",
  parques: "#178653",
  feiras_livres: "#FF6E17",
  artesanato: "#C83D7A",
  bordados: "#B7791F",
  gastronomia: "#B42318",
  eventos: "#6B4FD8",
  comercio_local: "#4A5568",
};

export const pinhaisFilterOptions: { label: string; value: PinhaisCategory | "todos" }[] = [
  { label: "Todos", value: "todos" },
  { label: "Turismo", value: "pontos_turisticos" },
  { label: "Feiras", value: "feiras_livres" },
  { label: "Artesanato", value: "artesanato" },
  { label: "Bordados", value: "bordados" },
  { label: "Parques", value: "parques" },
  { label: "Gastronomia", value: "gastronomia" },
  { label: "Eventos", value: "eventos" },
  { label: "Comercio", value: "comercio_local" },
];

export const googlePlacesNearbySearches: { types: string[]; categoria: PinhaisCategory }[] = [
  { types: ["tourist_attraction"], categoria: "pontos_turisticos" },
  { types: ["park", "city_park", "plaza"], categoria: "parques" },
  { types: ["convention_center", "event_venue"], categoria: "eventos" },
  { types: ["farmers_market", "flea_market", "market"], categoria: "feiras_livres" },
  { types: ["gift_shop", "store"], categoria: "artesanato" },
  { types: ["restaurant", "cafe", "coffee_shop", "bakery", "bar"], categoria: "gastronomia" },
];

export const googlePlacesTextSearches: { query: string; categoria: PinhaisCategory }[] = [
  { query: "Expotrade Convention Center Pinhais", categoria: "eventos" },
  { query: "Parque das Aguas Pinhais", categoria: "parques" },
  { query: "Espaco Boulevard Parque das Aguas Pinhais", categoria: "eventos" },
  { query: "feira livre Pinhais PR", categoria: "feiras_livres" },
  { query: "feira de artesanato Pinhais", categoria: "artesanato" },
  { query: "artesanato em Pinhais PR", categoria: "artesanato" },
  { query: "bordados em Pinhais PR", categoria: "bordados" },
  { query: "loja de artesanato Pinhais", categoria: "artesanato" },
  { query: "presentes artesanais Pinhais", categoria: "comercio_local" },
  { query: "pontos turisticos em Pinhais PR", categoria: "pontos_turisticos" },
  { query: "restaurantes perto do Parque das Aguas Pinhais", categoria: "gastronomia" },
  { query: "eventos no Expotrade Pinhais", categoria: "eventos" },
];

export const pinhaisPlaces: PinhaisPlace[] = [
  {
    id: "pinhais-expotrade",
    nome: "Expotrade Convention Center",
    categoriaApp: "eventos",
    categoriasSecundarias: ["pontos_turisticos"],
    endereco: "Rod. Dep. João Leopoldo Jacomel, 10454 - Jardim Amélia, Pinhais, PR, 83330-167",
    latitude: -25.4341738,
    longitude: -49.1673043,
    rating: null,
    totalAvaliacoes: 0,
    origem: "seed_pinhais",
    buscaOrigem: "Expotrade Convention Center Pinhais",
    ativo: true,
    curadoriaManual: false,
    potencialTuristico: 92,
    tags: ["centro de convencoes", "eventos", "turismo de negocios"],
    resumo: "Centro de eventos de grande porte usado como ancora para turismo de negocios e agenda regional.",
    googleMapsUri: "https://www.google.com/maps/search/?api=1&query=Expotrade%20Convention%20Center%20Pinhais",
    mapPosition: estimatePinhaisMapPosition(-25.4341738, -49.1673043),
  },
  {
    id: "pinhais-parque-das-aguas",
    nome: "Parque das Aguas",
    categoriaApp: "parques",
    categoriasSecundarias: ["eventos", "pontos_turisticos"],
    endereco: "Rod. Dep. João Leopoldo Jacomel com Estrada Ecológica - Pinhais, PR",
    latitude: -25.4404411,
    longitude: -49.1443666,
    rating: null,
    totalAvaliacoes: 0,
    origem: "seed_pinhais",
    buscaOrigem: "Parque das Aguas Pinhais",
    ativo: true,
    curadoriaManual: false,
    potencialTuristico: 88,
    tags: ["lazer", "fotografia", "caminhada", "familia"],
    resumo: "Parque urbano associado a lazer, caminhadas, fotos e eventos municipais.",
    googleMapsUri: "https://www.google.com/maps/search/?api=1&query=Parque%20das%20Aguas%20Pinhais",
    mapPosition: estimatePinhaisMapPosition(-25.4404411, -49.1443666),
  },
  {
    id: "pinhais-boulevard-parque",
    nome: "Espaco Boulevard do Parque das Aguas",
    categoriaApp: "eventos",
    categoriasSecundarias: ["parques", "gastronomia"],
    endereco: "Estrada Ecológica de Pinhais, 12 - Parque das Águas, Pinhais, PR",
    latitude: -25.442221,
    longitude: -49.1475179,
    rating: null,
    totalAvaliacoes: 0,
    origem: "seed_pinhais",
    buscaOrigem: "Espaco Boulevard Parque das Aguas Pinhais",
    ativo: true,
    curadoriaManual: false,
    potencialTuristico: 82,
    tags: ["eventos", "convivencia", "gastronomia"],
    resumo: "Ponto de apoio para eventos, convivencia e consumo local no entorno do parque.",
    googleMapsUri: "https://www.google.com/maps/search/?api=1&query=Espaco%20Boulevard%20Parque%20das%20Aguas%20Pinhais",
    mapPosition: estimatePinhaisMapPosition(-25.442221, -49.1475179),
  },
  {
    id: "pinhais-feira-maria-antonieta",
    nome: "Feira livre da Praca Maria Antonieta",
    categoriaApp: "feiras_livres",
    categoriasSecundarias: ["artesanato", "gastronomia"],
    endereco: "Praca Maria Antonieta - Pinhais, PR",
    latitude: -25.4414149,
    longitude: -49.160252,
    rating: null,
    totalAvaliacoes: 0,
    origem: "curadoria_manual",
    buscaOrigem: "feira livre Pinhais PR",
    ativo: true,
    curadoriaManual: true,
    potencialTuristico: 86,
    tags: ["quarta-feira", "13h as 19h", "gastronomia", "artesanato"],
    resumo: "Feira divulgada localmente com gastronomia, artesanato e produtos industrializados.",
    googleMapsUri: "https://www.google.com/maps/search/?api=1&query=Praca%20Maria%20Antonieta%20Pinhais",
    mapPosition: estimatePinhaisMapPosition(-25.4414149, -49.160252),
  },
  {
    id: "pinhais-praca-maria-antonieta",
    nome: "Praca Maria Antonieta",
    categoriaApp: "pontos_turisticos",
    categoriasSecundarias: ["parques", "feiras_livres"],
    endereco: "Praca Maria Antonieta - Pinhais, PR",
    latitude: -25.4414149,
    longitude: -49.160252,
    rating: null,
    totalAvaliacoes: 0,
    origem: "seed_pinhais",
    buscaOrigem: "Praca Maria Antonieta Pinhais",
    ativo: true,
    curadoriaManual: false,
    potencialTuristico: 76,
    tags: ["praca", "feiras", "bairro"],
    resumo: "Praca usada como referencia para encontro, comercio local e feira livre.",
    googleMapsUri: "https://www.google.com/maps/search/?api=1&query=Praca%20Maria%20Antonieta%20Pinhais",
    mapPosition: estimatePinhaisMapPosition(-25.4414149, -49.160252),
  },
  {
    id: "pinhais-bosque-municipal",
    nome: "Bosque Municipal",
    categoriaApp: "parques",
    categoriasSecundarias: ["pontos_turisticos"],
    endereco: "Av. 24 de Maio, s/n - Centro, Pinhais, PR",
    latitude: -25.4406172,
    longitude: -49.1941428,
    rating: null,
    totalAvaliacoes: 0,
    origem: "seed_pinhais",
    buscaOrigem: "Bosque Municipal Pinhais",
    ativo: true,
    curadoriaManual: false,
    potencialTuristico: 74,
    tags: ["natureza", "familia", "caminhada"],
    resumo: "Area verde para compor roteiros de lazer junto aos parques e pracas da cidade.",
    googleMapsUri: "https://www.google.com/maps/search/?api=1&query=Bosque%20Municipal%20Pinhais",
    mapPosition: estimatePinhaisMapPosition(-25.4406172, -49.1941428),
  },
  {
    id: "pinhais-artesanato-local",
    nome: "Lojas e atelies de artesanato",
    categoriaApp: "artesanato",
    categoriasSecundarias: ["comercio_local"],
    endereco: "Pinhais, PR",
    latitude: -25.4325,
    longitude: -49.1931,
    rating: null,
    totalAvaliacoes: 0,
    origem: "curadoria_manual",
    buscaOrigem: "loja de artesanato Pinhais",
    ativo: true,
    curadoriaManual: true,
    potencialTuristico: 69,
    tags: ["artesanato", "presentes", "economia criativa"],
    resumo: "Agrupamento inicial para cadastrar lojas, atelies e produtores artesanais encontrados pela curadoria.",
    googleMapsUri: "https://www.google.com/maps/search/?api=1&query=artesanato%20em%20Pinhais%20PR",
    mapVerified: false,
    mapPosition: { x: 50, y: 55 },
  },
  {
    id: "pinhais-bordados",
    nome: "Bordados e producao manual",
    categoriaApp: "bordados",
    categoriasSecundarias: ["artesanato", "comercio_local"],
    endereco: "Pinhais, PR",
    latitude: -25.4325,
    longitude: -49.1931,
    rating: null,
    totalAvaliacoes: 0,
    origem: "curadoria_manual",
    buscaOrigem: "bordados em Pinhais PR",
    ativo: true,
    curadoriaManual: true,
    potencialTuristico: 68,
    tags: ["bordados", "manual", "empreendedores locais"],
    resumo: "Categoria de curadoria para produtoras e pequenos negocios que nem sempre aparecem bem no Google Maps.",
    googleMapsUri: "https://www.google.com/maps/search/?api=1&query=bordados%20em%20Pinhais%20PR",
    mapVerified: false,
    mapPosition: { x: 45, y: 61 },
  },
  {
    id: "pinhais-gastronomia-parque",
    nome: "Restaurantes e cafes perto do Parque das Aguas",
    categoriaApp: "gastronomia",
    categoriasSecundarias: ["comercio_local"],
    endereco: "Entorno do Parque das Aguas - Pinhais, PR",
    latitude: -25.4245,
    longitude: -49.1912,
    rating: null,
    totalAvaliacoes: 0,
    origem: "seed_pinhais",
    buscaOrigem: "restaurantes perto do Parque das Aguas Pinhais",
    ativo: true,
    curadoriaManual: false,
    potencialTuristico: 72,
    tags: ["restaurantes", "cafes", "parque"],
    resumo: "Busca ancora para conectar lazer no parque com consumo gastronomico local.",
    googleMapsUri: "https://www.google.com/maps/search/?api=1&query=restaurantes%20perto%20do%20Parque%20das%20Aguas%20Pinhais",
    mapVerified: false,
    mapPosition: { x: 66, y: 43 },
  },
  {
    id: "pinhais-comercio-presentes",
    nome: "Comercio local e presentes artesanais",
    categoriaApp: "comercio_local",
    categoriasSecundarias: ["artesanato", "bordados"],
    endereco: "Pinhais, PR",
    latitude: -25.4325,
    longitude: -49.1931,
    rating: null,
    totalAvaliacoes: 0,
    origem: "curadoria_manual",
    buscaOrigem: "presentes artesanais Pinhais",
    ativo: true,
    curadoriaManual: true,
    potencialTuristico: 66,
    tags: ["presentes", "comercio", "producao manual"],
    resumo: "Base para cadastrar pequenos negocios que completam rotas de compra e lembrancas da cidade.",
    googleMapsUri: "https://www.google.com/maps/search/?api=1&query=presentes%20artesanais%20Pinhais",
    mapVerified: false,
    mapPosition: { x: 52, y: 64 },
  },
];
