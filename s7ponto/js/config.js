/* ==========================================================================
   S7 PONTO — configuração
   Edite SOMENTE este arquivo para ligar o sistema no seu Supabase.
   Enquanto SUPABASE_URL estiver vazio, o app roda em MODO DEMONSTRAÇÃO
   (dados de mentira no próprio navegador, nada é enviado para lugar nenhum).
   ========================================================================== */

export const CONFIG = {
  // ---- Supabase (self-hosted na VPS) -------------------------------------
  // Ex.: 'https://supabase.s7strategy.com.br'  (sem barra no final)
  SUPABASE_URL: '',
  // Chave pública "anon" do projeto. Pode ficar no código: ela é pública por
  // desenho — quem protege os dados é o RLS do schema (ver schema.sql).
  SUPABASE_ANON_KEY: '',

  // Schema dedicado do projeto dentro do Postgres — é o nosso "workspace"
  // separado, sem misturar com nada que já exista no banco.
  DB_SCHEMA: 's7ponto',

  // A pessoa digita só o usuário ("maria"); o sistema completa por trás com
  // este domínio para falar com o Supabase Auth. Nunca é um e-mail real.
  EMAIL_DOMAIN: 's7ponto.local',

  // ---- Marca / formato ---------------------------------------------------
  BRAND: { name: 'S7 PONTO', owner: 'S7 Strategy' },
  LOCALE: 'pt-BR',
  CURRENCY: 'BRL',

  // ---- Comportamento -----------------------------------------------------
  // De quanto em quanto tempo lembrar de marcar troca de tarefa (minutos).
  // Só aparece para quem tem mais de uma tarefa liberada. 0 desliga.
  REMINDER_MINUTES: 45,
  // Turno esquecido aberto por mais de X horas vira alerta para o admin.
  LONG_SHIFT_HOURS: 14,
};

export const IS_DEMO = !CONFIG.SUPABASE_URL || !CONFIG.SUPABASE_ANON_KEY;
