import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import LimiteDeErro from "./components/LimiteDeErro";
import "./styles/global.css";

/**
 * O limite mais externo existe porque a alternativa e uma tela preta.
 *
 * Uma excecao nao tratada em qualquer ponto da arvore faz o React desmontar
 * tudo, e o que sobra e o fundo escuro do body — sem mensagem, sem pista,
 * indistinguivel de "o arquivo nao subiu direito". Ja aconteceu: o MapLibre
 * lancando por falta de WebGL levou junto a tabela inteira.
 *
 * Falhar dizendo o que houve custa dez linhas.
 */
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <LimiteDeErro
      aoFalhar={(erro) => (
        <div className="tela-erro">
          <h1>O aplicativo não conseguiu carregar</h1>
          <p>{erro}</p>
          <p className="tela-erro-dica">
            Se a mensagem citar WebGL ou contexto gráfico, o motivo é a aceleração de hardware
            estar desligada no navegador. Ligá-la nas configurações resolve; abrir esta página em
            outro navegador também.
          </p>
        </div>
      )}
    >
      <App />
    </LimiteDeErro>
  </React.StrictMode>,
);
