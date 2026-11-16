# Validação inicial

Versão adaptada ao portal público do SIPAC/UFBA disponível em **15/11/2026**.

## Consulta real

O teste no processo público `23066.026112/2026-79` encontrou **22 documentos** e recuperou todas as versões de conteúdo acessíveis nessa consulta:

| Verificação | Resultado |
| --- | --- |
| Documentos listados | 22 |
| Documentos com todas as versões acessíveis salvas | 22 |
| Arquivos de conteúdo | 36: 28 PDFs e 8 documentos eletrônicos em HTML |
| Páginas adicionais de metadados | 22 |
| Links relativos com destino existente | 58 |
| Pendências ao final | 0 |

Foram recuperados cabeçalho, interessados e movimentações. Os 28 PDFs puderam ser abertos pelo leitor de validação e os hashes SHA-256 dos 36 arquivos correspondiam ao inventário. Os acentos dos despachos em UTF-8 foram preservados. Respostas HTTP 503 temporárias foram recuperadas em novas tentativas.

Os documentos reais e os resultados dessa consulta **não estão incluídos no repositório**.

## Verificações do código

- Dez testes offline com dados sintéticos passaram.
- A integração HTTP foi verificada para página inicial, arquivos da interface, estado de conclusão, índice, abertura de PDF, rejeição de número inválido, token local, Host e proteção dos caminhos de arquivo.
- As sintaxes de Python e JavaScript foram verificadas.
- Os iniciadores verificam Python 3.10 ou superior e preparam um ambiente virtual local.

## Alcance

O teste real foi feito no ambiente Linux usado no desenvolvimento. Os iniciadores e as instruções contemplam Linux, Windows e macOS; a execução real em Windows e macOS ainda precisa ser validada.

A navegação visual automatizada não pôde ser concluída porque o navegador de teste não iniciou no ambiente de desenvolvimento. A integração HTTP e a extração e gravação dos documentos foram verificadas.

O processo usado no teste exibe seus 22 documentos em uma única página. Não houve teste real com login, CAPTCHA, conteúdos restritos ou outras instituições. Mudanças no layout do SIPAC podem exigir manutenção.
