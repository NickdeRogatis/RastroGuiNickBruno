# Pesquisa de pessoas nos casos selecionados — design

- **Data:** 23/11/2026
- **Status:** rascunho para aprovação do Nick; implementação em tarefa separada.
- **Base:** designs de 08/11 (§§1–7) e 22/11 (§§1 e 3), ExecucoesSP_FontesEPlano.html (§§2, 7 e 8), código e testes de aprofundamento.
- **Escopo desta entrega:** somente este documento e o plano; nenhuma consulta real ou alteração de produto.

Convenção: **decisão do Nick** registra o que ele decidiu; *(escolha minha)* registra decisões de refinamento e propostas de implementação para conferência. As notas de viabilidade são inferências da documentação local, não verificações atuais de sites. Nenhum dado de dados/ ou saida/ foi lido.

## 1. Intenção e porquê

Depois de escolher casos no DJEN e aprofundá-los no e-SAJ, Nick quer saber quem são as partes, se há indícios de capacidade de pagamento do devedor e como chegar às pessoas relevantes. O negócio é comprar o crédito com desconto e renegociar em condições mais gentis. A reunião de 13/11 mudou o foco do score para capacidade e histórico de pagar; esta etapa oferece evidências para julgamento humano, sem recalcular esse score.

A pesquisa começa após a seleção de até dez casos, usando a seleção do aprofundamento. Não é preciso comprar a dívida antes de coletar qualquer informação prevista aqui, inclusive contatos (**decisão do Nick**). Isso descreve o produto desejado, não uma conclusão sobre base legal: as dúvidas estão em L11–L16.

## 2. Objetivos

Duas passagens (**decisão do Nick**):
1. `pesquisar`: fontes gratuitas para identificar candidatos e reunir indícios de capacidade de pagamento.
2. `contatos`: provedor pago para os candidatos cuja identidade Nick confirmou.

Entregar HTML legível, Excel editável para confirmação e JSON por processo. Todos os achados começam como candidatos; confiança alta não substitui confirmação (**decisão do Nick**).

Critério de aceite *(escolha minha)*: lote fictício com dois casos percorre as duas passagens com fontes falsas, preserva os arquivos de entrada e as decisões humanas, distingue indisponibilidade de ausência de achados e nunca revela contatos de candidatos ambíguos do provedor.

## 3. Não-objetivos

Não alterar DJEN, aprofundamento, score, ranking ou arquivos existentes. Não implementar cessão, negociação, cobrança, agendamento, avaliação patrimonial completa, salário estimado, saldo da dívida ou garantias de solvência. Não criar cliente Hermes. Não implementar uma busca exaustiva de processos ou acesso a autos restritos.

O programa nunca envia mensagens, e-mails, chamadas, pedidos de amizade ou qualquer contato (**decisão do Nick**). A decisão de contato fica com Nick.

## 4. Anti-objetivos e fronteiras

Pesquisar apenas devedores, credores PF/PJ em igualdade de tratamento, e advogados de ambos os lados (**decisão do Nick**). Nunca pesquisar familiares, vizinhos, amigos ou sócios que não sejam partes; nunca navegar a rede de relacionamentos.

Sobre o devedor, coletar emprego/empregador em páginas profissionais públicas; participações societárias, situação e capital declarado das empresas; outros processos homônimos; links públicos Instagram/Facebook como indícios de identidade, cidade ou empregador. Não catalogar posts, fotos, estilo de vida ou conexões (**decisão do Nick**).

Sobre credores e advogados: contatos públicos, inclusive dados profissionais do cadastro OAB; contatos pagos apenas após confirmação. O provedor oferece endereço, telefone/WhatsApp e e-mail (**decisão do Nick**). Um telefone não será rotulado WhatsApp sem indicação da fonte *(escolha minha)*.

Capital social não equivale a patrimônio pessoal disponível; emprego não prova renda; homonímia não prova identidade; ausência de resultados não prova falta de capacidade de pagamento *(escolha minha)*. Nunca promover inferências do modelo a fatos sem evidência.

## 5. Regras que mudam

| Regra anterior | Substituição nesta etapa |
|---|---|
| 08/11 §4: não virar lista de abordagem; sem contatos, telefone ou e-mail | Coletar contatos de devedor, credor e advogados antes da compra; nenhuma abordagem automática (**decisão do Nick**). |
| 08/11 §4: nomes nunca enviados a serviços externos | Nomes podem ir à busca, sites públicos e registros; nome ou CPF ao provedor. Modelo somente nas máquinas do Nick (**decisão do Nick**). |
| 08/11 §§4–5: não raspar tribunal; DJEN fonte única | Aprofundamento já acrescentou e-SAJ; pessoas acrescenta páginas públicas e registros. Isso não autoriza burlar bloqueios nem afirma permissão jurídica de raspagem (**decisão do Nick**). |
| 22/11 §3: provedores fora; consulta só nos 2–3 casos comprados | Provedor pago de contatos para pessoas confirmadas dos casos selecionados, antes da compra (**decisão do Nick**). |
| 08/11 §1: falar com devedor só depois de virar credor | O sistema passa a possuir contatos antes da compra. Mudança na ordem do contato humano não foi decidida: pendência para Nick (**decisão do Nick** quanto à coleta). |

A fronteira de terceiros da seção 7 do documento de 26/10 continua. Bases vazadas continuam fora. Nenhuma mudança neste documento altera retroativamente o funcionamento das duas etapas existentes.

## 6. Abordagens e estrutura

Escolhido: novo módulo `src/guicredito/pessoas/`, testes `tests/pessoas/`, comandos próprios (**decisão do Nick**).
Alternativas consideradas:
- Subcomandos no aprofundamento: misturam contatos em uma etapa documentada como dados processuais públicos, exigindo reescrever testes e READING.
- Repositório separado: separação de dados mais forte, mas duplica CNJ, seleção e manutenção.

*(escolha minha — A1)*: dividir responsabilidades em `modelos.py`, `entrada.py`, `identidade.py`, `config.py`, `http.py`, `modelo.py`, `fontes.py`, `cnpj.py`, `oab.py`, `evidencias.py`, `planilha.py`, `relatorio.py`, `fluxo.py` e `__main__.py`. Usar dataclasses/Protocol, urllib, sqlite3 e demais módulos padrão; openpyxl e certifi já estão instalados. Nenhuma dependência nova.

Reutilizar somente utilitários públicos e puros: normalização textual do DJEN, classificação de empresa/cabeçalho e validação CNJ/seleção do aprofundamento; não chamar sua coleta nem seu gravador de lote. A regra de três palavras em `_nomes_para_cruzar` pertence ao score. Não importar essa função privada: JOÃO EXEMPLO, nome de duas palavras, deve poder aparecer como candidato sem confirmação automática *(escolha minha — A2)*.

## 7. Entrada e contrato de dados

*(escolha minha — A3)*: `pesquisar --selecao <json> --aprofundamento <pasta> --planilha <xlsx> --saida <lote>`; todos os caminhos explícitos, evitando pegar uma rodada por acidente. Seleção versão 1 contém `casos` com `numero_processo`, `posicao_original`, `pontuacao_original`, além de `origem_planilha` e `selecionado_em`. Validar 1–10 CNJs sem repetição.

Ler somente os resultados dos CNJs selecionados e linhas correspondentes das abas Casos e Publicações. Conferir CNJ do resultado, manifestos e hashes das evidências utilizadas. Nunca seguir automaticamente `processo_principal_texto`: incidente é processo próprio. Ausência de capa vira limitação registrada; divergência ou hash inválido interrompe antes de pesquisa. A planilha original tem Credor, Devedor, Comarca, Trecho principal, mas não OAB estruturada. Publicações tem Processo, Data, Tipo, Órgão e Texto.

*(escolha minha — A4)*: dados versionados:
- alvo: id estável, CNJ, papel, tipo PF/PJ, nome original, fonte do papel;
- candidato: id, alvo_id, fonte/chave externa, nome, confiança, indícios, conflitos, status de verificação;
- evidência: id, URL, data UTC, fonte, trecho, tipo página/snippet/registro/manual, arquivo e SHA-256;
- confirmação: candidato_id, sim/não/vazio, CPF opcional, data da leitura do Excel;
- consulta: fonte, estado, motivo, horário, versão do extrator;
- contato: candidato confirmado, identificador do provedor, valor, tipo, origem/data, sem afirmar atualidade além do que o fornecedor informa.

IDs persistentes independem da ordem das linhas. Não fundir automaticamente duas pessoas por nome. Relações entre processos usam referências; as decisões continuam vinculadas ao candidato e à evidência daquele lote.

## 8. Passagem 1 — pesquisar

1. Validar entradas; extrair alvos das partes, complementando com texto do Excel. Todo PF no polo devedor entra: executado, réu, avalista, fiador, coobrigado *(escolha minha)*. PJ devedora recebe só seu cadastro, situação e capital; seus sócios não viram alvos. Credor PJ não autoriza buscar seus donos.
2. Parser próprio de advogados em pessoas interpreta nomes, OAB e vínculo com a parte; sem vínculo comprovável, mostrar “lado desconhecido” *(escolha minha)*. Não pesquisar testemunhas ou nomes meramente citados.
3. CNPJ local e cadastro OAB oferecem candidatos e evidências. Contatos gratuitos de credor/advogado ficam separados de contatos pagos *(escolha minha)*.
4. Serviço de busca ainda não escolhido (**decisão do Nick**). Interface `buscar(consulta) -> resultados(url, titulo, snippet)`, com fake. Sem configuração: “busca não configurada”, pular pesquisa web; registros continuam.
5. Código pesquisa emprego/empregador, perfis públicos e outros processos; baixa páginas. Modelo não navega, não escolhe ferramentas nem dispara requisições *(escolha minha)*.
6. Cada link LinkedIn/Instagram/Facebook recebe UMA tentativa simples: sem login, cookies/sessão, resolver captcha, seguir links internos ou retries. Parede de login, bloqueio ou erro: guardar título, snippet e URL do resultado, “não verificado — conferir no navegador”, continuar (**decisão do Nick**). Sem snippet útil, apenas link sem achado.
7. Modelo propõe candidatos a partir do texto recebido. Rejeitar URL ausente dos resultados de busca do lote e trecho que não ocorra na página baixada, comparando com `normalizar`; somente para download indisponível aceitar trecho do snippet. Snippet é sempre não verificado *(escolha minha)*. Registros estruturados seguem validadores próprios; não são obrigados a aparecer no buscador.
8. Salvar evidências aceitas com data/hash e produzir relatório/Excel; nada conta como identidade confirmada antes da marca humana.

*(escolha minha — A5)*: confiança baixa para nome isolado; média para nome mais um indício independente compatível (cidade, empregador, endereço do processo ou faixa etária); alta para dois indícios independentes compatíveis, sem conflitos. Conflitos explícitos reduzem a baixa. Exibir todos os candidatos retornados pelas consultas executadas, inclusive baixa confiança e sem limite silencioso. Registrar paginação/limite do serviço; não prometer todos os homônimos existentes.

*(escolha minha — A6)*: não guardar páginas sociais integrais com fotos/posts/conexões. Extrair texto relevante à identidade, guardar esse recorte e hash dele; hash do corpo transitório pode registrar integridade, sem persistir o corpo. Citações são verificadas no texto efetivamente recebido antes da minimização. Relatório distingue evidência de identidade de indício econômico.

## 9. Passagem 2 — contatos

*(escolha minha)*: só pessoas com `Confirmado = sim` podem gerar consultas pagas. Ler workbook salvo antes de qualquer chamada. CPF opcional deve passar formato, dois dígitos verificadores e rejeição de sequências repetidas; CPF inválido interrompe a validação da passagem, sem cobrança.

Interface do provedor ainda não escolhido (**decisão do Nick**): `identificar(identidade_confirmada)` e `obter_contatos(id_confirmado)`. Sem provedor: “provedor não configurado”, parar sem consultas. Usar CPF informado; sem CPF, nome e indícios confirmados (cidade/faixa etária). Se fornecedor exigir CPF, marcar “identificador necessário”, nunca adivinhar.

*(escolha minha — A7)*: quando o fornecedor retorna várias identidades, persistir apenas IDs opacos e indícios mínimos de desambiguação, sem contatos, CPF integral ou resposta bruta. Gerar candidatos na aba Provedor; Nick confirma um, salva e executa contatos novamente. Validar que o candidato pertence ao alvo confirmado. Somente então buscar/persistir contatos. Exigir fornecedor com descoberta separada de contatos ou projeção equivalente; contrato que só devolve contatos em massa é incompatível com esta garantia e fica pendente de escolha. Não logar payload bruto nem armazenar contatos descartados.

Credores PF/PJ e advogados também podem usar o provedor após confirmação; PJ usa CNPJ validado derivado do registro confirmado, nunca CPF inventado *(escolha minha — A8)*. Se o fornecedor não suporta PJ, registrar capacidade não disponível. Licenciamento e finalidade precisam ser compatíveis; não escolher fornecedor nesta entrega.

## 10. Excel, HTML, JSON e repetição

Arquivos por lote em `saida/pessoas/<lote>/`: `relatorio.html`, `pessoas.xlsx`, `<CNJ>/*.json` (**decisão do Nick**). Não modificar ranking nem arquivos do aprofundamento.

*(escolha minha — A9)*: abas:
- **Candidatos**: Lote, Alvo ID, Candidato ID, Processo, Papel, Tipo, Nome, Confiança, Cidade, Empregador, Faixa etária, Evidências IDs, URLs, Verificação, **Confirmado**, **CPF**.
- **Provedor**: Alvo ID, Candidato ID de origem, Provedor ID, Nome candidato, Indícios mínimos, **Confirmado**. Sem contatos antes da confirmação específica.
- **Evidências**: ID, Candidato ID, Categoria, Fonte, URL, Data, Trecho, SHA-256, Estado.
- **Contatos**: Candidato ID, Origem, Tipo, Valor, Data da fonte, Data da consulta; somente dados públicos permitidos ou pagos confirmados.
- **Como ler**: limitações, legendas, instrução de salvar/fechar Excel, contagens e fontes não consultadas.

Nick edita somente Confirmado (sim/não/vazio) e CPF na aba Candidatos, e Confirmado em Provedor. CPF é texto para preservar zeros. IDs e demais colunas não são autoridade para ampliar a seleção: comparar com manifesto local; rejeitar IDs desconhecidos, duplicados, confirmações incompatíveis e fórmulas nos campos editáveis antes de chamadas. Alterações inesperadas geram erro, sem sobrescrever Excel.

*(escolha minha — A10)*: por CNJ, `pessoas.json`, `consultas.json`, `evidencias.json`, `contatos.json` e recortes `evidencia-<id>.txt`; manifesto do lote contém versões, hashes de entrada e identidade da seleção, sem segredos. Escrita atômica e bloqueio de lote contra duas execuções simultâneas. Ao repetir, ler Excel primeiro, mesclar por IDs estáveis e preservar Confirmado/CPF; não reaproveitar confirmação em candidato diferente. Arquivo aberto/erro de gravação interrompe sem perder versão anterior. Reutilizar evidência e consultas pagas concluídas com data original; atualização usa novo lote. Mudança de entrada/seleção incompatível exige outro lote. Não repetir automaticamente pedido pago de resultado incerto: exigir conciliação pelo ID da requisição antes.

HTML escapa todo texto e atributos, aceita hyperlinks apenas HTTP(S), não incorpora scripts/HTML das fontes. Excel escreve conteúdo externo como texto, evitando execução de fórmulas *(escolha minha — A11)*. Terminal imprime somente contagens e caminho do relatório; diagnósticos de configuração podem nomear endpoint sanitizado e chaves ausentes, nunca nomes, CPFs, contatos, snippets ou segredos *(escolha minha)*.

## 11. Conexão com o Mac Studio

Laptop do Nick (24 GB) executa pessoas; Mac Studio (64 GB) serve **Qwen3.6-35B-A3B-UD-Q4_K_M**. Cliente chama diretamente servidor OpenAI-compatible, o mesmo usado por Hermes: `/v1/models`, `/v1/chat/completions`. Não passa por Hermes (**decisão do Nick**).

*(escolha minha)*: configuração local .env:
- `PESSOAS_MODELO_URL`: base terminando /v1; exemplo http://<mac-studio>.local:<porta>/v1. Portas exemplificativas dependem do servidor (LM Studio 1234, Ollama 11434, llama.cpp 8080), não são autodetectadas.
- `PESSOAS_MODELO_NOME`: ID exato listado pelo servidor.
- `PESSOAS_MODELO_TIMEOUT`: segundos.
- `PESSOAS_MODELO_CONTEXTO`: janela configurada no servidor.
- slots de busca/provedor, URLs e chaves quando escolhidos.

*(escolha minha — A12)*: timeout padrão 180 s; contexto obrigatório, sem adivinhar capacidade. Reservar 25% para saída, contar conservadoramente UTF-8 bytes como limite superior de tokens do texto, incluindo instruções e metadados; truncar em janelas ao redor do nome. Se instruções/reserva excedem janela, falhar configuração. Validar depois com tokenizer do servidor se disponível sem dependência nova; teste deve provar limite e retenção de trecho do nome. Não enviar página inteira quando excede limite.

*(escolha minha)*: `verificar` chama somente /v1/models, valida modelo configurado e informa se busca/provedor estão configurados, sem pessoas nem chamadas aos provedores. Nome ausente ou não listado é erro explícito. Servidor inacessível interrompe lote com URL sanitizada, nunca “nada encontrado”. Busca não configurada pode ser pulada com registros funcionando; modelo indisponível ao ser necessário interrompe lote preservando o já coletado.

*(escolha minha — A13)*: aceitar localhost, *.local ou IP privado; validar resolução DNS de *.local/localhost para loopback ou faixas privadas RFC1918/IPv6 ULA, não apenas `is_private` genérico. Recusar URL com usuário/senha, query, fragmento e host público; desabilitar redirects do modelo; validar endereço efetivo antes da conexão para impedir mudança DNS para IP público. Nenhum fallback para modelo na nuvem. Nomes podem sair para busca/registros/provedor, mas nunca para modelo externo.

*(escolha minha — A14)*: .env lido por parser simples KEY=VALUE (sem shell, interpolação ou execução), ambiente explícito tem precedência. Primeira tarefa de implementação acrescenta .env a .gitignore antes de qualquer configuração. Segredos nunca em manifesto, relatório ou exceções. Configurações adicionais: intervalo padrão 5 s, mínimo 3 s; limite de página 5 MB; timeout web 25 s; caminho/versionamento do índice CNPJ. Configuração do provedor/busca é validada pelo respectivo adapter; ausente é diferente de malformada.

## 12. Falhas e rede

*(escolha minha)*: requisições sequenciais, pausa, sem retry automático. Bloqueio/captcha/login em página individual: “não consultado” para download, snippet disponível como “não verificado”, seguir lote. Falha/bloqueio de serviço de busca, modelo, registro ou provedor: parar novas consultas e salvar parcial. Cadastro indisponível não equivale a “sem registro”.

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

CNPJ não configurado deve aparecer como limitação explícita, sem impedir OAB/busca; índice configurado corrompido interrompe. OAB com captcha conhecido usa caminho manual declarado; bloqueio inesperado interrompe registro/lote e oferece alternativa manual, sem tentar contornar.
HTTP de páginas não aceita cookies; redirects não são seguidos automaticamente (especialmente redes sociais). URLs públicas HTTP(S) têm host validado; recusar IPs locais, endpoints internos e esquemas executáveis para downloads originados de busca. O cliente do modelo tem política local separada. Conteúdo externo é dado, nunca instrução para chamadas ou alteração de escopo.

## 13. Viabilidade para quem construir

Todas as propostas abaixo são *(escolha minha — A16)*; nenhuma foi testada online nesta tarefa.

| Questão | Evidência local e resposta proposta |
|---|---|
| Advogados/OAB/lado sem mudar DJEN | e-SAJ entrega `partes_linhas` como células textuais, sem estrutura garantida. Parser pessoas preserva vínculo apenas quando explícito; complementar com Texto de Publicações. A API DJEN tem `destinatarioadvogados[].advogado.numero_oab`, mas Excel não exporta esse campo. Não reler ~700 MB para recuperá-lo. Se necessário depois, adapter próprio de consulta pontual por processo/publicação, contrato ainda a validar, sem depender dele no MVP. Ausente OAB: busca nominal gera candidatos; lado desconhecido permanece visível. |
| CNPJ por nome de sócio | F13 descreve download completo mensal; não há endpoint nominal assegurado. Proposta: ingestão separada de snapshot oficial em streaming CSV/ZIP para SQLite em disco, índice nome normalizado de sócio → CNPJ básico → empresas/estabelecimentos. Lote só consulta índice pronto. Sem carregar base inteira na RAM de 24 GB; importador junta somente campos necessários, não pesquisa sócios terceiros. Tamanho exato/arquivos/leiaute não verificados: prever dezenas de GB de disco, medir manifestos e espaço antes de baixar/extrair, não fixar promessa. Nick escolhe preparação e local do snapshot. Refresh explícito por competência mensal, troca atômica, manter data/hash; CPF mascarado nunca desmascarado nem aceito como identidade única. Contrato CSV oficial precisa ser confirmado antes do adapter real; fixtures sintéticas testam contrato interno. |
| OAB sem captcha | Não verificado nos insumos. Adapter com consulta automatizada somente quando acesso simples for confirmado. Alternativa implementável: link do cadastro e entrada manual de nome/OAB/UF/dados profissionais com URL/data e marcação manual. Não simular disponibilidade nem resolver captcha. |
| Outros processos | Cruzar somente linhas de Casos/Publicações do workbook já fornecido e resultados da busca web gratuita; não reler cadernos, não chamar DataJud para nomes (F1 não tem partes), não crawler e-SAJ por pessoa. Nome igual significa candidato. Mostrar cobertura parcial e data. Busca sem configuração: apenas workbook, com limitação. |
| Provedor de contatos | Provedor ainda não escolhido; não inferir que produtos jurídicos F9/F10 fornecem contatos. Exigir documentação de identificadores aceitos (CPF, CNPJ ou nome+cidade/faixa etária), descoberta sem contatos, preço, licença/finalidade e idempotência. CPF-only deixa sem CPF pendente; resposta ambígua exige segunda confirmação. |

Não expandir fontes para IPTU, remuneração pública, protestos, bancos, imóveis ou outros itens F1–F24 nesta implementação. Eles são contexto de pesquisa, não autorização adicional.

## 14. Testes obrigatórios

Sem rede, com fake modelo, busca, provedor, registros, relógio e transporte; nomes JOÃO EXEMPLO e BANCO EXEMPLO S.A.; arquivos em tmp_path. Cobrir:
- rejeitar URL fora da busca e citação não encontrada; aceitar normalização; snippet apenas quando página indisponível;
- página social com login faz uma tentativa, não segue links, conserva snippet não verificado e segue lote;
- desconhecidos/não/vazio nunca chegam ao provedor; CPF inválido rejeitado antes de cobrança;
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

Continuam L1–L10 do documento de 26/10; estas perguntas não presumem autorização jurídica:
- **L11:** Qual base LGPD e quais limites de finalidade/minimização/retenção para reunir capacidade de pagamento e contatos do devedor antes da cessão, incluindo combinação de emprego, QSA e processos?
- **L12:** Qual base e limites para coletar contatos de credor pessoa física antes da compra?
- **L13:** Que diligência sobre origem, licença, contratos, papéis LGPD e direitos dos titulares é necessária ao comprar contatos para essa finalidade?
- **L14:** Quais limites contratuais e legais para baixar uma página pública LinkedIn/Instagram/Facebook, considerando seus termos, mesmo sem login ou contorno?
- **L15:** Como e em que condições Nick pode abordar o advogado do devedor? Há restrições profissionais, representação ou comunicação com a parte?
- **L16:** Como os arts. 42 e 71 do CDC se aplicam ao momento, conteúdo, canal e frequência de eventual contato humano com o devedor, antes ou depois da cessão?

## 16. Pendências para o Nick

1. Aprovar mudanças de regras e encaminhar L11–L16 ao advogado; definir retenção, exclusão e acesso aos dados.
2. Decidir se a ordem do contato humano muda; obter contatos antes da compra não decide isso.
3. Escolher provedor: licença/finalidade, preço/orçamento, identificadores e descoberta sem contatos ambíguos; CPF-only deixará casos pendentes.
4. Escolher busca gratuita e confirmar qual serviço testado com Hermes pode preencher o slot, seus limites e credenciais.
5. Informar URL LAN, ID exato do modelo, janela de contexto e autenticação eventualmente exigida pelo servidor Mac Studio.
6. Escolher local/espaço e preparação do snapshot CNPJ; confirmar leiaute/volume e rotina de atualização antes do adapter real.
7. Confirmar acesso simples ao cadastro OAB ou aceitar operação manual inicial.
8. Conferir escolhas minhas A1–A16 e defaults marcados; fazer a primeira execução real pessoalmente, começando com dois casos, e revisar comportamento de páginas sociais.

## 17. O que fica com quem implementar

Após aprovação, seguir plano test-first. Pode escolher nomes internos, parser de layout, estilos do relatório e índices SQLite equivalentes aos contratos acima. Não pode escolher fornecedor, ampliar alvos/fontes, relaxar confirmação, inventar identidade, mudar fluxo de contato ou resolver pendência jurídica em nome de Nick. Os adapters sem contrato verificado ficam explícitos como não configurados/manuais, com fakes funcionando. Nenhuma execução real faz parte do plano.
