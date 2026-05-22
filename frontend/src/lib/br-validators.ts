/**
 * Validadores brasileiros (CPF, CNPJ, CEP) — implementação local sem
 * dependência externa. Algoritmos padrão Receita Federal.
 */

/** Remove todos os caracteres não-numéricos. */
export function onlyDigits(value: string): string {
  return value.replace(/\D+/g, "");
}

/** Valida CPF (11 dígitos + 2 dígitos verificadores). */
export function isValidCPF(input: string): boolean {
  const cpf = onlyDigits(input);
  if (cpf.length !== 11) return false;
  // Rejeita sequências repetidas (000.000.000-00, etc)
  if (/^(\d)\1+$/.test(cpf)) return false;

  // 1º dígito verificador
  let sum = 0;
  for (let i = 0; i < 9; i++) sum += parseInt(cpf[i], 10) * (10 - i);
  let dv = 11 - (sum % 11);
  if (dv >= 10) dv = 0;
  if (dv !== parseInt(cpf[9], 10)) return false;

  // 2º dígito verificador
  sum = 0;
  for (let i = 0; i < 10; i++) sum += parseInt(cpf[i], 10) * (11 - i);
  dv = 11 - (sum % 11);
  if (dv >= 10) dv = 0;
  return dv === parseInt(cpf[10], 10);
}

/** Valida CNPJ (14 dígitos + 2 dígitos verificadores). */
export function isValidCNPJ(input: string): boolean {
  const cnpj = onlyDigits(input);
  if (cnpj.length !== 14) return false;
  if (/^(\d)\1+$/.test(cnpj)) return false;

  const calcDV = (length: number): number => {
    const weights = length === 12
      ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
      : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    let sum = 0;
    for (let i = 0; i < length; i++) {
      sum += parseInt(cnpj[i], 10) * weights[i];
    }
    const mod = sum % 11;
    return mod < 2 ? 0 : 11 - mod;
  };

  return (
    calcDV(12) === parseInt(cnpj[12], 10) &&
    calcDV(13) === parseInt(cnpj[13], 10)
  );
}

/** Valida CPF OU CNPJ. */
export function isValidCPFOrCNPJ(input: string): boolean {
  const digits = onlyDigits(input);
  if (digits.length === 11) return isValidCPF(digits);
  if (digits.length === 14) return isValidCNPJ(digits);
  return false;
}

/** Formata CPF (000.000.000-00). */
export function formatCPF(input: string): string {
  const d = onlyDigits(input).slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

/** Formata CNPJ (00.000.000/0000-00). */
export function formatCNPJ(input: string): string {
  const d = onlyDigits(input).slice(0, 14);
  if (d.length <= 2) return d;
  if (d.length <= 5) return `${d.slice(0, 2)}.${d.slice(2)}`;
  if (d.length <= 8) return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5)}`;
  if (d.length <= 12)
    return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8)}`;
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
}

/** Auto-detecta CPF vs CNPJ e formata. */
export function formatCPFOrCNPJ(input: string): string {
  const d = onlyDigits(input);
  if (d.length <= 11) return formatCPF(d);
  return formatCNPJ(d);
}

/** Formata CEP (00000-000). */
export function formatCEP(input: string): string {
  const d = onlyDigits(input).slice(0, 8);
  if (d.length <= 5) return d;
  return `${d.slice(0, 5)}-${d.slice(5)}`;
}

/** Slug URL-friendly a partir de qualquer texto BR. */
export function slugify(input: string): string {
  return input
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")  // remove acentos (combining marks)
    .replace(/[^a-z0-9\s-]/g, "")     // remove caracteres não-permitidos
    .trim()
    .replace(/\s+/g, "-")              // espaços viram hífen
    .replace(/-+/g, "-")               // hífens duplicados
    .replace(/^-|-$/g, "")             // hífens nas pontas
    .slice(0, 100);
}

/** Resultado do lookup ViaCEP. */
export interface CepLookupResult {
  cep: string;
  logradouro: string;
  bairro: string;
  localidade: string;  // cidade
  uf: string;
  complemento?: string;
}

/**
 * Lookup CEP via API pública ViaCEP. Retorna null se inválido / não achado.
 * Não requer auth. Time-out ~5s pra UI não travar.
 */
export async function lookupCep(cep: string): Promise<CepLookupResult | null> {
  const d = onlyDigits(cep);
  if (d.length !== 8) return null;
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    const resp = await fetch(`https://viacep.com.br/ws/${d}/json/`, {
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    if (!resp.ok) return null;
    const data = await resp.json();
    if (data.erro) return null;
    return {
      cep: data.cep,
      logradouro: data.logradouro || "",
      bairro: data.bairro || "",
      localidade: data.localidade || "",
      uf: data.uf || "",
      complemento: data.complemento || undefined,
    };
  } catch {
    return null;
  }
}
