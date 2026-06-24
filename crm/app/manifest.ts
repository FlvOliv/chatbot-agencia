import type { MetadataRoute } from "next";

// Web App Manifest — torna o painel instalável ("Adicionar à Tela de Início").
// No iOS, instalar é o que DESTRAVA o web push (Safari só dispara push em PWA
// instalada). O Next injeta o <link rel="manifest"> automaticamente.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Painel da Malu · Lu Milhas",
    short_name: "Malu",
    description: "Atendimento e insights da assistente virtual Malu",
    start_url: "/conversas",
    display: "standalone",
    background_color: "#000000",
    theme_color: "#000000",
    lang: "pt-BR",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
    ],
  };
}
