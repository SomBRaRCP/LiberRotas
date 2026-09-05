import {
  googlePlacesNearbySearches,
  googlePlacesTextSearches,
  PINHAIS_CENTER,
  PINHAIS_RADIUS_METERS,
  type PinhaisCategory,
  type PinhaisPlace,
} from "@/data/pinhais";

declare const process: {
  env: {
    EXPO_PUBLIC_GOOGLE_PLACES_API_KEY?: string;
  };
};

type GooglePlacePhoto = {
  name?: string;
  widthPx?: number;
  heightPx?: number;
};

type GooglePlace = {
  id?: string;
  displayName?: {
    text?: string;
  };
  formattedAddress?: string;
  location?: {
    latitude?: number;
    longitude?: number;
  };
  rating?: number;
  userRatingCount?: number;
  types?: string[];
  primaryType?: string;
  googleMapsUri?: string;
  photos?: GooglePlacePhoto[];
};

type GooglePlacesResponse = {
  places?: GooglePlace[];
};

type GooglePlacesOptions = {
  apiKey?: string;
};

const FIELD_MASK = [
  "places.id",
  "places.displayName",
  "places.formattedAddress",
  "places.location",
  "places.rating",
  "places.userRatingCount",
  "places.types",
  "places.primaryType",
  "places.googleMapsUri",
  "places.photos",
].join(",");

const GOOGLE_PLACES_API_KEY = process.env.EXPO_PUBLIC_GOOGLE_PLACES_API_KEY;

function getApiKey(options?: GooglePlacesOptions) {
  const apiKey = options?.apiKey || GOOGLE_PLACES_API_KEY;
  if (!apiKey) {
    throw new Error("Configure EXPO_PUBLIC_GOOGLE_PLACES_API_KEY ou chame este service por um backend com chave protegida.");
  }
  return apiKey;
}

async function postPlaces(endpoint: "places:searchText" | "places:searchNearby", body: object, options?: GooglePlacesOptions) {
  const response = await fetch(`https://places.googleapis.com/v1/${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Goog-Api-Key": getApiKey(options),
      "X-Goog-FieldMask": FIELD_MASK,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Erro Google Places ${endpoint}: ${errorText}`);
  }

  return (await response.json()) as GooglePlacesResponse;
}

function slugify(value: string) {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

function estimateMapPosition(latitude: number | null, longitude: number | null) {
  if (latitude === null || longitude === null) return { x: 50, y: 50 };

  const west = -49.23;
  const east = -49.16;
  const north = -25.405;
  const south = -25.462;
  const x = ((longitude - west) / (east - west)) * 100;
  const y = ((latitude - north) / (south - north)) * 100;

  return {
    x: Math.max(8, Math.min(92, x)),
    y: Math.max(12, Math.min(88, y)),
  };
}

function calcularPotencialTuristico(place: GooglePlace, categoriaApp: PinhaisCategory) {
  let score = 30;
  const rating = place.rating || 0;
  const avaliacoes = place.userRatingCount || 0;
  const temFoto = Array.isArray(place.photos) && place.photos.length > 0;

  if (categoriaApp === "pontos_turisticos") score += 25;
  if (categoriaApp === "parques") score += 20;
  if (categoriaApp === "feiras_livres") score += 20;
  if (categoriaApp === "artesanato") score += 15;
  if (categoriaApp === "bordados") score += 15;
  if (categoriaApp === "eventos") score += 20;
  if (categoriaApp === "gastronomia") score += 10;
  if (categoriaApp === "comercio_local") score += 10;

  if (rating >= 4.7) score += 20;
  else if (rating >= 4.3) score += 15;
  else if (rating >= 4.0) score += 10;

  if (avaliacoes >= 1000) score += 20;
  else if (avaliacoes >= 300) score += 15;
  else if (avaliacoes >= 50) score += 10;

  if (temFoto) score += 5;

  return Math.min(score, 100);
}

function normalizarPlace(place: GooglePlace, categoriaApp: PinhaisCategory, buscaOrigem: string): PinhaisPlace {
  const nome = place.displayName?.text || "Local sem nome";
  const latitude = place.location?.latitude ?? PINHAIS_CENTER.latitude;
  const longitude = place.location?.longitude ?? PINHAIS_CENTER.longitude;

  return {
    id: place.id ? `google-${place.id}` : `google-${slugify(`${nome}-${buscaOrigem}`)}`,
    googlePlaceId: place.id,
    nome,
    categoriaApp,
    endereco: place.formattedAddress || "Pinhais, PR",
    latitude,
    longitude,
    rating: place.rating ?? null,
    totalAvaliacoes: place.userRatingCount || 0,
    origem: "google_places",
    buscaOrigem,
    ativo: true,
    curadoriaManual: false,
    potencialTuristico: calcularPotencialTuristico(place, categoriaApp),
    tags: [place.primaryType, ...(place.types || [])].filter((tag): tag is string => Boolean(tag)),
    resumo: "Local encontrado pelo Google Places para curadoria do mapa turistico de Pinhais.",
    googleMapsUri: place.googleMapsUri,
    mapPosition: estimateMapPosition(latitude, longitude),
  };
}

export async function textSearchPinhais(textQuery: string, categoriaApp: PinhaisCategory, options?: GooglePlacesOptions) {
  const data = await postPlaces(
    "places:searchText",
    {
      textQuery,
      languageCode: "pt-BR",
      regionCode: "BR",
      locationBias: {
        circle: {
          center: PINHAIS_CENTER,
          radius: PINHAIS_RADIUS_METERS,
        },
      },
    },
    options,
  );

  return (data.places || []).map((place) => normalizarPlace(place, categoriaApp, textQuery));
}

export async function nearbySearchPinhais(includedTypes: string[], categoriaApp: PinhaisCategory, options?: GooglePlacesOptions) {
  const data = await postPlaces(
    "places:searchNearby",
    {
      includedTypes,
      maxResultCount: 20,
      languageCode: "pt-BR",
      locationRestriction: {
        circle: {
          center: PINHAIS_CENTER,
          radius: PINHAIS_RADIUS_METERS,
        },
      },
    },
    options,
  );

  return (data.places || []).map((place) => normalizarPlace(place, categoriaApp, includedTypes.join(",")));
}

export async function descobrirPontosPinhais(options?: GooglePlacesOptions) {
  const resultados: PinhaisPlace[] = [];

  for (const busca of googlePlacesTextSearches) {
    const encontrados = await textSearchPinhais(busca.query, busca.categoria, options);
    resultados.push(...encontrados);
  }

  for (const busca of googlePlacesNearbySearches) {
    const encontrados = await nearbySearchPinhais(busca.types, busca.categoria, options);
    resultados.push(...encontrados);
  }

  return removerDuplicadosPorPlaceId(resultados);
}

export function removerDuplicadosPorPlaceId(lista: PinhaisPlace[]) {
  const mapa = new Map<string, PinhaisPlace>();

  for (const item of lista) {
    const dedupeKey = item.googlePlaceId || item.id;
    const existente = mapa.get(dedupeKey);

    if (!existente || item.potencialTuristico > existente.potencialTuristico) {
      mapa.set(dedupeKey, item);
    }
  }

  return Array.from(mapa.values()).sort((left, right) => right.potencialTuristico - left.potencialTuristico);
}
