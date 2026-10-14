# Vibrações — análise de vibrações

Aplicação web em português para explorar ensaios CSV de aceleração. FFT com janela Hann, RMS, curtose de Pearson, assimetria, integração espectral de velocidade, estimativa de rotação, média síncrona por volta e envelope de Hilbert. Frequências de rolamento e engrenamento usam os parâmetros informados.

## Resultados em cinco abas

Diagnóstico Geral; Gráfico de Defeitos (espectro com faixas e picos); Gráficos de Análise (onda e FFT brutas, onda e FFT processadas, RMS móvel); Análise de Rolamentos (envelope e referências geométricas); Status de Saúde (polar de 1X, métricas e tabela de faixas). O espectro tem cinco regiões orientativas proporcionais à rotação: 0,8–1,2X (desbalanceamento), 1,8–3,2X (desalinhamento), 3–10X (folga), 10–100X (investigação de rolamentos) e acima de 100X (investigação de lubrificação/atrito). Não são faixas normativas nem frequências geométricas de falha. Regiões fora de Nyquist são identificadas e não desenhadas como se fossem medidas. Referências 1X–10X e picos detectados são marcados separadamente; GMF e referências geométricas só aparecem com parâmetros informados.

A fase de 1X é ajustada na frequência exata da rotação e referida ao início do registro, sem referência física de chave de fase.

## Executar

Requer Python 3.12. Na pasta do repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python app.py
```

Abra http://127.0.0.1:5000. Não há escrita de banco ou criação de diretórios ao importar o app. Recursos de interface, incluindo Plotly 3.1.0, estão em `public/`; nenhuma CDN é necessária em execução.

## CSV

- Até 4 MiB, entre 50 e 200.000 amostras e até 32 colunas.
- Separadores: vírgula, ponto e vírgula, tabulação ou barra vertical. Decimais com vírgula são aceitos quando não conflitam com o separador.
- Cabeçalho opcional; sem cabeçalho, duas ou mais colunas usam a primeira como tempo. A escolha pode ser alterada no formulário.
- Tempo em segundos, estritamente crescente, com variação de intervalo de no máximo 1%.
- Taxa de amostragem inferida do tempo ou lida de metadado; sem ambos, informar manualmente. Divergência superior a 1% entre fontes é recusada.
- Selecionar coluna de aceleração e unidade: m/s², g padrão ou mm/s². Não há conversão automática de arquivos de velocidade/deslocamento.
- Valores ausentes, não numéricos, infinitos, cabeçalhos duplicados e quantidade inconsistente de campos são recusados. Não descarta amostras silenciosamente.
- Tacômetro é opcional e deve ter um pulso por volta. Metadado `Frequencia_Hz` não é tacômetro.

## Como os resultados são calculados

Métricas usam o sinal convertido para m/s² com média removida, sem janela. O espectro usa janela Hann periódica e correção de ganho coerente; amplitude de pico com DC/Nyquist tratados separadamente. Valores espectrais entre bins sofrem leakage/scalloping; resolução é fs/N.

Velocidade é integrada no domínio espectral, limitada à banda declarada (padrão 10–1000 Hz, truncada por Nyquist); DC e Nyquist são excluídos da integração. Para registros não periódicos, efeitos de borda/leakage podem alterar o valor: escolha ensaios representativos e compare com instrumentos/linha de base. O formulário permite comparação orientativa pelos limites 2,8 / 7,1 / 18 mm/s, ativada por padrão e desativável. Não é classificação normativa; a adequação dos limites e da banda depende da máquina. Banda sem bins resolvidos é recusada.

RPM manual prevalece. Na ausência, tacômetro válido é usado; sem ambos, o algoritmo estima uma referência a partir de picos e relações harmônicas. Essa referência pode ser incorreta para sinais com ruído, fontes múltiplas ou fundamental ausente; a interface sempre avisa. Não é medição independente de rotação.

TSA é opcional e exige RPM estável informado ou tacômetro; resultado da média é mostrado na forma de onda e na FFT processada. FFT de diagnóstico, métricas e indícios continuam usando o sinal sem DC para que impactos/energia não síncrona não desapareçam da avaliação global.

Envelope: filtro Butterworth de ordem 4, fase zero, entre 0,1 fs e 0,45 fs; módulo da Hilbert, remoção de média e FFT com Hann. Essa banda automática precisa ser avaliada contra a ressonância portadora do ensaio; não é otimização automática da banda de rolamento.

Regras sinalizam componentes 1X/2X, múltiplos harmônicos e 120 Hz. Não classificam automaticamente ressonância, lubrificação, barras de rotor ou defeito específico de rolamento. Frequências BPFO/BPFI/BSF/FTF e GMF são referências calculadas, não confirmação de falha. Ensaios sem resolução para separar os harmônicos não recebem essas interpretações. Não há probabilidades ou scores calibrados.

## Histórico e privacidade

Resumos ficam em `localStorage` neste navegador, até 200 análises. A tela de tendências mostra contagens por condição registrada, quatro gráficos (velocidade RMS, curtose, amplitude 1X e RPM) e uma tabela com diagnósticos. Linhas agrupam apenas equipamento identificado e mesma banda; registros sem identificação são pontos separados. Amplitude, condição e títulos de diagnósticos são salvos nas novas análises. Registros antigos continuam válidos, com campos ausentes indicados como não registrados, sem preencher com zero. Nenhum histórico global ou rota de exclusão compartilhada. Exportação/importação JSON é validada; gráficos completos são incluídos na exportação individual, mas não no histórico resumido. Limpar dados do navegador remove os resumos; exporte para preservá-los. Pessoas no mesmo perfil do navegador compartilham esse armazenamento local.

Arquivos são processados em memória durante a requisição; o código não os salva no servidor. A infraestrutura de hospedagem continua responsável por seus próprios mecanismos de observabilidade. Os bancos SQLite antigos não são lidos, alterados ou publicados pela versão web. Não há migração automática do histórico legado.

## API

| Endpoint | Uso |
|---|---|
| GET `/` | Interface |
| GET `/api/health` | Versão e estado de importação |
| POST `/api/inspect` | Multipart `arquivo`; devolve colunas e sugestões |
| POST `/api/analyze` | Multipart `arquivo`, seletores, parâmetros; devolve JSON |
| GET `/api/examples/normal` | Seno sintético determinístico |
| GET `/api/examples/harmonicos` | Harmônicos sintéticos |
| GET `/api/examples/impactos` | Impactos sintéticos |

Campos de análise: `signal_column`, `time_column`, `tach_column` (`__none__` desativa tempo/tac), `unit`, `sampling_frequency`, `rpm_manual`, `machine`, `n`, `d`, `p`, `theta`, `num_dentes`, `velocity_min`, `velocity_max`, `tsa=on`, `health_reference=orientative` (opcional). Parâmetros geométricos são todos opcionais em conjunto. Erros de dados retornam 400; limite de tamanho 413. Sem sinal de demonstração em substituição a falhas.

Gráficos retornam no máximo 2000 pontos por curva, preservando extremos ou picos por intervalo. FFT/métricas usam todas as amostras. Essa redução limita o detalhe visual e deve ser considerada ao ampliar o gráfico.

## Testes

```powershell
.\.venv\Scripts\python -m pytest -q
npm ci --ignore-scripts
npm test
```

Testes determinísticos cobrem importação, conflitos, unidades/referências, métricas conhecidas, TSA, geometria, rotas, erros, limites e coleta dos controles reais do formulário em DOM simulado. CI executa Python e Node. Aprovação desses testes não certifica acurácia de diagnóstico em máquinas reais.

## Publicar no Vercel

Projeto existente: `vibration-analysis-dashboard`, equipe `claudioalexandreclaudio427-3093s-projects`. Framework Flask; Python 3.12; entrada `app:app`. O Vercel serve `public/` diretamente e instala `requirements.txt`. O antigo arquivo com `builds`/`routes` foi substituído pela configuração nativa.

```text
vercel login
vercel link --yes --team claudioalexandreclaudio427-3093s-projects --project vibration-analysis-dashboard
vercel deploy --prod
```

Excluir ambientes, bancos, caches, executáveis e testes do upload/bundle conforme `.vercelignore` e `vercel.json`. Não usar SQLite local como histórico persistente em função. Não é necessário configurar chave de sessão ou banco externo para esta versão. Não fazer download de variáveis secretas para publicar.

Teto de upload da função Vercel é 4,5 MB por requisição; esta aplicação limita o arquivo a 4 MiB com margem para o multipart. Para arquivos maiores, uma futura versão exige upload externo ou processamento local. Consultar [Flask no Vercel](https://vercel.com/docs/frameworks/backend/flask) e [limites](https://vercel.com/docs/functions/limitations) antes de mudar configuração.

## Estrutura

`csv_io.py`: contrato CSV/ensaio; `analise_vibracoes.py`: numérico; `analysis_service.py`: pipeline e resposta; `app.py`: HTTP; `utils.py`: parsing/validações; `templates/index.html`, `public/app.css`, `public/app.js`: interface. `config.py`, specs e `testes.py` são material legado; o serviço web não depende deles. O legado desktop original foi preservado fora do clone em `../V17`.
