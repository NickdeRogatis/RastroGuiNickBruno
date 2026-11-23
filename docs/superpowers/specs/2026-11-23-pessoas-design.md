# Pesquisa de pessoas nos casos selecionados — design

- **Data:** 23/11/2026
- **Status:** rascunho para aprovação do Nick; implementação em tarefa separada.
- **Base:** designs de 08/11 (§§1–7) e 22/11 (§§1 e 3), ExecucoesSP_FontesEPlano.html (§§2, 7 e 8), código e testes de aprofundamento.
- **Escopo desta entrega:** somente este documento e o plano; nenhuma consulta real ou alteração de produto.

Convenção: **decisão do Nick** registra o que ele decidiu; *(escolha minha)* registra decisões de refinamento e propostas de implementação para conferência. As notas sobre registros e fornecedores usam a documentação local. O ensaio impessoal anterior do Hermes no Studio fornece os resultados operacionais da seção 11. Nenhum dado de dados/ ou saida/ foi lido.

## 1. Intenção e porquê

Depois de escolher casos no DJEN e aprofundá-los no e-SAJ, Nick quer saber quem são as partes, se há indícios de capacidade de pagamento do devedor e como chegar às pessoas relevantes. O negócio é comprar o crédito com desconto e renegociar em condições mais gentis. A reunião de 13/11 mudou o foco do score para capacidade e histórico de pagar; esta etapa oferece evidências para julgamento humano, sem recalcular esse score.

A pesquisa começa após a seleção de até dez casos, usando a seleção do aprofundamento. Não é preciso comprar a dívida antes de coletar qualquer informação prevista aqui, inclusive contatos (**decisão do Nick**). Isso descreve o produto desejado, não uma conclusão sobre base legal: as dúvidas estão em L11–L16.

## 2. Objetivos

Duas passagens (**decisão do Nick**):
1. `pesquisar`: fontes gratuitas para identificar candidatos e reunir indícios de capacidade de pagamento.
2. `contatos` fica para uma fase posterior. Nick confirma a identidade, autoriza o gasto para aquela pessoa e executa o comando. A primeira rodada usa apenas fontes gratuitas (**decisão do Nick**).

Entregar HTML legível, Excel editável para confirmação e JSON por processo. Todos os achados começam como candidatos; confiança alta não substitui confirmação (**decisão do Nick**).

Critério de aceite *(escolha minha)*: lote fictício com dois casos percorre as duas passagens com fontes falsas, preserva os arquivos de entrada e as decisões humanas, distingue indisponibilidade de ausência de achados e nunca revela contatos de candidatos ambíguos do provedor.

## 3. Não-objetivos

Não alterar DJEN, aprofundamento, score, ranking ou arquivos existentes. Não implementar cessão, negociação, cobrança, agendamento, avaliação patrimonial completa, salário estimado, saldo da dívida ou garantias de solvência. Não implementar uma busca exaustiva de processos ou acesso a autos restritos.

O programa nunca envia mensagens, e-mails, chamadas ou pedidos de amizade. Antes da cessão, Nick só fala com o credor ou com o advogado dele. O contato com o devedor ou com o advogado do devedor fica para depois da cessão (**decisão do Nick**). Um advogado com lado desconhecido precisa ter o vínculo esclarecido antes de qualquer abordagem.

## 4. Anti-objetivos e fronteiras

Pesquisar apenas devedores, credores PF/PJ em igualdade de tratamento, e advogados de ambos os lados (**decisão do Nick**). Nunca pesquisar familiares, vizinhos, amigos ou sócios que não sejam partes; nunca navegar a rede de relacionamentos.

Sobre o devedor, coletar emprego/empregador em páginas profissionais públicas; participações societárias, situação e capital declarado das empresas; outros processos homônimos; links públicos Instagram/Facebook como indícios de identidade, cidade ou empregador. Não catalogar posts, fotos, estilo de vida ou conexões (**decisão do Nick**).

Sobre credores e advogados: contatos públicos, inclusive dados profissionais do cadastro OAB; contatos pagos dependem da confirmação de identidade e da autorização individual do gasto. O provedor oferece endereço, telefone/WhatsApp e e-mail (**decisão do Nick**). Um telefone não será rotulado WhatsApp sem indicação da fonte *(escolha minha)*.

Capital social não equivale a patrimônio pessoal disponível; emprego não prova renda; homonímia não prova identidade; ausência de resultados não prova falta de capacidade de pagamento *(escolha minha)*. Nunca promover inferências do modelo a fatos sem evidência.

## 5. Regras que mudam

| Regra anterior | Substituição nesta etapa |
|---|---|
| 08/11 §4: não virar lista de abordagem; sem contatos, telefone ou e-mail | Coletar contatos de devedor, credor e advogados antes da compra; nenhuma abordagem automática (**decisão do Nick**). |
| 08/11 §4: nomes nunca enviados a serviços externos | A consulta nominal mínima pode sair do Hermes para o buscador gratuito. Sites públicos e registros recebem os dados necessários à consulta. Só o provedor de contatos recebe CPF, quando informado para uma identidade confirmada. A inferência fica no Studio (**decisão do Nick**). |
| 08/11 §§4–5: não raspar tribunal; DJEN fonte única | Aprofundamento já acrescentou e-SAJ; pessoas acrescenta páginas públicas e registros. Isso não autoriza burlar bloqueios nem afirma permissão jurídica de raspagem (**decisão do Nick**). |
| 22/11 §3: provedores fora; consulta só nos 2–3 casos comprados | Provedor pago de contatos para pessoas confirmadas e marcadas por Nick para a consulta paga dos casos selecionados, antes da compra (**decisão do Nick**). |
| 08/11 §1. Falar com o devedor só depois da cessão | A coleta pode anteceder a compra. Antes da cessão, o contato humano fica restrito ao credor e ao advogado do credor (**decisão do Nick**). |

A fronteira de terceiros da seção 7 do documento de 26/10 continua. Bases vazadas continuam fora. Nenhuma mudança neste documento altera retroativamente o funcionamento das duas etapas existentes.

## 6. Abordagens e estrutura

Escolhido: novo módulo `src/guicredito/pessoas/`, testes `tests/pessoas/`, comandos próprios (**decisão do Nick**).
Alternativas consideradas:
- Subcomandos no aprofundamento: misturam contatos em uma etapa documentada como dados processuais públicos, exigindo reescrever testes e READING.
- Repositório separado: separação de dados mais forte, mas duplica CNJ, seleção e manutenção.

*(escolha minha — A1)*: dividir responsabilidades em `modelos.py`, `entrada.py`, `identidade.py`, `config.py`, `http.py`, `hermes.py`, `fontes.py`, `cnpj.py`, `oab.py`, `evidencias.py`, `planilha.py`, `relatorio.py`, `fluxo.py` e `__main__.py`. Usar dataclasses/Protocol, urllib, sqlite3 e demais módulos padrão; openpyxl e certifi já estão instalados. Nenhuma dependência nova.

Reutilizar somente utilitários públicos e puros: normalização textual do DJEN, classificação de empresa/cabeçalho e validação CNJ/seleção do aprofundamento; não chamar sua coleta nem seu gravador de lote. A regra de três palavras em `_nomes_para_cruzar` pertence ao score. Não importar essa função privada: JOÃO EXEMPLO, nome de duas palavras, deve poder aparecer como candidato sem confirmação automática *(escolha minha — A2)*.

## 7. Entrada e contrato de dados

*(escolha minha — A3)*: `pesquisar --selecao <json> --aprofundamento <pasta> --planilha <xlsx> --saida <lote>`; todos os caminhos explícitos, evitando pegar uma rodada por acidente. Seleção versão 1 contém `casos` com `numero_processo`, `posicao_original`, `pontuacao_original`, além de `origem_planilha` e `selecionado_em`. Validar 1–10 CNJs sem repetição.

Ler somente os resultados dos CNJs selecionados e linhas correspondentes das abas Casos e Publicações. Conferir CNJ do resultado, manifestos e hashes das evidências utilizadas. Nunca seguir automaticamente `processo_principal_texto`: incidente é processo próprio. Ausência de capa vira limitação registrada; divergência ou hash inválido interrompe antes de pesquisa. A planilha original tem Credor, Devedor, Comarca, Trecho principal, mas não OAB estruturada. Publicações tem Processo, Data, Tipo, Órgão e Texto.

*(escolha minha — A4)*: dados versionados:
- alvo: id estável, CNJ, papel, tipo PF/PJ, nome original, fonte do papel;
- candidato: id, alvo_id, fonte/chave externa, nome, confiança, indícios, conflitos, status de verificação;
- evidência: id, URL, data UTC, fonte, trecho, tipo página/snippet/registro/manual, arquivo e SHA-256;
- decisão por candidato: ID estável, `Confirmado`, CPF opcional e `Autorizar consulta paga` (sim/não/vazio, padrão vazio). Guardar a data de leitura. Cada vínculo do índice empresarial referencia o candidato e a evidência que o sustenta.
- consulta: fonte, estado, motivo, horário, versão do extrator;
- contato: candidato confirmado, identificador do provedor, valor, tipo, origem/data, sem afirmar atualidade além do que o fornecedor informa.

IDs persistentes independem da ordem das linhas. Não fundir automaticamente duas pessoas por nome. Relações entre processos usam referências; as decisões continuam vinculadas ao candidato e à evidência daquele lote.

## 8. Passagem 1 — pesquisar

1. Validar entradas; extrair alvos das partes, complementando com texto do Excel. Todo PF no polo devedor entra: executado, réu, avalista, fiador, coobrigado *(escolha minha)*. PJ devedora recebe só seu cadastro, situação e capital; seus sócios não viram alvos. Credor PJ não autoriza buscar seus donos.
2. Parser próprio de advogados em pessoas interpreta nomes, OAB e vínculo com a parte; sem vínculo comprovável, mostrar “lado desconhecido” *(escolha minha)*. Não pesquisar testemunhas ou nomes meramente citados.
3. Consultar o índice CNPJ no SSD interno do Studio já na primeira rodada. Conferir o volume previsto e o espaço livre antes de obter a base. Quando o cadastro OAB apresentar captcha, registrar na planilha privada o nome do advogado, OAB/UF disponível, link para o cadastro e motivo da pendência. O lote segue. Nick pode conferir e preencher os campos profissionais mais tarde (**decisão do Nick**).
4. O agente Hermes executa a busca (**decisão do Nick**, revisão de 23/11). O Python monta a consulta a partir de um único alvo autorizado e do objetivo correspondente ao seu papel. Exemplos de objetivos são localizar página profissional do devedor, referência pública a outro processo, site institucional do credor ou página profissional do advogado. Uma consulta recebe somente nome e, quando necessário, cidade ou termo profissional. CPF, endereço residencial, telefone, contatos, arquivos e texto integral do processo ficam fora desse pedido.
5. O adapter implementa `buscar(consulta) -> resultados(url, titulo, snippet)` sobre a API do agente (§11). Só admite resultados da saída efetiva de `web_search`. O cliente mantém a interface substituível por um dublê nos testes. Com a busca desligada, registra “busca não configurada” e prossegue com os registros. Uma busca ligada que falha tem outro tratamento (§12).
6. O Python abre uma vez cada URL pública relevante devolvida pela busca e reaproveita sua evidência no lote *(escolha minha — A17)*. Em LinkedIn, Instagram e Facebook faz um único GET direto, sem login, cookies, sessão, redirecionamento, navegação interna ou repetição. Se houver barreira, captcha ou erro, conservar título, snippet e URL, marcar “não verificado — conferir no navegador” e seguir. Sem snippet útil, registrar só o link (**decisão do Nick**). Essa divisão permite contar e auditar as tentativas. Ainda que disponível no Studio, `web_extract` fica fora da pesquisa nominal nesta versão.
7. Em uma chamada independente de leitura, o Qwen via Hermes recebe apenas o recorte relevante e a referência da fonte, com ferramentas desabilitadas no servidor. Propõe candidatos a partir desse texto. Rejeitar URL ausente dos resultados de busca do lote e trecho que não ocorra na página baixada, comparando com `normalizar`; somente para download indisponível aceitar trecho do snippet. Snippet é sempre não verificado *(escolha minha)*. Registros estruturados seguem validadores próprios; não são obrigados a aparecer no buscador.
8. Salvar evidências aceitas com data/hash e produzir relatório/Excel; nada conta como identidade confirmada antes da marca humana.

*(escolha minha — A5)*: confiança baixa para nome isolado; média para nome mais um indício independente compatível (cidade, empregador, endereço do processo ou faixa etária); alta para dois indícios independentes compatíveis, sem conflitos. Conflitos explícitos reduzem a baixa. Exibir todos os candidatos retornados pelas consultas executadas, inclusive baixa confiança e sem limite silencioso. Registrar paginação/limite do serviço; não prometer todos os homônimos existentes.

*(escolha minha — A6)*: não guardar páginas sociais integrais com fotos/posts/conexões. Extrair texto relevante à identidade, guardar esse recorte e hash dele; hash do corpo transitório pode registrar integridade, sem persistir o corpo. Citações são verificadas no texto efetivamente recebido antes da minimização. Relatório distingue evidência de identidade de indício econômico.

## 9. Passagem 2 — contatos

**Decisão do Nick.** A primeira rodada utiliza somente fontes gratuitas. O Excel preserva as marcações para o futuro. Mesmo após configurar um fornecedor, só iniciar a identificação paga quando o mesmo candidato tiver `Confirmado = sim` e `Autorizar consulta paga = sim` e Nick executar `contatos`. A ausência de telefone ou a existência de e-mail público não muda nenhuma marcação. Revalidar ambas antes de solicitar contatos após desambiguação. CPF opcional deve passar os dois dígitos verificadores e a rejeição de sequências repetidas antes da primeira chamada.

Interface do provedor ainda não escolhido (**decisão do Nick**): `identificar(identidade_confirmada)` e `obter_contatos(id_confirmado)`. Sem provedor: “provedor não configurado”, manter as marcações pendentes e encerrar sem consultas. Usar CPF informado; sem CPF, nome e indícios confirmados (cidade/faixa etária). Se fornecedor exigir CPF, marcar “identificador necessário”, nunca adivinhar.

*(escolha minha — A7)*: quando o fornecedor retorna várias identidades, persistir apenas IDs opacos e indícios mínimos de desambiguação, sem contatos, CPF integral ou resposta bruta. Gerar candidatos na aba Provedor; Nick confirma um, salva e executa contatos novamente. Validar que o candidato pertence ao alvo confirmado. Somente então buscar/persistir contatos. Exigir fornecedor com descoberta separada de contatos ou projeção equivalente; contrato que só devolve contatos em massa é incompatível com esta garantia e fica pendente de escolha. Não logar payload bruto nem armazenar contatos descartados.

Credores PF/PJ e advogados também podem usar o provedor após confirmação e autorização individual; PJ usa CNPJ validado derivado do registro confirmado, nunca CPF inventado *(escolha minha — A8)*. Se o fornecedor não suporta PJ, registrar capacidade não disponível. Licenciamento e finalidade precisam ser compatíveis; não escolher fornecedor nesta entrega.

## 10. Excel, HTML, JSON e repetição

O lote privado contém `relatorio.html`, `pessoas.xlsx` e `<CNJ>/*.json` em `saida/pessoas/<lote>/`. O arquivo destinado ao revisor chama-se `revisao.html`. Nick é o único que recebe o conjunto completo e toma as decisões de identidade, gasto e exclusão (**decisão do Nick**).

*(escolha minha — A9)*: abas:
- **Candidatos**: Lote, Alvo ID, Candidato ID, Processo, Papel, Tipo, Nome, Confiança, Cidade, Empregador, Faixa etária, Evidências IDs, URLs, Verificação, **Confirmado**, **CPF**, **Autorizar consulta paga**.
- **Provedor**: Alvo ID, Candidato ID de origem, Provedor ID, Nome candidato, Indícios mínimos, **Confirmado**. Sem contatos antes da confirmação específica.
- **Evidências**: ID, Candidato ID, Categoria, Fonte, URL, Data, Trecho, SHA-256, Estado.
- **Contatos**: Candidato ID, Origem, Tipo, Valor, Data da fonte, Data da consulta; somente dados públicos permitidos ou pagos confirmados.
- **Casos**: código de revisão, processo, **Descartar** (sim/vazio). A marca seleciona o caso para a prévia de exclusão.
- **Vínculos**: Caso ID, Candidato ID, Vínculo ID, nome da empresa, evidências e capital declarado. Aba de leitura. A confirmação vem da linha correspondente na aba Candidatos. Coincidências de nome sem evidência de identidade comum geram candidatos distintos.
- **OAB**: Alvo ID, nome encontrado, OAB/UF disponível, link do cadastro, estado, **OAB/UF conferida**, **dados profissionais conferidos**, **data da conferência**. A entrada manual preserva o que a consulta automática encontrou.
- **Como ler**: limitações, legendas, instrução de salvar/fechar Excel, contagens e fontes não consultadas.

Nos campos em negrito, Nick informa decisões ou resultados de conferência manual. Nas abas Candidatos e Provedor, `Confirmado` aceita sim/não/vazio. CPF é texto para preservar zeros. Validar os IDs e seus vínculos com o manifesto antes de efeitos externos. Recusar linhas desconhecidas ou duplicadas, fórmulas em campos editáveis e decisões incompatíveis. A ordenação das linhas não altera a identidade. Preservar todos os campos manuais na reexecução.

*(escolha minha — A10)*: por CNJ, `pessoas.json`, `consultas.json`, `evidencias.json`, `contatos.json` e recortes `evidencia-<id>.txt`; manifesto do lote contém versões, hashes de entrada e identidade da seleção, sem segredos. Escrita atômica e bloqueio de lote contra duas execuções simultâneas. Ao repetir, ler Excel primeiro, mesclar por IDs estáveis e preservar confirmações, CPF, autorização de gasto, OAB manual e descarte pendente; não reaproveitar confirmação em candidato diferente. Arquivo aberto/erro de gravação interrompe sem perder versão anterior. Reutilizar evidência e consultas pagas concluídas com data original; atualização usa novo lote. Mudança de entrada/seleção incompatível exige outro lote. Não repetir automaticamente pedido pago de resultado incerto: exigir conciliação pelo ID da requisição antes.

HTML escapa todo texto e atributos, aceita hyperlinks apenas HTTP(S), não incorpora scripts/HTML das fontes. Excel escreve conteúdo externo como texto, evitando execução de fórmulas *(escolha minha — A11)*. Durante pesquisa e contatos, o terminal imprime contagens e caminho do relatório. Na prévia de descarte também exibe rótulos dos casos e código de confirmação. Diagnósticos de configuração podem nomear endpoint sanitizado e chaves ausentes, nunca nomes, CPFs, contatos, snippets ou segredos *(escolha minha)*.

### Resumo para decidir se o caso merece avançar

**Decisão do Nick.** O revisor recebe apenas `revisao.html`. A ficha mostra um rótulo como “Caso 01”, a fase processual em termos gerais, categorias de indícios confirmados e limitações. Se houver apenas uma coincidência de nome no quadro societário, a ficha diz **“vínculo empresarial pendente de confirmação”**. Quando Nick confirma a identidade do candidato correspondente ao registro societário, a ficha indica participação empresarial e a faixa do capital social declarado da empresa. Se o valor faltar, exibir “capital não informado”. A faixa descreve a empresa, sem estimar o patrimônio pessoal do devedor.

*(escolha minha — A18)* Gerar o arquivo do revisor a partir de uma lista fechada de campos e frases próprias. Usar rótulo estável dentro do lote, fase ampla, estado do vínculo, faixa de capital e limitações categóricas. Para a primeira versão, usar faixas em reais: abaixo de 100 mil, de 100 mil a menos de 1 milhão, e a partir de 1 milhão. Somente o arquivo privado contém o mapa entre rótulos e processos. O resumo não recebe nomes de pessoas ou empresas, CNJ, OAB, CPF, contatos, endereço, empregador, URL, citações, datas exatas ou texto livre da fonte. Aplicar o mesmo critério a atributos HTML, título, comentários, nomes de arquivos e metadados. Nick entrega o resumo ao revisor pelo meio que escolher.

### Descarte confirmado por caso

**Decisão do Nick.** Nick marca `Descartar = sim` no Excel e revisa a prévia dos casos pelo rótulo. A confirmação explícita remove a pesquisa desses casos da etapa `pessoas`: linhas de todas as abas, recortes, JSON, dados pessoais no manifesto e os dois relatórios gerados no lote. Regerar os relatórios com os casos mantidos. O índice do CNPJ é uma fonte compartilhada. O DJEN, as entradas do e-SAJ e os demais casos continuam disponíveis.

*(escolha minha — A19)* O comando `descartar --lote <pasta>` exibe a prévia e um código vinculado ao lote e à seleção exata. `descartar --lote <pasta> --confirmar <código>` repete a validação e aplica o descarte sob bloqueio. Alteração na seleção invalida o código. Registrar apenas as posições suprimidas na seleção imutável do lote para que uma reexecução não reconstrua casos descartados. Preparar a nova geração de saídas antes de remover a anterior. Uma execução interrompida retoma a limpeza antes de liberar qualquer exportação ou consulta do lote. Eliminar temporários e versões de trabalho controladas por `pessoas`. O descarte alcança a cópia do resumo sob controle do programa. Cópias já entregues e retenção no Hermes ou nos fornecedores têm ciclo próprio, a considerar na revisão jurídica.

## 11. Conexão com o Mac Studio

**Decisão do Nick, revisada em 23/11/2026.** O Python pode rodar no Studio, onde o projeto está aberto, ou no laptop. Em ambos os casos, ele chama o **gateway do agente Hermes**. O Studio executa o Qwen e administra as ferramentas. A aplicação não escolhe nem contrata o motor de busca a cada requisição.

| Configuração observada no ensaio impessoal anterior | Valor |
|---|---|
| Hermes | `v0.21.7+500.g8f81791`, um gateway de usuário |
| Base da aplicação e ID anunciado por `GET /v1/models` | `http://127.0.0.1:8642/v1`, `hermes-agent` |
| Inferência interna do Hermes | llama.cpp autenticado em `127.0.0.1:18434`, `Qwen3.6-35B-A3B-UD-Q4_K_M`, contexto de 262144 tokens |
| Autenticação e texto | Sem Bearer ou com chave incorreta, HTTP 401. Com chave válida, modelos e texto retornaram HTTP 200. |
| Ferramentas em pergunta impessoal | Em `POST /v1/responses`, o Hermes executou `web_search` via Parallel e `web_extract` via Firecrawl, sem chaves desses fornecedores. Três entradas apontaram para a mesma página da IANA. |

O gateway escuta em loopback. No próprio Studio basta a base acima. No laptop usa-se a mesma base após abrir o túnel abaixo. O SSH do Studio respondeu em `192.168.15.10:22`; a autenticação e o encaminhamento a partir do laptop ainda precisam de validação. O cliente reaproveita o gateway instalado.

```sh
ssh -NT -o ExitOnForwardFailure=yes -L 127.0.0.1:8642:127.0.0.1:8642 nickderogatis@Nicks-Mac-Studio.local
```

**Configuração da aplicação** *(escolha minha — A12 a A14)*. `PESSOAS_BUSCA=hermes` habilita a web. Ausente ou vazia, pula somente a web; outro valor é erro. `PESSOAS_HERMES_URL` e `PESSOAS_HERMES_MODELO` usam a base e o ID da tabela. `PESSOAS_HERMES_TIMEOUT` tem padrão de 180 s. `PESSOAS_HERMES_CONTEXTO` declara a janela efetiva, aqui 262144. `PESSOAS_HERMES_KEY` fornece a chave dedicada ao gateway por ambiente ou pelo arquivo local privado da aplicação. No Studio sua origem é o campo `API_SERVER_KEY` em `~/.hermes/.env`. O cliente transmite o valor apenas ao gateway, em cabeçalho Bearer. Os registros públicos e o fornecedor de contatos têm transportes próprios. O arquivo privado do Hermes não é arquivo de configuração geral do projeto.

A12. Reservar 25% para a resposta e recortar o texto em torno das ocorrências do nome. Orçar mensagens, instruções, metadados e margem para o contexto interno do agente; contar bytes UTF-8 como aproximação conservadora para o texto. Rejeitar orçamento insuficiente. Uma resposta truncada ou parcial não autoriza aceitar o fragmento como evidência.

A13. Na configuração atual, aceitar somente loopback local ou o encaminhamento SSH, inclusive IPv6 loopback. Validar endereço literal ou todas as resoluções de `localhost`, conferir destino efetivo, desativar proxies de ambiente e redirects. Recusar endereço público, porta interna do llama.cpp, usuário/senha na URL, query e fragmento antes de enviar o Bearer. A aplicação não abre portas na LAN nem encaminha para modelos de nuvem.

A14. Ler `.env` como pares KEY=VALUE sem executar shell nem interpolar variáveis; ambiente explícito tem precedência. Ignorá-lo no Git antes de configurar. Pausa pública padrão de 5 s, mínimo 3 s, limite de 5 MB e timeout de 25 s por página. Manter versão e caminho do índice CNPJ e as configurações do provedor licenciado independentes da busca.

**Contrato de execução** *(escolha minha — A17)*

1. `verificar` faz apenas GET autenticado a `/v1/models` e confere `data[].id`. Informa modelo listado, busca habilitada em configuração e presença do provedor. Nome ausente, 401 e gateway indisponível geram diagnósticos diferentes, com endpoint sanitizado. Esse GET não comprova que as ferramentas estejam habilitadas.
2. Para pesquisar, enviar `POST /v1/responses` com `model=hermes-agent`, a consulta do alvo em `input` e `store=false`, sem histórico compartilhado, ID anterior ou sobrescrita de provedor/modelo. No retorno exigir HTTP de sucesso, `status=completed`, uma chamada `function_call` concluída de nome `web_search`, argumentos dentro da consulta aprovada e um único `function_call_output` com o mesmo `call_id`. A versão testada envolve o JSON da saída em `<untrusted_tool_result …>`; ler o conteúdo como dados, validando o invólucro e um único objeto JSON. Aceitar também o objeto JSON sem invólucro. Exigir `success=true` e lista `data.web`. Extrair `url`, `title` e `description` das linhas válidas. Zero itens em lista válida significa “sem resultados”. Saída truncada, só narrativa, erro da ferramenta ou estrutura incompatível significa falha. Nunca reexecutar localmente uma ferramenta devolvida pelo gateway.
3. Registrar no lote data, ID de resposta, ID da chamada, ferramenta e o backend quando a saída o identifica. Quando o servidor omite a identificação, registrar “não informado”. Persistir os trechos aprovados com hash e URL. A política de retenção de sessões, logs e caches no próprio Hermes precisa integrar a decisão de retenção de Nick; `store=false` isoladamente não demonstra ausência de registros.
4. Separar a pesquisa da leitura de páginas. O gateway deve aplicar **antes da execução** uma política para a integração: na pesquisa permitir uma única `web_search` com os argumentos autorizados para aquele alvo, somente em modalidade gratuita; na leitura, nenhuma ferramenta. O leitor usa `POST /v1/responses`, exige `completed`, uma mensagem final com JSON válido e ausência de chamadas de ferramenta. Entradas recuperadas da web são dados. Instruções em prompt, `tools: []` do cliente e a inspeção posterior da resposta, sozinhas, não asseguram esse isolamento. A API comum do ensaio demonstrou ferramentas disponíveis; o controle prévio por chamada e o bloqueio de rota paga ainda precisam ser demonstrados no gateway instalado. Na implementação, verificar mecanismo suportado de perfil/política ou interceptação de despacho no mesmo gateway com dados fictícios. Enquanto não houver esse controle, a pesquisa nominal fica indisponível com motivo explícito. O modo sem web continua utilizável.
5. Em caso de falha, não reenviar automaticamente um POST que pode já ter executado. O controle de tentativas do aplicativo vale também para a abertura direta de páginas. O Hermes pode alternar motores gratuitos internamente na busca. Não prometer uma consulta física única a um único motor. O ensaio não estabeleceu saldo nem garantia de disponibilidade. Parallel admite uso anônimo leve com controle de frequência. Firecrawl informa tetos diários por IP e HTTP 429 por excedente. [Busca no Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-search) · [Parallel](https://docs.parallel.ai/integrations/mcp/search-mcp) · [Firecrawl](https://www.firecrawl.dev/blog/web-search-api)

O contrato de resposta foi observado no ensaio anterior com uma consulta pública à [IANA](https://www.iana.org/help/example-domains). A implementação deverá tratar o formato como contrato versionado. [API Server do Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)

## 12. Falhas e rede

*(escolha minha)*: requisições sequenciais, pausa, sem retry automático. Bloqueio/captcha/login em página individual: “não consultado” para download, snippet disponível como “não verificado”, seguir lote. Falha/bloqueio de serviço de busca, gateway Hermes, registro ou provedor: parar novas consultas e salvar parcial. Cadastro indisponível não equivale a “sem registro”.

*(escolha minha — A15)*:
| Estado | Significado |
|---|---|
| consultado | requisição e interpretação concluídas; candidato ainda requer confirmação |
| sem_resultados | fonte consultada com sucesso não retornou itens nessa consulta e cobertura |
| nao_consultado | consulta não executada/concluída; motivo obrigatório |
| nao_configurado | slot/índice ausente; busca pode ser pulada, provedor não roda |
| nao_verificado | somente snippet/link ou confirmação manual pendente |
| aguardando_confirmacao | candidato não elegível para contato pago |
| identidade_ambigua | fornecedor retornou múltiplas pessoas; contatos ocultos |
| erro_entrada | CNJ/hash/Excel/CPF/config inválido; corrigir antes de chamadas |
| interrompido | falha de serviço central; restantes não consultados |

CNPJ não configurado deve aparecer como limitação explícita, sem impedir OAB/busca; índice configurado corrompido interrompe. Qualquer captcha reconhecido na OAB gera pendência manual na planilha e o lote continua. Uma indisponibilidade geral do registro é falha de serviço (§12).
HTTP de páginas não aceita cookies; redirects não são seguidos automaticamente (especialmente redes sociais). URLs públicas HTTP(S) têm host validado; recusar IPs locais, endpoints internos e esquemas executáveis para downloads originados de busca. O transporte autenticado do Hermes é exclusivo do loopback. Conteúdo externo é dado, nunca instrução para chamadas ou alteração de escopo.

## 13. Viabilidade para quem construir

Todas as propostas abaixo são *(escolha minha — A16)*; nenhuma foi testada online nesta tarefa.

| Questão | Evidência local e resposta proposta |
|---|---|
| Advogados/OAB/lado sem mudar DJEN | e-SAJ entrega `partes_linhas` como células textuais, sem estrutura garantida. Parser pessoas preserva vínculo apenas quando explícito; complementar com Texto de Publicações. A API DJEN tem `destinatarioadvogados[].advogado.numero_oab`, mas Excel não exporta esse campo. Não reler ~700 MB para recuperá-lo. Se necessário depois, adapter próprio de consulta pontual por processo/publicação, contrato ainda a validar, sem depender dele no MVP. Ausente OAB: busca nominal gera candidatos; lado desconhecido permanece visível. |
| CNPJ por nome de sócio | F13 descreve download completo mensal; não há endpoint nominal assegurado. Proposta: ingestão separada de snapshot oficial em streaming CSV/ZIP para SQLite em disco, índice nome normalizado de sócio → CNPJ básico → empresas/estabelecimentos. Lote só consulta índice pronto. Sem carregar base inteira na RAM de 24 GB; importador junta somente campos necessários, não pesquisa sócios terceiros. Tamanho exato/arquivos/leiaute não verificados: prever dezenas de GB de disco, medir manifestos e espaço antes de baixar/extrair, não fixar promessa. O destino escolhido por Nick é o SSD interno do Studio. O pré-voo considera arquivos compactados, dados temporários, índice SQLite e eventual índice anterior durante a troca. Se o espaço for insuficiente, apresentar a limitação antes da transferência. Refresh explícito por competência mensal, troca atômica, manter data/hash; CPF mascarado nunca desmascarado nem aceito como identidade única. Contrato CSV oficial precisa ser confirmado antes do adapter real; fixtures sintéticas testam contrato interno. |
| OAB sem captcha | Não verificado nos insumos. Adapter com consulta automatizada somente quando acesso simples for confirmado. Em caso de captcha, aplicar a decisão da §8: registrar a pendência na aba OAB e seguir para o próximo alvo. Nick completa a conferência posteriormente. Não simular disponibilidade nem resolver captcha. |
| Outros processos | Cruzar somente linhas de Casos/Publicações do workbook já fornecido e resultados da busca web gratuita; não reler cadernos, não chamar DataJud para nomes (F1 não tem partes), não crawler e-SAJ por pessoa. Nome igual significa candidato. Mostrar cobertura parcial e data. Busca sem configuração: apenas workbook, com limitação. |
| Provedor de contatos | Provedor ainda não escolhido; não inferir que produtos jurídicos F9/F10 fornecem contatos. Exigir documentação de identificadores aceitos (CPF, CNPJ ou nome+cidade/faixa etária), descoberta sem contatos, preço, licença/finalidade e idempotência. CPF-only deixa sem CPF pendente; resposta ambígua exige segunda confirmação. |

Não expandir fontes para IPTU, remuneração pública, protestos, bancos, imóveis ou outros itens F1–F24 nesta implementação. Eles são contexto de pesquisa, não autorização adicional.

## 14. Testes obrigatórios

Sem rede, com dublês de Hermes (busca e leitura), provedor, registros, relógio e transporte; nomes JOÃO EXEMPLO e BANCO EXEMPLO S.A.; arquivos em tmp_path. Cobrir:
- reproduzir respostas sintéticas da API Hermes. Cobrir chamada/saída com `call_id` correspondente, invólucro, resposta apenas textual, chamada ausente/extra, chamada sem par, consulta alterada, ferramenta em erro, 401, timeout, status incompleto e sucesso sem itens;
- demonstrar no despachante falso que pesquisa adicional, terceiro, ferramenta diferente, rota paga e qualquer ferramenta na fase de leitura são recusados antes do efeito. Falta de controle gera indisponibilidade explícita. Verificar que o Bearer não segue para sites nem registros;
- rejeitar URL fora da busca e citação não encontrada; aceitar normalização; snippet apenas quando página indisponível;
- página social com login faz uma tentativa, não segue links, conserva snippet não verificado e segue lote;
- desconhecidos/não/vazio nunca chegam ao provedor; CPF inválido rejeitado antes de cobrança;
- testar autorização de gasto separada, primeira rodada sem fornecedor e marcações preservadas. Simular captcha OAB entre dois alvos e atualização posterior via Excel;
- verificar o resumo inteiro com sentinelas identificadoras em texto, atributos e metadados. Vínculo pendente omite até a faixa de capital. Confirmar o candidato associado libera a faixa somente para seus vínculos documentados.
- testar descarte marcado, cancelado, confirmado, prévia vencida, falha durante a limpeza e reexecução. Conferir todas as saídas, os casos remanescentes e a numeração estável;
- múltiplas pessoas do provedor não exibem nem persistem contatos; confirmação específica libera somente uma;
- URL pública de modelo, redirect e DNS público recusados; servidor indisponível para com URL sanitizada;
- verificar acusa nome ausente/não listado; truncamento respeita contexto e preserva trechos relevantes;
- reexecução conserva Confirmado/CPF, IDs e datas; ambiguidades de Excel e lote diferente não sobrescrevem;
- terminal/erros não imprimem nomes, CPF, contato ou segredo;
- terceiros nunca pesquisados; PJ devedora não dispara busca de seus sócios; advogado de lado desconhecido identificado como tal;
- bloqueio vira não consultado, nunca nada encontrado; falhas centrais param, página isolada não;
- entradas originais permanecem byte a byte iguais; HTML totalmente escapado, hyperlinks seguros e Excel sem fórmulas externas;
- CNPJ snapshot/máscara/refresh e OAB manual; ausência dos slots não inventa resultados;
- end-to-end dois casos fictícios, sem chamadas de rede, sem abrir dados/ ou saida/ reais.

## 15. Perguntas para advogado

**Decisão do Nick.** Antes da primeira pesquisa com nomes reais, encaminhar ao advogado as questões sobre fontes gratuitas, o envio de nome/cidade à busca externa, a coleta anterior à cessão, o resumo do revisor e a exclusão do lote (L11, L12 e L14). O desenvolvimento com casos fictícios pode avançar. Quando houver fornecedor concreto, revisar compra, licença, retenção e contrato (L13) antes de habilitar o gasto. L15 e L16 orientam a abordagem humana no estágio aplicável. A decisão operacional é abordar devedor ou seu advogado somente depois da cessão.
- **L11:** Qual base LGPD e quais limites de finalidade/minimização/retenção para reunir capacidade de pagamento e contatos do devedor antes da cessão, incluindo combinação de emprego, QSA e processos?
- **L12:** Qual base e limites para coletar contatos de credor pessoa física antes da compra?
- **L13:** Que diligência sobre origem, licença, contratos, papéis LGPD e direitos dos titulares é necessária ao comprar contatos para essa finalidade?
- **L14:** Quais limites contratuais e legais para baixar uma página pública LinkedIn/Instagram/Facebook, considerando seus termos, mesmo sem login ou contorno?
- **L15:** Como e em que condições Nick pode abordar o advogado do devedor? Há restrições profissionais, representação ou comunicação com a parte?
- **L16:** Como os arts. 42 e 71 do CDC se aplicam ao momento, conteúdo, canal e frequência de eventual contato humano com o devedor, antes ou depois da cessão?

## 16. Pendências para o Nick

1. Revisar o design atualizado. Antes da rodada nominal, obter a avaliação do advogado sobre a etapa gratuita, o resumo e o alcance do descarte, inclusive cópias externas e retenção do Hermes.
2. Conferir as propostas técnicas A1–A19, em especial as faixas de capital e o modo de confirmar o descarte na prévia.
3. Quando a rodada gratuita indicar necessidade, selecionar o fornecedor, verificar identificadores, preço e orçamento, e levar o contrato à segunda revisão jurídica.
4. Na primeira rodada autorizada, confirmar que a cobertura e os limites da busca gratuita do Hermes atendem ao volume desejado. O mecanismo prévio de restrição da §11 é verificação técnica de quem implementar.
5. Se optar por executar no laptop, validar de lá o túnel e o acesso autenticado. Para execução no Studio, a API local já foi testada.
6. Antes de preparar o índice no SSD interno do Studio, conferir a competência, o leiaute, os tamanhos e o espaço livre. A primeira carga e as consultas reais ficarão para a implementação aprovada.
7. Na rodada autorizada, conferir o leiaute da OAB e se os campos da planilha bastam para a conferência manual.
8. Fazer pessoalmente a primeira rodada gratuita de até dois casos e conferir o comportamento das páginas sociais e a utilidade do resumo do revisor.

## 17. O que fica com quem implementar

Após aprovação, seguir plano test-first. Pode escolher nomes internos, parser de layout, estilos do relatório e índices SQLite equivalentes aos contratos acima. Não pode escolher fornecedor, ampliar alvos/fontes, relaxar confirmação, inventar identidade, mudar fluxo de contato ou resolver pendência jurídica em nome de Nick. Os adapters sem contrato verificado ficam explícitos como não configurados/manuais, com fakes funcionando. Nenhuma execução real faz parte do plano.
