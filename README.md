<div align="center">

# ⚡ El Gravador 18 Pro Max

**Automação visual rápida para Windows — grave, edite e execute tarefas repetitivas sem precisar programar.**

[![Baixar Última Versão](https://img.shields.io/badge/Download-Última_Versão_(Windows_x64)-0d9488?style=for-the-badge&logo=windows)](https://github.com/wolly0x/el-gravador/releases/latest)
[![Versão](https://img.shields.io/badge/Versão-3.0.3-1e293b?style=for-the-badge)](https://github.com/wolly0x/el-gravador/releases)

</div>

---

## ✨ O que ele faz

- **Gravação inteligente:** capture cliques, movimentos, arrastar, rolagem, atalhos e digitação no Windows.
- **Visão computacional (OpenCV):** aguarde elementos aparecerem ou sumirem na tela e clique automaticamente com precisão configurável.
- **Prévia visual na tela:** veja exatamente onde cada ação vai clicar antes de executar, além de copiar e colar coordenadas entre passos com 1 clique.
- **Editor de fluxo visual:** reordene passos arrastando, duplique, desative temporariamente, agrupe em blocos de repetição ou teste em **Modo Simulação**.
- **Exportação para Python (`.py`):** gere scripts independentes a partir do seu fluxo visual quando precisar.
- **Atualizações automáticas:** novas versões chegam direto dentro do aplicativo.

---

## 🆕 Novidades da v3.0.3

- **Interface & legibilidade:** nome padrão de novos projetos alterado para **`Projeto sem título`**, badge **`Não salvo`** reposicionado e alinhado ao título, e texto **"Salvo automaticamente"** com maior contraste nos temas claro e escuro.
- **Bloqueio de fundo em modais:** janelas como *Licença e Sobre*, *Atalhos e dicas* e *Atualizações* agora bloqueiam cliques, foco e seleção de texto na tela ao fundo enquanto estiverem abertas.
- **Versão final mais limpa:** botão **Testar som** ocultado na versão de usuário (mantido apenas em modo Dev).

### Destaques anteriores (v3.0.2)

- **Motor nativo Windows & instalador mais leve:** substituição completa do `pynput` por hooks Win32 próprios, scripts `.py` exportados 100% independentes e instalador de **~55 MB**.
- **Gravação ABNT2 corrigida:** composição correta de acentos mortos (`á`, `ã`, `ê`, `ü`) e fim do travamento ao soltar `Shift` antes da letra.
- **Visual Windows & som relaxante:** fonte padrão `Segoe UI` (`15px`), som calmo ao iniciar (estilo felt-piano/harpa) com opção de ligar/desligar em Configurações.
- **Privacidade & segurança reforçadas:** textos digitados mascarados nos logs, screenshots de diagnóstico opt-in, CSP estrita, proteção contra *path traversal*, `FailSafe` inviolável e ferramentas de dev ocultas na versão final.

---

## 🚀 Como instalar (Windows 10 / 11)

1. Acesse a página [**Releases**](https://github.com/wolly0x/el-gravador/releases/latest) e baixe o arquivo `*-setup.exe` mais recente.
2. Execute o instalador.
   > **Nota do Windows SmartScreen:** durante a fase de testes, o instalador ainda não possui certificado digital pago. Se o Windows exibir *"O Windows protegeu o computador"*, clique em **Mais informações → Executar assim mesmo**.
3. Abra o **El Gravador 18 Pro Max** pelo Menu Iniciar ou Área de Trabalho.

---

## ⌨️ Atalhos principais

| Contexto | Atalho | Ação |
| :--- | :---: | :--- |
| **Gravação** | `F9` | Encerrar gravação e adicionar passos |
| **Gravação** | `F10` | Pausar / retomar gravação |
| **Gravação** | `ESC` | Descartar gravação atual |
| **Execução** | `F8` | Pausar / retomar execução |
| **Execução** | `ESC` | Interromper execução imediatamente |

---

## 🔄 Atualizações

O aplicativo verifica automaticamente novas versões ao iniciar. Você também pode conferir manualmente abrindo o menu **`...`** no canto superior direito e clicando em **Verificar atualizações…**.

---

<div align="center">
  <sub>© 2026 wolly0x · Todos os direitos reservados.</sub>
</div>
