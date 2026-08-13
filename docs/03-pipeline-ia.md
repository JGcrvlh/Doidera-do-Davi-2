# 03 — Pipeline de IA

```
Screen Capture → OCR → Question Detection → Context Extraction
      → Company Research → Job Analysis → LLM → Suggested Answer
```

A regra de ouro do pipeline: **cada etapa produz um objeto tipado (Pydantic) que é o único insumo da etapa seguinte**. Nada de passar "o texto da tela" cru de ponta a ponta — cada estágio refina e reduz o dado. Isso dá três coisas: testabilidade (cada etapa testável isolada), privacidade (o que chega ao LLM é o mínimo necessário) e evolução (trocar OCR ou fonte de captura não afeta o resto).

## Etapa 1 — Screen Capture

**Entrada:** hotkey do usuário.
**Saída:** `RawCapture { image, window_title, process_name, timestamp, monitor }`

- Captura **a janela ativa** (não o monitor todo) sempre que o SO permitir — menor superfície de dado sensível.
- Antes de prosseguir, o **filtro de escopo** roda: se `window_title`/`process_name` não parecem contexto de candidatura (lista de padrões configurável: LinkedIn, Gupy, Greenhouse, Lever, Workday, "vaga", "careers"...), o overlay pergunta "Analisar esta janela mesmo assim?" em vez de seguir sozinho.
- A imagem vive só em memória e é **descartada imediatamente após o OCR**.

## Etapa 2 — OCR

**Entrada:** `RawCapture`
**Saída:** `OcrResult { blocks: [{text, bbox, confidence}], full_text }`

- RapidOCR local. Os *bounding boxes* importam: a posição relativa dos blocos é o que permite, na etapa seguinte, distinguir "label de campo acima de um textarea" de "parágrafo da descrição da vaga".
- Normalizações locais: juntar linhas quebradas, corrigir hifenização, filtrar blocos de confiança < 0,4 (ruído de ícones).
- Otimização de custo/latência: um **hash perceptual** da tela é comparado com a última captura; se a tela quase não mudou, reaproveita o OCR anterior.

## Etapa 3 — Question Detection

**Entrada:** `OcrResult`
**Saída:** `ScreenAnalysis`

```python
class ScreenAnalysis(BaseModel):
    questions: list[DetectedQuestion]   # pode haver mais de uma na tela
    job_signals: JobSignals             # trechos que descrevem a vaga, se visíveis
    platform_hint: str | None           # "linkedin", "gupy", ...

class DetectedQuestion(BaseModel):
    text: str                           # a pergunta, limpa
    kind: Literal["open_text", "motivation", "experience",
                  "behavioral", "technical", "salary",
                  "availability", "multiple_choice", "other"]
    char_limit: int | None              # "máx. 500 caracteres" detectado na tela
    options: list[str] | None           # para múltipla escolha
```

Duas camadas, da mais barata para a mais cara:

1. **Heurísticas locais** (resolvem a maioria): interrogação no fim de linha; verbos imperativos típicos ("Descreva", "Conte", "Explique", "Por que"); labels seguidos de área vazia grande (via bbox); marcadores de obrigatoriedade; padrões conhecidos por plataforma.
2. **Haiku 4.5** para o que sobrar ambíguo: recebe o texto (já **redigido** pelo Redactor) e devolve `ScreenAnalysis` via structured output. Um structured output com schema estrito elimina parsing frágil.

Se nada for detectado, o pipeline para aqui com um aviso discreto — sem gastar tokens de geração.

## Etapa 4 — Context Extraction (o `JobContext`)

**Entrada:** `ScreenAnalysis` + histórico da sessão + telas anteriores da mesma vaga
**Saída:** `JobContext` — o objeto central do sistema:

```python
class JobContext(BaseModel):
    company: str | None
    company_domain: str | None          # chave do cache de pesquisa
    role_title: str | None
    seniority: Literal["intern", "junior", "mid", "senior",
                       "staff", "manager", "unknown"]
    requirements: list[str]             # "3+ anos de Python", "inglês avançado"...
    technologies: list[str]             # ["python", "django", "aws"]
    responsibilities: list[str]
    job_description_summary: str | None
    culture_signals: list[str]          # o que a PRÓPRIA vaga diz de cultura
    source_confidence: float            # quanto disso veio da tela vs. inferência
    completeness: float                 # dispara re-extração quando baixo
```

Pontos de projeto:

- **O contexto é acumulativo por vaga, não por captura.** A descrição da vaga raramente está na mesma tela da pergunta. O usuário captura a página da vaga uma vez (ou o sistema aproveita `job_signals` de capturas anteriores) e o `JobContext` vai sendo **fundido**: campos novos preenchem lacunas, conflitos ficam com a versão de maior confiança. Persistido em SQLite, chaveado por `(empresa, cargo)`.
- Extração via **Haiku + structured output**, com instrução explícita de não inventar: campo ausente fica `None`/lista vazia — `completeness` baixo é sinal para a UI sugerir "capture a página da descrição da vaga para melhorar as respostas".
- Se o usuário colar a URL ou o texto da vaga manualmente (atalho na UI), isso entra como fonte de maior confiança.

## Etapa 5 — Company Research

**Entrada:** `JobContext.company` / `company_domain`
**Saída:** `CompanyProfile`

```python
class CompanyProfile(BaseModel):
    name: str
    summary: str                        # o que a empresa faz, mercado, porte
    products: list[str]
    tech_stack_public: list[str]        # o que é público (blog de eng., vagas)
    values_culture: list[SourcedClaim]  # cada item carrega a fonte
    recent_news: list[SourcedClaim]
    researched_at: datetime
    sources: list[str]                  # URLs

class SourcedClaim(BaseModel):
    claim: str
    source_url: str
    source_date: str | None
```

Como funciona e como evitar lixo/desatualização:

- **Uma chamada ao Claude com a web search tool server-side** (`web_search_20260209`) e um prompt de pesquisa direcionado: "site oficial, página de carreiras/cultura, blog de engenharia, notícias recentes; **priorize fontes primárias** (a própria empresa) sobre agregadores; registre a URL e a data de cada afirmação". A versão 20260209 da tool filtra resultados irrelevantes antes de entrarem no contexto.
- **Toda afirmação carrega fonte** (`SourcedClaim`). Sem URL, a afirmação é descartada na validação do structured output. Isso resolve o problema da informação inventada *sobre a empresa* pelo mesmo mecanismo usado para o perfil do usuário.
- **Desatualização**: instrução para preferir conteúdo recente e registrar `source_date`; claims de notícia com mais de ~18 meses são marcados como "histórico" e o gerador é instruído a não tratá-los como atuais. Cache com **TTL de 7 dias** por domínio — dentro do TTL, zero custo e zero latência; a UI mostra "pesquisado há X dias" com botão de atualizar.
- **Ambiguidade de nome** ("Nubank" é fácil; "Atlas" não): a busca inclui o domínio (extraído da URL da vaga quando disponível) e o setor inferido do `JobContext`; se a confiança ficar baixa, o overlay pede confirmação ("É esta empresa? atlas.com.br — fintech") em vez de pesquisar a empresa errada.
- **Relevância na geração**: o `CompanyProfile` inteiro não entra no prompt final — entra um recorte: valores/cultura sempre; produtos/stack só quando a pergunta é técnica ou de motivação; notícias só se recentes e pertinentes. Menos contexto irrelevante = respostas mais focadas e menos tokens.

## Etapa 6 — Job Analysis (cruzamento vaga × perfil)

**Entrada:** `JobContext` + `UserProfile`
**Saída:** `FitAnalysis { matched: [(requisito, fato_do_perfil)], gaps: [...], angle: str }`

Etapa pequena mas importante: antes de escrever, o sistema decide **o ângulo da resposta** — quais experiências suas casam com quais requisitos, e quais lacunas não devem ser escondidas (mencionar honestamente ou contornar sem mentir). Roda junto com a geração (mesma chamada, como primeiro campo do structured output) para não pagar uma chamada extra; separá-la é otimização futura.

## Etapa 7 — Geração da resposta

**Entrada:** tudo acima + a pergunta atual + preferências do usuário (tom, idioma, limite de caracteres)
**Saída:**

```python
class SuggestedAnswer(BaseModel):
    fit_analysis: FitAnalysis
    answer: str
    rationale: str                      # por que ESTA resposta para ESTE contexto
    facts_used: list[str]               # IDs de fatos do perfil, ex.: ["exp-003", "proj-001"]
    company_claims_used: list[str]      # claims do CompanyProfile citados
    confidence: Literal["high", "medium", "low"]
    caveats: list[str]                  # "não encontrei experiência com X; a resposta contorna isso"
```

### O perfil como base de fatos

O `profile.yaml` é a peça anti-alucinação central. Não é um currículo em prosa — é uma **base de fatos com IDs estáveis**:

```yaml
experiences:
  - id: exp-001
    company: "Empresa X"
    role: "Desenvolvedor Backend"
    period: "2022-2024"
    facts:
      - "Mantive APIs REST em Python/FastAPI com ~200k req/dia"
      - "Reduzi tempo de resposta p95 de 800ms para 220ms"
    skills: [python, fastapi, postgres, redis]
projects:
  - id: proj-001
    name: "Sistema Y"
    facts: ["..."]
skills_matrix:
  python: {level: "avançado", years: 4}
  java: {level: "iniciante", years: 0.5}   # honestidade calibrada
constraints:
  - "Nunca afirmar experiência profissional com tecnologias fora da skills_matrix"
preferences:
  tone: "profissional, direto, primeira pessoa"
  language: "pt-BR"
```

### Estrutura do prompt (e por que cada parte existe)

```
[system — estável, com cache_control]
  Papel: assistente de redação de candidaturas.
  REGRAS RÍGIDAS:
  - Use SOMENTE fatos presentes no perfil abaixo. Cada afirmação sobre o
    candidato deve ser rastreável a um ID de fato, listado em facts_used.
  - Se o perfil não cobre a pergunta, diga isso em caveats e escreva uma
    resposta honesta que não invente experiência.
  - Nunca eleve o nível declarado na skills_matrix.
  - Afirmações sobre a empresa: somente as fornecidas em CompanyProfile.
[perfil completo — estável, dentro do cache]
[user — variável]
  JobContext (recorte relevante) + CompanyProfile (recorte relevante)
  + pergunta + tipo + limite de caracteres + instruções de tom
```

- **Prompt caching**: system + perfil são idênticos em toda chamada → prefixo cacheado (leitura a ~0,1× do preço). O que varia fica no final.
- **Structured output** (`messages.parse` com o Pydantic `SuggestedAnswer`): garante o schema — inclusive `facts_used`, que alimenta o verificador.
- **Streaming**: o overlay mostra a resposta sendo escrita; percepção de latência despenca.
- `char_limit` detectado na tela entra como instrução dura ("máximo 500 caracteres — corte de conteúdo, não de qualidade").

### Anti-alucinação: três camadas

1. **Prevenção (prompt)** — regras rígidas + base de fatos com IDs + skills_matrix com níveis honestos. A instrução mais eficaz não é "não alucine", e sim dar ao modelo uma saída legítima para lacunas: o campo `caveats`.
2. **Verificação (pós-geração)**
   - *Checagem determinística, local*: todo ID em `facts_used` existe no perfil? Alguma tecnologia citada na resposta está fora da `skills_matrix`? (matching simples por vocabulário controlado).
   - *Checagem semântica, Haiku*: "Cada afirmação factual desta resposta é suportada pelos fatos [lista]? Liste as não suportadas." Custa ~1 centavo e pega paráfrases que o matching não pega.
   - Afirmação não suportada ⇒ **uma** regeneração automática com o apontamento do erro; se persistir, a resposta vai à UI com a frase problemática **destacada em vermelho** — o sistema nunca esconde a falha, expõe.
3. **Revisão humana (UI)** — o overlay mostra: resposta, `rationale`, fatos usados (expansíveis — você vê *de onde* veio cada afirmação), `caveats` e confiança. Botões: Copiar / Editar / Regenerar (com instrução extra, ex.: "mais curto", "menos formal") / Descartar. **Não existe caminho no código que preencha ou envie um formulário.**

### Feedback loop

Toda edição do usuário é gravada (`answers.final_text` vs `answers.suggested_text`). Isso alimenta melhorias baratas já na V1: exemplos few-shot das *suas* respostas aprovadas entram no prompt ("escreva no estilo destes exemplos"), o que ajusta tom sem nenhum fine-tuning.

## Custo por pergunta (ordem de grandeza)

| Chamada | Modelo | Tokens típicos (in/out) | Custo aprox. |
|---|---|---|---|
| Detecção (quando heurística não basta) | Haiku 4.5 | 1,5k / 300 | ~US$ 0,003 |
| Extração de JobContext (1× por vaga) | Haiku 4.5 | 2k / 500 | ~US$ 0,005 |
| Pesquisa de empresa (1× por empresa/7 dias) | Opus 5 + web search | 15k / 2k | ~US$ 0,15–0,30 |
| Geração | Opus 5 (perfil cacheado) | 6k / 800 | ~US$ 0,05 |
| Verificação | Haiku 4.5 | 2k / 300 | ~US$ 0,004 |

**Uma candidatura típica (5 perguntas, empresa nova): ~US$ 0,50.** Com cache de empresa quente: ~US$ 0,25. Detalhes e cenários em `docs/06-mvp-roadmap.md`.
