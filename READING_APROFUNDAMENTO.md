# Aprofundamento de 10 casos no TJSP

Esta pasta é uma segunda etapa independente do leitor de diários. Você escolhe até 10 casos da aba **Casos**, consulta o e-SAJ e recebe um relatório com as informações públicas encontradas. A planilha original e seu score não são modificados.

## No projeto

O código fica em `src/guicredito/aprofundamento/` e os testes em `tests/aprofundamento/`. Não exige dependências novas. Execute os comandos na raiz do projeto, usando `.venv/bin/python`.

Os 10 primeiros casos da rodada `casos_djen_2026-11-12_a_2026-11-21.xlsx` já estão selecionados em `dados/aprofundamento/selecionados.json`. Você pode ir direto à etapa 2. Para mudar a seleção, use outras posições e outro destino na etapa 1.

A suíte completa do projeto passou: **240 testes**, incluindo 25 desta etapa. A coleta online ainda precisa ser confirmada; os testes usam páginas fictícias e não garantem compatibilidade com o layout atual do TJSP.

Esta versão consulta **e-SAJ, 1º grau**. Migração para eproc ou redirecionamento para outro serviço exige conferência manual.

## 1. Escolher os casos

Os números abaixo são as posições da coluna **#**, não os números das linhas do Excel. Salve a rodada no Excel antes de selecionar: o comando lê o arquivo salvo.

```bash
.venv/bin/python -m guicredito.aprofundamento selecionar \
  --planilha saida/casos_djen_2026-11-12_a_2026-11-21.xlsx \
  --posicoes 1-10
```

Para escolher outros casos, use, por exemplo, `--posicoes 1,3,7,10-16`. Isso seleciona dez posições. Use `--destino dados/aprofundamento/outra_selecao.json` para manter uma segunda seleção; uma seleção existente não é sobrescrita.

O JSON registra o CNJ, a posição e o score original. Não é preciso digitar nome, CPF, senha ou chave de API.

## 2. Consultar

```bash
.venv/bin/python -m guicredito.aprofundamento consultar
```

O comando cria uma pasta com data e hora em `saida/aprofundamento/` e imprime o caminho do `relatorio.html`. Abra esse relatório no navegador.

Para consultar uma seleção específica:

```bash
.venv/bin/python -m guicredito.aprofundamento consultar \
  --selecao dados/aprofundamento/outra_selecao.json \
  --saida saida/aprofundamento/revisao_01
```

Repetir com a mesma seleção e a mesma pasta de saída reutiliza os casos já coletados, mantendo a data original da consulta. Para obter dados novos, escolha uma nova pasta de saída. Não é possível reutilizar uma pasta de saída pertencente a outro lote.

## O que volta

Quando os campos estiverem presentes na página reconhecida:

- Classe, assunto, foro, vara e juiz.
- Valor da causa, distribuição e situação, como escritos pelo site.
- Partes exibidas e linhas de movimentações presentes no HTML retornado.
- Data da consulta, URL, cópia textual da resposta e hash para conferência.

O valor da causa **não é o saldo atualizado da dívida**. As movimentações retornadas não são garantia do histórico integral. Esta etapa não baixa a pasta digital, documentos restritos ou autos completos, não interpreta decisões e não recalcula o score.

Os arquivos ficam assim:

```text
dados/aprofundamento/selecionados.json
saida/aprofundamento/<rodada>/
  selecao.json
  resumo.json
  relatorio.html
  <numero-CNJ>/
    resultado.json
    consulta.html.txt
    detalhe.html.txt       # quando foi necessário abrir um resultado
```

Os arquivos `*.html.txt` são evidências textuais. O relatório apresenta somente texto escapado; não executa scripts vindos das respostas. `dados/` e `saida/` já são ignorados pelo Git do projeto.

## Quando a consulta não funcionar

O lote é sequencial, com intervalo de cinco segundos entre requisições. Não repete automaticamente erros. Bloqueio, captcha, falha de rede ou página não reconhecida interrompem novas consultas e deixam os restantes pendentes. Nenhum desses estados significa ausência de dívida ou bens.

O TJSP informa que o e-SAJ se destina a consultas avulsas e restringe padrões de RPA. Portanto, não há garantia de que esse acesso por programa será aceito, mesmo num lote de dez. Esta implementação não contorna bloqueios, não resolve captchas e não usa credenciais.

Se o site exigir interação humana, faça a consulta no navegador. É possível importar um HTML e-SAJ salvo em UTF-8 com o CNJ e os campos presentes:

```bash
.venv/bin/python -m guicredito.aprofundamento importar \
  --processo NUMERO_CNJ_DO_CASO \
  --html /caminho/pagina_salva.html \
  --saida saida/aprofundamento/revisao_01
```

A importação confere o CNJ e registra que a origem é um arquivo fornecido pelo usuário. Ela não é uma consulta online. Páginas do eproc e PDFs não são aceitos por esse extrator.

## Testes

```bash
.venv/bin/python -m pytest tests/aprofundamento -q
```

Cobrem seleção, limites do lote, CNJ, identidade do processo retornado, dados ausentes, interrupção em bloqueios, preservação do score e da planilha, relatório, origem dos dados e reutilização de resultados. Não substituem a validação contra o portal real.

## Referências oficiais

- [Consulta pública e escolha entre e-SAJ e eproc](https://portal.tjsp.jus.br/eproc/Duvidas/Duvida?id=12&pagina=3).
- [Informações do TJSP sobre restrições a consultas robotizadas](https://portal.tjsp.jus.br/Noticias/Noticia?codigoNoticia=64795).
- [Consulta de primeiro grau e limitações de acesso aos documentos](https://esaj.tjsp.jus.br/WebHelp/id_consultando_processos_de_1_grau.htm).
