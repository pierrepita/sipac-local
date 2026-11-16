# SIPAC Local — UFBA

Consulte um processo pelo número e salve os documentos públicos do **SIPAC da Universidade Federal da Bahia** em uma pasta do seu computador, com um índice para abrir cada arquivo.

A aplicação é feita em Python e abre uma interface no navegador. O processamento e a gravação dos arquivos acontecem no computador em que você executa o programa.

## Funcionalidades

- Consulta pelo número completo do processo.
- Recuperação do cabeçalho, dos interessados e das movimentações disponíveis.
- Download dos anexos originais e das versões com informações de assinatura oferecidas pelo portal.
- Cópia local em HTML dos despachos e documentos digitados diretamente no SIPAC.
- Índice com a descrição de cada documento e um link para o arquivo local.
- Registro de arquivos indisponíveis, restrições de acesso e falhas de download.

**Escopo:** consulta pública de `sipac.ufba.br`. Esta versão não realiza login. Documentos totalmente ocultos na consulta pública não podem ser enumerados. Outros SIPACs podem exigir adaptações.

## Requisitos

| Item | Requisito |
| --- | --- |
| Sistema | Linux, Windows ou macOS |
| Python | Versão 3.10 ou superior, com `pip` e suporte a ambientes virtuais |
| Navegador | Um navegador instalado no computador |
| Internet | Necessária para instalar as dependências e consultar o SIPAC |
| Conta no SIPAC | Dispensada para a consulta pública |

Depois de baixados, o índice e os documentos podem ser abertos sem internet.

## Instalação rápida

### 1. Baixe o código

Nesta página do GitHub, clique em **Code → Download ZIP**, extraia o arquivo e abra a pasta `sipac-local-main`.

Se você usa Git, também pode clonar:

```bash
git clone https://github.com/pierrepita/sipac-local.git
cd sipac-local
```

### 2. Instale o Python

Baixe pelo [site oficial](https://www.python.org/downloads/) se ele ainda não estiver instalado. Use **Python 3.10 ou superior**. No Windows, inclua o Python Launcher (`py`) durante a instalação.

Para conferir a versão, abra um terminal:

| Sistema | Comando |
| --- | --- |
| Linux / macOS | `python3 --version` |
| Windows | `py -3 --version` ou `python --version` |

### 3. Inicie a aplicação

**Linux ou macOS:** abra o terminal dentro da pasta do projeto e execute:

```bash
bash iniciar.sh
```

Se você extraiu o ZIP, entre primeiro na pasta extraída, por exemplo:

```bash
cd ~/Downloads/sipac-local-main
bash iniciar.sh
```

**Windows:** abra a pasta do projeto e dê dois cliques em **`iniciar.bat`**. Pelo Prompt de Comando:

```bat
cd %USERPROFILE%\Downloads\sipac-local-main
iniciar.bat
```

Os iniciadores verificam a versão do Python, criam o ambiente `.venv`, instalam as dependências e abrem o navegador em **[http://127.0.0.1:8765](http://127.0.0.1:8765)**.

Mantenha o terminal aberto durante o uso. Para encerrar, espere a consulta terminar e pressione **Ctrl+C** no terminal.

## Como usar

1. Informe o número completo do processo, por exemplo `23066.026112/2026-79`. Os 17 dígitos sem pontuação também são aceitos.
2. Em **Salvar os processos em**, escolha uma pasta ou digite seu caminho completo.
3. Clique em **Consultar e baixar** e acompanhe o andamento.
4. Confira o total de documentos salvos e as pendências informadas ao final.
5. Clique em **Abrir índice do processo** ou abra `indice.html` diretamente na pasta criada.

O destino inicial é `Documentos/SIPAC` dentro da sua pasta de usuário; você pode alterá-lo. Em alguns sistemas, a pasta pessoal de documentos tem outro nome, então escolha o caminho que preferir.

Cada consulta cria uma subpasta com o número do processo, a data e a hora. Execuções anteriores não são sobrescritas.

**Execute o Python no computador em que deseja salvar os arquivos.** Se o programa for iniciado em um servidor remoto, os arquivos serão gravados nesse servidor.

## Conteúdo da pasta do processo

| Arquivo ou pasta | Conteúdo |
| --- | --- |
| `indice.html` | Cabeçalho, interessados, tabela de documentos com descrições e links locais, movimentações e pendências |
| `documentos/` | Arquivos baixados, cópias HTML dos documentos eletrônicos e páginas com seus metadados |
| `processo.json` | Dados estruturados e inventário com hashes SHA-256 |
| `documentos.csv` | Relação de documentos para abrir em uma planilha |

**Mantenha `indice.html` e `documentos/` juntos.** Os links são relativos: mover ou copiar a subpasta completa preserva os vínculos.

Um documento pode oferecer um original e uma versão com assinaturas. Por isso, o total de arquivos pode superar o total de documentos.

As descrições reproduzem o campo **Assunto Detalhado** do SIPAC; quando ele não está disponível, o índice usa o tipo do documento. Não há geração de resumos por IA.

Os PDFs são salvos com os mesmos bytes recebidos do portal. Documentos em HTML recebem uma cópia local em UTF-8, com o texto e as informações de assinatura exibidas, sem scripts ou dependências remotas. Essa cópia não acrescenta assinatura digital ao arquivo. Para imprimir um despacho, abra seu HTML no navegador e use **Imprimir**.

## Problemas comuns

| Problema | Como resolver |
| --- | --- |
| `python3`, `python` ou `py` não encontrado | Instale Python 3.10 ou superior; no Windows, habilite o Python Launcher ou a inclusão do Python no PATH |
| Falha ao criar `.venv` no Ubuntu/Debian | Instale o pacote `python3-venv` e execute o iniciador novamente |
| Falha na instalação de dependências | Confira a conexão e as permissões de rede para o PyPI. Em computadores institucionais, pode ser necessário apoio da equipe de TI |
| O navegador não abriu | Com o programa executando, abra `http://127.0.0.1:8765` manualmente |
| Porta 8765 ocupada | Use `bash iniciar.sh --porta 8766` ou, no Windows, `iniciar.bat --porta 8766`. Depois abra `http://127.0.0.1:8766` |
| O seletor de pastas não funciona | Digite o caminho completo. O seletor é opcional e depende do Tkinter; no Ubuntu/Debian, ele costuma estar no pacote `python3-tk` |
| A pasta não permite gravação | Escolha uma pasta pertencente ao seu usuário |
| Processo não localizado | Confira o número e a disponibilidade diretamente no [portal público do SIPAC/UFBA](https://sipac.ufba.br/public/jsp/portal.jsf) |
| Download parcial ou erro HTTP | Veja os detalhes e o índice. O programa faz novas tentativas limitadas; persistindo o erro, repita a consulta mais tarde |
| A interface perdeu a conexão | Confira se o terminal continua aberto. Os arquivos já gravados ficam na pasta de destino |

## Instalação manual

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

### Windows — Prompt de Comando

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

Os comandos do Windows usam o executável do ambiente diretamente e dispensam a ativação por PowerShell.

## Uso pelo terminal

Depois de instalar as dependências, você pode consultar sem abrir a interface. Com o ambiente ativado:

```bash
python app.py --processo 23066.026112/2026-79 --destino "/caminho/completo/para/SIPAC"
```

No Windows:

```bat
.venv\Scripts\python.exe app.py --processo 23066.026112/2026-79 --destino "%USERPROFILE%\Documents\SIPAC"
```

Códigos de saída: `0` para consulta concluída sem pendências, `2` para consulta concluída com pendências e `1` para falha da operação.

## Limitações

- A cópia reflete o momento da consulta. Novas juntadas exigem outra execução.
- Itens listados sem conteúdo acessível são registrados como restritos ou indisponíveis; itens totalmente ocultos não podem ser detectados.
- Falha em uma versão de um documento gera resultado parcial, mesmo que outra versão tenha sido salva.
- Respostas de login, páginas de erro e formatos não reconhecidos não são tratados como downloads válidos.
- A paginação é percorrida quando reconhecida. Mudanças de layout podem exigir atualização do código.
- O limite é de 250 MB por resposta; arquivos maiores geram pendência.
- Cada nova execução cria outra pasta. A versão atual não retoma automaticamente uma execução anterior.
- A interface escuta somente em `127.0.0.1`. O programa não publica os arquivos em um serviço de hospedagem.

## Desenvolvimento e testes

Com as dependências instaladas, execute na raiz do projeto:

```bash
python -m unittest -v test_sipac.py
```

Os testes são offline e usam dados sintéticos. Eles cobrem integridade dos PDFs, restrições de acesso, falhas e novas tentativas, codificação e links locais.

| Caminho | Responsabilidade |
| --- | --- |
| `app.py` | Servidor local, interface e modo terminal |
| `sipac.py` | Consulta JSF, extração, downloads e índice |
| `web/` | Interface HTML, CSS e JavaScript |
| `test_sipac.py` | Testes offline |
| `docs/VALIDACAO.md` | Evidências e alcance da validação inicial |

O repositório contém o código e a documentação. Documentos baixados, ambientes virtuais e resultados locais estão excluídos do versionamento pelo `.gitignore`.

Para relatar um problema, abra uma issue com seu sistema operacional, versão do Python e mensagem de erro. Compartilhe apenas as informações necessárias para reproduzir o problema.
