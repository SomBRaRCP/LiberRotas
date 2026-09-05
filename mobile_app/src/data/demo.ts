/**
 * Tipos e dados de demonstração usados pelas telas de Cupons e Feiras.
 *
 * Os tipos descrevem o formato esperado dos objetos e permitem que o
 * TypeScript detecte propriedades ausentes ou categorias inválidas. Os arrays
 * simulam dados que, em uma evolução do projeto, poderiam vir de uma API ou
 * do Firebase sem exigir mudanças grandes nos componentes visuais.
 */
export type Coupon = {
  id: string;
  title: string;
  validUntil: string;
  badge: string;
  category: "Todos" | "Alim." | "Arte";
};

export type Fair = {
  id: string;
  title: string;
  category: string;
  detail: string;
};

export type PublicDemoProfile = {
  id: string;
  role: "entrepreneur" | "visitor";
  name: string;
  city: string;
  category: string;
  bio: string;
  initials: string;
  avatarColor: string;
  interests: string[];
};

export type MarketPost = {
  id: string;
  authorId: string;
  seller: string;
  category: "Alim." | "Arte";
  title: string;
  city: string;
  date: string;
  imageKind: "photo" | "placeholder";
};

export type Product = {
  id: string;
  ownerId: string;
  title: string;
  price: string;
  description: string;
  category: string;
};

// Conteúdo inicial iterado com map/filter na tela de cupons.
export const coupons: Coupon[] = [
  { id: "FEITUR-001", title: "10% OFF na Feijoada", validUntil: "31/05/2026", badge: "10%", category: "Alim." },
  { id: "FEITUR-002", title: "Tour em Dobro", validUntil: "30/06/2026", badge: "1+1", category: "Todos" },
  { id: "FEITUR-003", title: "15% OFF Artesanato", validUntil: "15/05/2026", badge: "15%", category: "Arte" },
  { id: "FEITUR-004", title: "Entrada Gratuita Expo", validUntil: "Utilizado", badge: "Grátis", category: "Todos" },
];

// Ranking inicial exibido e filtrado na tela de exploração de feiras.
export const fairs: Fair[] = [
  { id: "1", title: "Rota cultural guiada", category: "Guias locais", detail: "Centro Histórico · Domingo, 10h" },
  { id: "2", title: "Café artesanal", category: "Gastronomia", detail: "Praça Central · Sábado, 9h" },
  { id: "3", title: "Oficina de cerâmica", category: "Artesanato", detail: "Casa da Cultura · Sexta, 14h" },
  { id: "4", title: "Feira economia solidária", category: "Gastronomia", detail: "Parque Municipal · Domingo, 8h" },
  { id: "5", title: "Passeio histórico", category: "Guias locais", detail: "Largo da Ordem · Sábado, 15h" },
];

// Perfis e vitrines simulam outros usuarios ate existir backend/Firebase.
export const demoProfiles: PublicDemoProfile[] = [
  {
    id: "seller-bf",
    role: "entrepreneur",
    name: "B.F. Agroecologia",
    city: "Curitiba - PR",
    category: "Horta e Agroecologia",
    bio: "Produtor familiar com alimentos de epoca, manejo agroecologico e entrega nas feiras parceiras.",
    initials: "BF",
    avatarColor: "#DDF5C9",
    interests: ["Gastronomia", "Feiras locais"],
  },
  {
    id: "seller-atelie-ana",
    role: "entrepreneur",
    name: "Atelie da Ana",
    city: "Morretes - PR",
    category: "Artesanato",
    bio: "Pecas de ceramica feitas a mao, inspiradas na cultura local e em roteiros historicos.",
    initials: "AA",
    avatarColor: "#FFE2C7",
    interests: ["Artesanato", "Cultura local"],
  },
  {
    id: "visitor-maria",
    role: "visitor",
    name: "Maria Santos",
    city: "Pinhais - PR",
    category: "Visitante LiberRotas",
    bio: "Visitante interessada em roteiros culturais, gastronomia local e eventos de fim de semana.",
    initials: "MS",
    avatarColor: "#E1E9FF",
    interests: ["Gastronomia", "Guias locais"],
  },
];

export const marketPosts: MarketPost[] = [
  {
    id: "melancia",
    authorId: "seller-bf",
    seller: "B.F. Agroecologia",
    category: "Alim.",
    title: "Melancia agroecologica",
    city: "Curitiba",
    date: "13/04/2026",
    imageKind: "photo",
  },
  {
    id: "ceramica",
    authorId: "seller-atelie-ana",
    seller: "Atelie da Ana",
    category: "Arte",
    title: "Ceramica inspirada na cultura local",
    city: "Morretes",
    date: "25/04/2026",
    imageKind: "placeholder",
  },
];

export const demoProducts: Product[] = [
  {
    id: "produto-rota-comunitaria",
    ownerId: "local-empreendedor",
    title: "Roteiro comunitario guiado",
    price: "R$ 45,00",
    description: "Passeio de 2 horas com historias do bairro, paradas culturais e indicacao de feiras locais.",
    category: "Experiencia",
  },
  {
    id: "produto-kit-local",
    ownerId: "local-empreendedor",
    title: "Kit lembranca LiberRotas",
    price: "R$ 32,00",
    description: "Conjunto com mapa afetivo, postal artesanal e cupom para feira parceira.",
    category: "Turismo",
  },
  {
    id: "produto-melancia",
    ownerId: "seller-bf",
    title: "Melancia agroecologica",
    price: "R$ 18,00",
    description: "Fruta de epoca produzida sem agrotoxicos, retirada na feira de domingo.",
    category: "Alimentos",
  },
  {
    id: "produto-cesta-verde",
    ownerId: "seller-bf",
    title: "Cesta verde da semana",
    price: "R$ 38,00",
    description: "Selecao de hortalicas frescas conforme colheita da semana.",
    category: "Alimentos",
  },
  {
    id: "produto-vaso",
    ownerId: "seller-atelie-ana",
    title: "Vaso ceramico pequeno",
    price: "R$ 55,00",
    description: "Peca unica modelada a mao e queimada em baixa temperatura.",
    category: "Artesanato",
  },
  {
    id: "produto-oficina",
    ownerId: "seller-atelie-ana",
    title: "Oficina de ceramica",
    price: "R$ 80,00",
    description: "Vivencia introdutoria para visitantes criarem uma pequena peca artesanal.",
    category: "Experiencia",
  },
];
