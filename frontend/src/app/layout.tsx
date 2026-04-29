import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { AppShell } from "@/components/app-shell";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Nexus Chat AI",
  description: "Painel administrativo Nexus Chat AI — VSA Tech",
  icons: {
    icon: "/icon.png",
    apple: "/apple-icon.png",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  userScalable: true,
  themeColor: "#0d0d10",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} antialiased`}
        suppressHydrationWarning
      >
        {/* Ambient Light Orbs — suaves, mais difusos pra reduzir saturação visual */}
        <div
          aria-hidden
          className="fixed top-[-150px] left-[-150px] w-[600px] h-[600px] bg-brand-primary/[0.08] blur-[120px] rounded-full pointer-events-none -z-10 animate-float"
        />
        <div
          aria-hidden
          className="fixed bottom-[-100px] right-[-100px] w-[500px] h-[500px] bg-brand-secondary/[0.08] blur-[120px] rounded-full pointer-events-none -z-10 animate-float"
          style={{ animationDelay: "2s" }}
        />
        <div
          aria-hidden
          className="fixed top-[30%] right-[35%] w-[350px] h-[350px] bg-brand-primary/[0.05] blur-[110px] rounded-full pointer-events-none -z-10 animate-pulse-slow"
        />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
