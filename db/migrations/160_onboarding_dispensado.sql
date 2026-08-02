-- "Pular pra agora" do onboarding passa a ser lembrado.
--
-- A tela `/onboarding` (4 passos: doc da empresa, conexão, agente, atendente)
-- promete em dois lugares que dá pra sair dela: o texto do topo — "Você pode
-- pular e voltar aqui depois quando quiser" — e o botão "Pular pra agora" no
-- rodapé. Nenhum dos dois era verdade: o botão é um link pro dashboard e não
-- gravava nada, então a próxima visita a "/" caía no wizard de novo. Empresa
-- que legitimamente não quer completar os 4 passos ficava presa vendo a mesma
-- tela em todo login.
--
-- Guardar na empresa (e não em cookie) é o que cumpre o "não aparecer mais":
-- atravessa navegador, máquina e usuário. É coerente com o resto — os 4 checks
-- já medem estado da empresa, não do usuário.
--
-- NULL = nunca dispensado (é o default, e mantém o comportamento guiado pra
-- quem acabou de entrar). Preenchido = o dono decidiu sair do wizard; "/"
-- passa a mandar direto pro painel. Completar os 4 passos continua valendo
-- por si só, independente desta coluna.
--
-- Sem bloco de RLS: `empresa` já tem ENABLE + FORCE + isolamento por tenant
-- desde a Sprint A.2 (migs 096/100-103), e ALTER TABLE não movimenta linha —
-- por isso também não precisa do `app.bypass_rls`.

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS onboarding_dispensado_at TIMESTAMPTZ;

COMMENT ON COLUMN empresa.onboarding_dispensado_at IS
    'Quando alguém clicou em "Pular" no wizard de onboarding. NULL = nunca '
    'dispensado. Preenchido faz a raiz "/" ir direto pro painel mesmo com os '
    '4 passos incompletos; a tela segue acessível pelo menu.';
