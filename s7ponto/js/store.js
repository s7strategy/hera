/* ==========================================================================
   S7 PONTO — escolhe o armazém: Supabase de verdade ou demonstração local.
   O resto do app não sabe (nem precisa saber) qual dos dois está rodando.
   ========================================================================== */
import { IS_DEMO } from './config.js';
import { criaStoreDemo } from './store-demo.js';

export let store = null;

/** ?demo=1 na URL força a demonstração mesmo com Supabase configurado. */
export const demoForcada = () => new URLSearchParams(location.search).has('demo');

export async function iniciaStore() {
  if (IS_DEMO || demoForcada()) {
    store = criaStoreDemo();
  } else {
    const { criaStoreSupabase } = await import('./store-supabase.js');
    store = await criaStoreSupabase();
  }
  await store.init();
  return store;
}
