import type { Metadata, Viewport } from "next";
import { Fraunces, Geist, Geist_Mono } from "next/font/google";
import { cookies } from "next/headers";
import "./globals.css";
import { SiteShell } from "@/components/site-shell";
import { getHealthStatus } from "@/lib/api";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/auth";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Serifa display só para títulos — eco da elegância do logo Lu Milhas.
const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["opsz"],
});

export const metadata: Metadata = {
  title: "Painel da Malu · Lu Milhas",
  description: "Painel de insights da assistente virtual Malu",
  appleWebApp: {
    capable: true,
    title: "Malu",
    statusBarStyle: "default",
  },
  icons: {
    icon: [
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon-180.png", sizes: "180x180" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#0e1f3b",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  // Chrome/Android: encolhe o layout (não só o viewport visual) quando o
  // teclado abre — o compositor do chat (dvh) fica visível acima dele.
  interactiveWidget: "resizes-content",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const healthStatus = await getHealthStatus();
  const jar = await cookies();
  const session = await verifySessionToken(jar.get(SESSION_COOKIE)?.value);

  return (
    <html
      lang="pt-BR"
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <SiteShell status={healthStatus} userName={session?.name ?? null}>
          {children}
        </SiteShell>
      </body>
    </html>
  );
}
