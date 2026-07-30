/**
 * Marca da empresa exibida no topo da sidebar (white-label).
 *
 * Módulo neutro porque o tipo é usado tanto pelo layout (Server Component) que
 * resolve a empresa ativa quanto pelo shell (Client Component).
 */
export interface SidebarBrand {
  nome: string;
  logo_path: string | null;
}
