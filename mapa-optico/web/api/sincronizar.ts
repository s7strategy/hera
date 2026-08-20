/**
 * Ponte entre o botão "Sincronizar" e o robô do GitHub Actions.
 *
 * POR QUE ISTO EXISTE. O pipeline é Python e lê o CNES em formato .DBC — nada
 * disso roda num navegador nem numa edge function. E o token que dispara o
 * workflow não pode ir para o navegador: quem tem o token pode rodar qualquer
 * coisa no repositório. Então o token fica aqui, numa função serverless, e o
 * navegador só consegue pedir exatamente as duas coisas abaixo.
 *
 * GET   → estado da última execução (não dispara nada)
 * POST  → dispara uma execução com os parâmetros escolhidos na tela
 *
 * Variáveis de ambiente na Vercel:
 *   GITHUB_TOKEN   token fine-grained com permissão de Actions:write NESTE repo
 *                  e em mais nada. Sem ele a rota responde 501 e a tela explica
 *                  o que falta, em vez de fingir que sincronizou.
 *   GITHUB_REPO    "dono/repositorio"  (padrão: s7strategy/hera)
 *   GITHUB_REF     branch onde o workflow roda (padrão: main)
 */

const ARQUIVO_WORKFLOW = "mapa-optico-pipeline.yml";
const API = "https://api.github.com";

interface Disparo {
  ufs?: string;
  com_places?: boolean;
  com_osrm?: boolean;
  refresh?: boolean;
}

function config() {
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || "s7strategy/hera";
  const ref = process.env.GITHUB_REF_SINCRONIZACAO || "main";
  return { token, repo, ref };
}

async function github(caminho: string, token: string, init?: RequestInit) {
  return fetch(`${API}${caminho}`, {
    ...init,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
}

const json = (corpo: unknown, status = 200) =>
  new Response(JSON.stringify(corpo), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });

export const config_vercel = { runtime: "edge" };

export default async function handler(req: Request): Promise<Response> {
  const { token, repo, ref } = config();

  if (!token) {
    // Falta de configuração não é erro do usuário: a tela precisa poder dizer
    // exatamente o que falta e quem resolve.
    return json(
      {
        configurado: false,
        motivo:
          "Falta a variável GITHUB_TOKEN no projeto da Vercel. Gere um token fine-grained com " +
          "permissão Actions: read and write apenas neste repositório e adicione em " +
          "Settings → Environment Variables.",
      },
      501,
    );
  }

  if (req.method === "GET") {
    const r = await github(
      `/repos/${repo}/actions/workflows/${ARQUIVO_WORKFLOW}/runs?per_page=5`,
      token,
    );
    if (!r.ok) {
      return json({ configurado: true, erro: `GitHub respondeu ${r.status}` }, 502);
    }
    const dados = (await r.json()) as { workflow_runs?: Record<string, unknown>[] };
    const execucoes = (dados.workflow_runs ?? []).map((x) => ({
      id: x.id,
      estado: x.status, // queued | in_progress | completed
      resultado: x.conclusion, // success | failure | cancelled | null
      criado_em: x.created_at,
      atualizado_em: x.updated_at,
      url: x.html_url,
    }));
    return json({ configurado: true, execucoes });
  }

  if (req.method === "POST") {
    let corpo: Disparo = {};
    try {
      corpo = (await req.json()) as Disparo;
    } catch {
      corpo = {};
    }

    // A tela manda o que quer; aqui a gente decide o que é aceitável. O padrão
    // de todo campo é o mais barato — Places desligado, cache ligado.
    const inputs = {
      ufs: (corpo.ufs ?? "SC").slice(0, 200),
      com_places: String(corpo.com_places === true),
      com_osrm: String(corpo.com_osrm !== false),
      refresh: String(corpo.refresh === true),
    };

    const r = await github(
      `/repos/${repo}/actions/workflows/${ARQUIVO_WORKFLOW}/dispatches`,
      token,
      { method: "POST", body: JSON.stringify({ ref, inputs }) },
    );

    if (r.status !== 204) {
      const texto = await r.text();
      return json({ ok: false, erro: `GitHub respondeu ${r.status}: ${texto.slice(0, 300)}` }, 502);
    }
    return json({ ok: true, inputs });
  }

  return json({ erro: "método não suportado" }, 405);
}
