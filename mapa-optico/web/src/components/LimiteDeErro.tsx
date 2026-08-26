/**
 * Isola um pedaco da tela para que ele nao derrube o resto.
 *
 * Existe por causa de um caso real: o MapLibre lanca uma excecao quando o
 * navegador nao entrega contexto WebGL (placa antiga, aceleracao desligada,
 * politica de TI). Sem este limite, essa excecao subia pela arvore do React,
 * desmontava a aplicacao inteira e a pagina ficava PRETA — inclusive a tabela
 * de municipios, que nao depende de mapa nenhum.
 *
 * Ranking sem mapa continua sendo um ranking. Mapa quebrado nao pode levar o
 * ranking junto.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  /** O que aparece no lugar quando o filho quebra. Recebe a mensagem do erro. */
  aoFalhar: (mensagem: string) => ReactNode;
  children: ReactNode;
}

interface Estado {
  erro: string | null;
}

export default class LimiteDeErro extends Component<Props, Estado> {
  state: Estado = { erro: null };

  static getDerivedStateFromError(erro: unknown): Estado {
    return { erro: erro instanceof Error ? erro.message : String(erro) };
  }

  componentDidCatch(erro: Error, info: ErrorInfo): void {
    // Vai para o console e nao para a tela: quem abre o app quer saber que o
    // mapa nao carregou, nao ler um stack trace.
    console.error("componente isolado falhou:", erro, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.erro !== null) return this.props.aoFalhar(this.state.erro);
    return this.props.children;
  }
}
