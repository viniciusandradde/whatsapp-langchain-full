import { NextRequest, NextResponse } from "next/server";
import { cookies, headers } from "next/headers";

import { auth } from "@/lib/auth";

/**
 * Proxy de ENVIO de mídia: composer do painel → FastAPI
 * `/atendimentos/{id}/responder-midia` (nota de voz gravada, foto, documento).
 *
 * Por que Route Handler e não Server Action: Server Action tem corpo de 1 MB
 * por padrão (`next.config.ts` não define `bodySizeLimit`), e um PDF de 3 MB
 * ou um vídeo falharia antes de chegar à API. Aqui o multipart atravessa em
 * stream; o teto é o `MIDIA_MAX_BYTES` (16 MB) da API.
 *
 * Mesmo desenho do GET ao lado (`[mensagemId]/route.ts`): autentica pelo
 * cookie do Better Auth e injeta service token + identidade — o token nunca
 * chega ao navegador (ADR-003).
 */
export const dynamic = "force-dynamic";

const apiUrl = () => process.env.INTERNAL_API_URL || "http://localhost:8000";
const internalToken = () => process.env.INTERNAL_SERVICE_TOKEN || "";
const ACTIVE_EMPRESA_COOKIE = "active_empresa_id";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ atendimentoId: string }> }
): Promise<Response> {
  const { atendimentoId } = await context.params;
  const id = Number(atendimentoId);
  if (!Number.isFinite(id) || id <= 0) {
    return NextResponse.json({ error: "Atendimento inválido." }, { status: 400 });
  }

  try {
    const session = await auth.api.getSession({ headers: await headers() });
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Sessão expirada." }, { status: 401 });
    }
    const empresaId = (await cookies()).get(ACTIVE_EMPRESA_COOKIE)?.value;

    // O FormData é reconstruído (não repassado o body cru) pra que o boundary
    // do multipart seja o que o `fetch` de saída gera — o do navegador não
    // bate com o Content-Type que o Next expõe aqui.
    const entrada = await request.formData();
    const arquivo = entrada.get("arquivo");
    if (!(arquivo instanceof File) || arquivo.size === 0) {
      return NextResponse.json({ error: "Nenhum arquivo enviado." }, { status: 400 });
    }
    const saida = new FormData();
    saida.set("arquivo", arquivo, arquivo.name || "arquivo");
    const legenda = entrada.get("legenda");
    saida.set("legenda", typeof legenda === "string" ? legenda : "");

    const r = await fetch(`${apiUrl()}/api/atendimentos/${id}/responder-midia`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${internalToken()}`,
        "X-User-Id": session.user.id,
        ...(empresaId ? { "X-Empresa-Id": empresaId } : {}),
      },
      body: saida,
    });

    const texto = await r.text();
    if (!r.ok) {
      // A API devolve `{"detail": "…"}` legível (tipo não suportado, áudio
      // ilegível, conexão sem mídia, atendimento fechado). Repassa a frase,
      // nunca o corpo técnico.
      let detail = "Não foi possível enviar o arquivo.";
      try {
        const j = JSON.parse(texto) as { detail?: unknown };
        if (typeof j.detail === "string" && j.detail) detail = j.detail;
      } catch {
        // corpo não-JSON (proxy, 502…): fica a frase genérica
      }
      return NextResponse.json({ error: detail }, { status: r.status });
    }
    return new NextResponse(texto, {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("[proxy midia POST]", e);
    return NextResponse.json(
      { error: "Não foi possível enviar o arquivo." },
      { status: 500 }
    );
  }
}
