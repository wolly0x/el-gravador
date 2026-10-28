# El Gravador 18 Pro Max

Gravador e executor de automação para Windows: registra mouse e teclado, permite
editar o fluxo visualmente, usa imagens da tela como referência e gera um script
`.py` autocontido para rodar em outra máquina.

Esta é a reescrita modular do `AUTOMACAO_EL_GRAVADOR` antigo. O propósito é o
mesmo, mas agora as ações são dados (JSON), o núcleo é independente da interface
e o código gravado nunca é executado com `exec`.

---

## Requisitos

- Windows 10/11 (interface **PyWebView/WebView2**; automação real com
  `pyautogui`)
- Python 3.12 (3.10+ deve funcionar)
- Microsoft Edge WebView2 Runtime — já vem no Windows 11 e na maioria dos
  Windows 10 com Edge atualizado; se a janela não abrir, instale o runtime
  gratuito da Microsoft
- Permissão para controlar o computador (o Windows pode pedir confirmação em
  jogos/apps elevados; rode o app com o mesmo nível de privilégio do alvo)

## Instalação

O jeito mais simples é dar **duplo clique em `executar.bat`**. Na primeira
execução ele localiza o Python, cria a pasta `.venv`, instala as dependências
e abre o programa. As execuções seguintes reutilizam o ambiente e só conferem
o que estiver faltando.

Se preferir fazer manualmente:

```bat
cd AUTOMACAO_EL_GRAVADOR2
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

`pywebview` é a janela moderna. O Tkinter continua sendo usado **apenas no
processo interno** que mantém gravação, execução, HUD e captura de região; ele
não aparece para o usuário. O Tkinter já acompanha o Python oficial do Windows.

`opencv-python-headless` é obrigatório para busca por imagem com confiança
abaixo de 1.0. Sem ele, existe apenas a comparação exata (confiança ≥ 0.999).

## Como executar

```bat
executar.bat
```

A interface web abre em uma janela PyWebView. Os arquivos HTML/CSS/JS são
estáticos e não exigem Node.js, npm nem etapa de build.

Opções de linha de comando (funcionam com o `.bat` ou com `python main.py`):

```bat
executar.bat --projeto projetos\meu_fluxo.json
executar.bat --tk                                     :: interface Tk clássica
python main.py --importar "C:\caminho\parte1.py"      :: converte um script antigo
python main.py --importar "C:\caminho\pasta_scripts"   :: converte uma pasta inteira
python main.py --templates "C:\caminho\imagens_templates"
python main.py --sem-logs
```
```

O modo `--backend` é interno: o processo principal o inicia automaticamente.
Ele mantém um Tk oculto e se comunica por HTTP em `127.0.0.1` com um token
aleatório. Isso preserva o HUD nativo, o indicador de gravação e a seleção de
região já validados, sem colocar o loop do Tk no mesmo thread do WebView2.

A interface usa uma camada visual **Apple Glass** em HTML/CSS: vidro fosco,
cartões arredondados, tipografia Segoe UI, animações discretas e layout
responsivo. O tema é fixo no Apple Glass. O menu nativo foi substituído pelo
botão **⋯** no canto superior direito. Em **Configurações** você ajusta apenas
a fonte e a escala da interface; as demais opções ficam divididas entre
execução, imagem e gravação. As mudanças são aplicadas ao vivo.

Os dados ficam ao lado do código:

```
AUTOMACAO_EL_GRAVADOR2/
├── config.json            # criado no primeiro uso
├── imagens_templates/     # templates PNG + manifest.json
├── projetos/              # projetos .json e scripts .py gerados
├── logs/                  # log diário
├── ui/                    # launcher PyWebView + backend Tk oculto
└── ui_web/                # HTML, CSS e JavaScript da interface
```

## Fluxo de trabalho

### 1. Gravar (F9)

1. Abra o app e clique em **● Gravar (F9)**.
2. A janela principal é **escondida** e aparece uma faixa vermelha no canto da
   tela.
3. Use o mouse/teclado normalmente no programa que quer automatizar.
4. **F9** encerra e converte os eventos em passos.
   **F10** pausa/retoma. **ESC** descarta a gravação.

A conversão agrupa digitação em um passo só, trata backspace como edição do
texto, reconhece duplo clique (≤ 0.35 s e ≤ 6 px), arrasto e rolagem contínua.
Cliques podem virar coordenadas fixas ou, se **“Criar template em cada clique”**
estiver ligado, passos de imagem com coordenada de reserva.

### 2. Editar

- Duplo clique (ou **Editar**) abre o editor do passo em uma janela web.
- **Capturar ponto na tela** esconde a interface, espera o clique real e
  preenche X/Y. **ESC** cancela.
- **Capturar** (nos passos de imagem) pede o nome, esconde a interface e
  recorta a região para salvar o PNG já usado no passo.
- Arraste os cartões na lista para reordenar; também é possível usar os botões
  de ação de cada linha.
- **Espaço** ativa/desativa; **Delete** exclui; **Ctrl+Z** desfaz.
- **Bloco repetidor** insere automaticamente o `FIM do bloco` correspondente.
- Diálogos de confirmação, avisos e nomes de projeto/template são web; os
  seletores de arquivo usam o diálogo nativo do Windows.

### 3. Imagens

Passos de imagem esperam o template aparecer (ou desaparecer), com timeout,
confiança mínima, tentativas e política de falha:

- `abortar`: para a execução e tira um screenshot de erro.
- `continuar`: registra o aviso e segue para o próximo passo.

`Imagem + clique` e `Esperar imagem` capturam a região na hora. Também é
possível importar uma pasta inteira de PNGs em **⋯ → Importar templates** ou
em **Configurações → Diagnóstico → Importar templates**. O botão **Templates**
na barra lateral abre o gerenciador com prévia, filtro e remoção. O
`manifest.json` guarda metadados (hash, data, região).

No editor de um passo de imagem, **Testar template agora** esconde o app por
cerca de meio segundo e compara o template com a tela real. O resultado mostra
o score obtido e o melhor ponto encontrado; se falhar, salva um diagnóstico em
`logs/diag_teste_*.png`.

### 4. Executar

- **▶ Executar (Ctrl+R)**: executa o fluxo inteiro (respeitando os blocos).
- Pelo menu **⋯**: executar daqui em diante, executar até o passo selecionado
  ou testar o passo selecionado.
- **Pausar (F8)** / **Parar (ESC)**: funcionam globalmente, mesmo com a janela
  escondida.
- Ao executar ou testar de verdade, a janela web é **escondida** para não cobrir
  o alvo da captura. Um HUD nativo flutuante mostra o passo atual e o progresso
  da busca de imagem; ele fica no canto oposto ao template, não recebe foco e
  não aparece na captura.
- No modo **Simular**, a janela permanece visível e nada é controlado de
  verdade.
- O item em execução fica destacado na lista e o log mostra cada ação, inclusive
  quando uma imagem é **encontrada**.

### 5. Gerar o script `.py`

**Gerar .py** valida o projeto, pergunta as repetições (0 = infinito), salva o
script e copia os templates usados:

```
meu_fluxo.py
meu_fluxo.elgravador.json      # permite reimportar sem perda
imagens_templates/
    botao_salvar.png
    ...
```

Leve o `.py` **e** a pasta `imagens_templates` juntos. O script roda com:

```bat
python meu_fluxo.py
```

Durante a execução do script: **ESC** cancela e **F8** pausa/retoma.

## Atalhos

| Atalho | Ação |
|---|---|
| `F9` | iniciar/parar gravação |
| `F10` | pausar/retomar gravação |
| `ESC` | descartar gravação (gravando) / parar execução |
| `F8` | pausar/retomar execução |
| `Ctrl+R` | executar tudo |
| `Ctrl+S` / `Ctrl+Shift+S` | salvar / salvar como |
| `Ctrl+O` / `Ctrl+N` | abrir / novo projeto |
| `Ctrl+G` | gerar `.py` |
| `Ctrl+Z` | desfazer |
| `Ctrl++` / `Ctrl+-` | escala da interface |
| duplo clique | editar passo |
| `Espaço` | ativar/desativar passo |
| `Delete` | excluir passo |

## Estrutura

```
main.py                 # DPI + config + CLI + escolha da interface
nucleo/
  caminhos.py           # pastas e constantes
  dpi.py                # consciência de DPI e área virtual
  tema.py               # paleta Apple Glass (tema fixo)
  config.py             # configuração persistida e migração
  logs.py               # log em arquivo e console
  passos.py             # tipos, padrões, rótulos e emissores de código
  projeto.py            # Passo/Projeto, JSON, edição e validação
  imagens.py            # captura, recorte, templates e busca (OpenCV)
  backend.py            # pyautogui atrás de uma interface
  executor.py           # execução no app e fonte do runtime gerado
  codegen.py            # geração do .py autocontido
  legado.py             # importação de scripts antigos via AST
  gravador.py           # pynput + conversão de eventos em passos
ui/
  web_app.py            # janela PyWebView, ponte JS, diálogos e hide/show
  web_backend.py        # processo Tk oculto + API HTTP local com token
  janela.py             # controlador Tk reutilizado (gravação/execução/HUD)
  widgets.py            # botões, entradas, switches e cartões de vidro
  lista_passos.py       # lista com reordenação e atalhos
  dialogos.py           # captura de ponto/template e mensagens nativas
  config_view.py        # antiga aba de configurações do modo --tk
  overlay.py            # seleção de região na tela
  hud.py                # HUD flutuante durante a execução
ui_web/
  index.html            # estrutura da interface e sprite de ícones
  styles.css            # tema Apple Glass, layout e animações
  app.js                # fluxo, editor, modais, config e ponte com Python
testes/                 # pytest do núcleo (sem GUI)
```

Princípios:

- A interface web conversa com o Python por uma API local autenticada; ela não
  acessa arquivos nem executa automação diretamente.
- O processo do Tk nunca aparece: ele serve como backend maduro para gravação,
  execução, HUD, indicador e overlay.
- Passos são dados; o mesmo `Executor` roda no app e é espelhado no script.
- Coordenadas sempre em espaço virtual (`ImageGrab(all_screens=True)` +
  `SM_XVIRTUALSCREEN`), o que funciona com múltiplos monitores e DPI diferente.
- Listeners de teclado/mouse nunca chamam Tkinter: a UI consome uma `queue`.
- Gravação não usa `exec`/`eval` de nada capturado.

## Migração do app antigo

1. Na primeira execução, o `config.json` do app antigo é importado
   automaticamente se ele estiver em `../AUTOMACAO_EL_GRAVADOR/config.json`
   (tema, tempos e preferências). Nada no app antigo é alterado.
2. Importe os scripts: **⋯ → Importar script legado** (ou
   `python main.py --importar pasta`).
3. Importe os templates antigos: **⋯ → Importar templates** (ou
   `--templates`). Arquivos idênticos por hash não são duplicados.
4. Repetições detectadas no `for` externo viram configuração do projeto, sem
   multiplicar passos.
5. Se existir um `.elgravador.json` ao lado do script, ele é usado para uma
   reimportação fiel; senão, o importador lê o código com `ast`, resolve
   constantes e avisa sobre o que não conseguiu converter.

O importador reconhece `pyautogui`/`pynput`, `time.sleep`, `input`, `if`
simples, `range`/`while` de repetição e chamadas de imagem por nome de arquivo.

## Configurações importantes

- **Fonte / escala**: aplicadas ao vivo na interface web e salvas
  automaticamente. A escala vai de 15 a 22 px e afeta toda a interface.
- **Duração do movimento**: quanto o cursor leva para deslizar até o alvo.
- **Pausa entre ações**: intervalo após cada passo.
- **Intervalo de digitação**: ritmo usado ao digitar textos.
- **Confiança da imagem**: tolerância mínima para considerar um template
  encontrado.
- **Quando uma imagem não aparecer**: `abortar` ou `continuar`.
- **Gravação automática**: movimento livre, recorte em cliques e pausas.

## Testes

```bat
python -m pytest testes -q
```

Os testes cobrem projeto/JSON, geração de código, executor (com backend falso),
importação de legado, conversão do gravador e busca de imagens. A interface
gráfica e a integração WebView2/Tk precisam de uma sessão Windows e não são
testadas automaticamente.

## Gerar executável

```bat
python -m pip install pyinstaller
pyinstaller build.spec
```

O resultado fica em `dist/El_Gravador_18_Pro_Max.exe`. O spec inclui os arquivos de
`ui_web`, o backend Tk e os imports do PyWebView/WebView2. Os dados
(`config.json`, `imagens_templates`, `projetos`, `logs`) continuam sendo criados
ao lado do executável. O WebView2 Runtime precisa estar instalado na máquina.

## Solução de problemas

- **A janela não abre / “PyWebView não está instalado”**:
  `pip install pywebview` e confirme o WebView2 Runtime. Como fallback, rode
  `python main.py --tk`.
- **“A ponte com o Python não apareceu”**: feche e reabra. Execute
  `python main.py` em um terminal para ver o erro do backend; em builds,
  confirme que `ui_web` foi incluído no executável.
- **“pyautogui ausente”**: `pip install pyautogui pynput pillow`.
- **Cliques no lugar errado**: confira a escala do Windows; o app já declara
  DPI-aware. Evite misturar monitores com escalas muito diferentes sem testar.
- **Imagem não encontrada**: capture o template na mesma resolução/escala em
  que o script vai rodar; ajuste a confiança para 0.85–0.95. Use **Testar
  template agora** no editor: ele mostra o **melhor score**. Se o score estiver
  baixo, o template provavelmente está desatualizado, cortado ou coberto por
  outra janela.
- **O app cobre o alvo**: ao executar/testar de verdade, a janela principal é
  escondida automaticamente. Se ainda assim a imagem não for achada, confira se
  outra janela (navegador, explorer, notificação) não está por cima.
- **Diagnóstico de imagem**: em uma falha, o app salva
  `logs/diag_AAAAMMDD_HHMMSS.png` com um retângulo no melhor ponto e o score.
  O editor também salva `logs/diag_teste_*.png` ao usar **Testar template
  agora**. A pasta mantém os 20 diagnósticos mais recentes.
- **O script fecha sozinho**: ele tem `try/except` e imprime a falha no
  terminal; rode por um `cmd` para ler a mensagem.
- **Screenshots de erro**: ao executar pelo app, uma falha salva a tela em
  `logs/erro_AAAAMMDD_HHMMSS.png` para ajudar a diagnosticar.
- **ESC não para**: clique no console do script e pressione ESC; se o alvo roda
  como administrador, rode o gravador também como administrador.
- **Logs**: pasta `logs/`, um arquivo por dia.

## Notas

- `repeticoes = 0` significa loop infinito.
- O script gerado não depende deste projeto: só de `pyautogui`, `pynput`,
  `Pillow` e, opcionalmente, `opencv-python-headless` + `numpy`.
- O sidecar `<script>.elgravador.json` é a fonte para reimportar o `.py` sem
  depender de heurísticas.
