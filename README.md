<div align="center">

# ⚡ El Gravador 18 Pro Max

**Automação visual rápida para Windows — grave, edite e execute tarefas repetitivas sem precisar programar.**

[![Baixar Última Versão](https://img.shields.io/badge/Download-Última_Versão_(Windows_x64)-0d9488?style=for-the-badge&logo=windows)](https://github.com/wolly0x/el-gravador/releases/latest)
[![Versão](https://img.shields.io/badge/Versão-3.0.4-1e293b?style=for-the-badge)](https://github.com/wolly0x/el-gravador/releases)

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

## 🆕 Novidades da v3.0.4

- **Modo Simulação mais claro e seguro:** banner verde fixo no topo do fluxo e botão principal exibindo **Simular** quando ativo, além de isolamento total no motor (sem carregar controle real de mouse/teclado durante simulações).
- **Execução real corrigida:** resolvido travamento ao alternar de **Simular** para **Executar** em modo real e adicionada detecção de janelas elevadas (Administrador/UAC) com orientação clara.
- **Multi-monitor e DPI aprimorados:** suporte a DPI Per-Monitor v2 no Windows, redimensionamento/enquadramento automático ao mover a janela entre telas com resoluções ou escalas diferentes (a partir de `820×540`) e HUD posicionado no monitor ativo.
- **Estabilidade do motor e scripts exportados:** `ESC`/`F8` injetados durante a automação não cancelam nem pausam o próprio fluxo, gravação com recorte preserva clique direito/duplo clique, pausa `F8` congela prazos corretamente, blocos desativados pulam todo o corpo, cache LRU de templates (64 itens), e scripts `.py` exportados com tratamento de `FailSafeException` e `ao_falhar="continuar"` em todos os passos.
- **Interface & empacotamento:** código CSS/JS modularizado, polling leve, proteção de `ESC` em modais não-fecháveis e inclusão de `LICENSE` e `THIRD-PARTY-NOTICES.txt` no instalador.

### Destaques anteriores (v3.0.3)

- **Interface & legibilidade:** nome padrão de novos projetos alterado para **`Projeto sem título`**, badge **`Não salvo`** reposicionado e alinhado opticamente ao texto, texto **"Salvo automaticamente"** com maior contraste, bloqueio de interação atrás de modais e botão **Testar som** restrito ao modo Dev.

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
