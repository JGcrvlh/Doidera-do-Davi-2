# 06 — MVP, Roadmap, Custos e Desafios

## 1. MVP: a menor versão que entrega o valor central

**Definição do MVP:** aperto um atalho na tela de um formulário de candidatura → em segundos vejo, num painel discreto, uma resposta sugerida baseada no meu perfil real e no contexto da vaga, com justificativa → copio (ou edito e copio).

O que fica **fora** do MVP, de propósito: pesquisa de empresa (V1), verificador semântico (V1), histórico com busca (V1), múltiplos monitores, modo semi-automático, empacotamento. Cada um desses melhora o produto, nenhum é necessário para provar o conceito.

### Ordem de implementação (cada fase termina com algo utilizável)

**Fase A — o esqueleto que prova o conceito (comece aqui)**
1. `domain/models.py` + `profile.py`: contratos e carga do `profile.yaml`. *Primeiro porque tudo depende do vocabulário.*
2. `capture/` + `ocr/`: hotkey → screenshot da janela ativa → texto no console. *Primeiro risco técnico real: valide a qualidade do OCR nos formulários que você usa (Gupy, LinkedIn) antes de escrever qualquer coisa de IA.*
3. `llm/client.py` + `generation/generator.py` no modo mais cru: texto do OCR inteiro + perfil → Opus 5 → resposta no console. *Fim da fase A: o conceito já funciona de ponta a ponta, feio mas funciona.*

**Fase B — vira ferramenta**
4. `detection/heuristics.py`: isolar a pergunta em vez de mandar a tela inteira (qualidade sobe, custo desce).
5. `privacy/redactor.py`: antes de usar no dia a dia de verdade.
6. `ui/tray.py` + `ui/overlay.py`: sair do console; overlay com Copiar/Regenerar/Descartar; streaming da resposta.

**Fase C — vira produto mínimo**
7. `context/extractor.py` + `merger.py`: `JobContext` estruturado e acumulativo (Haiku).
8. `storage/`: salvar candidaturas, perguntas, respostas e edições.
9. Structured output completo (`SuggestedAnswer` com `facts_used` + `caveats`) + checagem determinística de fatos.

> Regra prática: **A3 é o momento "uau"** — chegue nele na primeira semana. Tudo depois é refinamento com o produto já na mão.

## 2. Roadmap

### MVP (acima) — semanas 1–3
Hotkey → OCR → detecção heurística → geração com perfil → overlay → histórico básico. Windows primeiro (seu ambiente), abstrações prontas para outros SOs.

### V1 — "assistente completo" — semanas 4–8
- **Pesquisa de empresa** com web search tool + cache TTL + fontes citadas.
- **Verificador semântico** anti-alucinação (Haiku) + destaque de frases não suportadas.
- **Histórico com busca** (FTS5): por empresa, vaga, pergunta; reuso de respostas anteriores como rascunho.
- **Editor no overlay** com "regenerar com instrução" ("mais curto", "menos formal").
- **Few-shot com suas respostas aprovadas** (feedback loop de tom).
- Detecção de limite de caracteres; suporte a múltipla escolha (sugere e justifica a opção).
- Onboarding do perfil (wizard que transforma seu currículo em `profile.yaml` — usando o próprio Claude).
- Empacotamento com PyInstaller.

### V2 — "plataforma pessoal de candidaturas" — meses 3–5
- **Split daemon + UI** (FastAPI + WebSocket) — destrava o resto da fase.
- **Extensão de navegador** como segunda fonte de captura (DOM = texto perfeito em web) alimentando o mesmo pipeline.
- **Modo semi-automático opt-in**: em janelas/sites autorizados, diff de tela detecta nova pergunta e prepara a sugestão antes do hotkey.
- **RAG do perfil** (sqlite-vec): perfis grandes → seleção das experiências mais relevantes por pergunta.
- Dashboard de candidaturas (funil: aplicadas, respondidas, entrevistas) e exportação (CSV/Notion).
- macOS/Linux de primeira classe.

### Funcionalidades avançadas — quando fizer sentido
- **Modo privacidade máxima**: Ollama para classificação/extração; nada de rede exceto geração (ou nem isso, aceitando perda de qualidade).
- **Preparação de entrevista**: a partir do histórico da vaga, gerar guia de estudo e perguntas prováveis — *para estudar antes, não para colar durante* (ver doc 07).
- Acompanhamento pós-candidatura (lembretes de follow-up).
- Sync multi-dispositivo criptografado (aí sim: backend na nuvem, autenticação, Postgres).
- Análise de gap de carreira agregada ("os requisitos que mais aparecem e você não tem são X, Y").

## 3. Custos

### Componentes gratuitos / locais
Captura (mss), OCR (RapidOCR), heurísticas, redação de PII, SQLite/FTS5, UI (PySide6), keyring — **todo o esqueleto do produto roda a custo zero**.

### Componentes pagos (APIs)

| Item | Preço de referência | Observação |
|---|---|---|
| Claude Haiku 4.5 | $1 in / $5 out por MTok | Classificação, extração, verificação |
| Claude Opus 5 | $5 in / $25 out por MTok | Geração e pesquisa; prompt caching corta ~90% do prefixo repetido |
| Web search (server-side) | ~$10 / 1.000 buscas + tokens | Só na pesquisa de empresa, 1× por empresa/7 dias |

### Cenários mensais (uso pessoal)

| Cenário | Volume | Custo estimado |
|---|---|---|
| Busca casual | 10 candidaturas/mês (~50 perguntas) | **US$ 3–5** |
| Busca ativa | 40 candidaturas/mês | **US$ 12–20** |
| Sem pesquisa de empresa (só MVP) | 40 candidaturas/mês | **US$ 5–8** |

Alavancas se precisar reduzir: gerar com Sonnet em vez de Opus (~40% do custo, qualidade ainda alta), TTL de cache maior, pesquisa de empresa opcional por vaga. Configure um **limite de gasto na console do provedor** desde o dia 1.

## 4. Desafios técnicos e como resolver

| # | Desafio | Risco | Solução |
|---|---|---|---|
| 1 | **Qualidade do OCR** em telas com temas escuros, fontes pequenas, zoom | Alto — corrompe tudo rio abaixo | Upscale 2× antes do OCR; binarização adaptativa; validar cedo (fase A2) com telas reais; fallback: recorte manual da região (o usuário arrasta um retângulo) |
| 2 | **Pergunta ≠ resto da tela** (menus, descrição da vaga, rodapé misturados) | Alto | Usar bounding boxes (label + campo vazio abaixo); heurísticas por plataforma; fallback LLM; e o overlay sempre mostra *qual* pergunta detectou — erro visível é erro corrigível (clique para escolher outro bloco) |
| 3 | **Descrição da vaga em outra tela** que a pergunta | Médio | `JobContext` acumulativo por vaga (merge de capturas) + atalho "colar descrição/URL da vaga" |
| 4 | **Alucinação de experiência** | Alto — mina a confiança no produto | As três camadas do doc 03: base de fatos com IDs, verificador, destaque na UI |
| 5 | **Latência percebida** | Médio | Streaming no overlay; pesquisa de empresa antecipada em background; cache agressivo; Haiku nos passos intermediários |
| 6 | **Hotkey/overlay em cima de apps fullscreen ou multi-monitor** | Médio | Qt `WindowStaysOnTopHint` + testes por SO; posição do overlay configurável; hotkey configurável (conflitos com outros apps) |
| 7 | **Permissões de captura do SO** (macOS pede Screen Recording; Wayland restringe) | Médio | Onboarding guiando a permissão; no Linux, priorizar X11 e usar portal `xdg-desktop-portal` no Wayland |
| 8 | **Custo fugir do controle** | Baixo | Contador de custo local por candidatura (o `llm/client.py` mede tokens), teto mensal configurável no app + hard limit na console |
| 9 | **Variedade de plataformas de vaga** | Médio | Golden tests com capturas reais das principais (Gupy, LinkedIn, Greenhouse, Lever, Workday); heurísticas por plataforma isoladas em um módulo com fixtures |
| 10 | **Prompt injection via tela** (página maliciosa com instruções embutidas) | Baixo/Médio | Texto de tela sempre delimitado como dado; structured output; revisão humana obrigatória |
