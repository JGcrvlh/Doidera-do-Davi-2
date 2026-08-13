# 05 — Estrutura do Projeto

Estrutura pensada para começar como **monólito modular** (MVP) e evoluir para daemon + UI (V2) sem reorganização: as fronteiras de pacote já são as fronteiras dos futuros processos.

```
candidate-copilot/
├── pyproject.toml              # uv + ruff + mypy + pytest configurados aqui
├── uv.lock
├── README.md
├── docs/                       # estes documentos de projeto
│
├── src/
│   └── copilot/
│       ├── __main__.py         # python -m copilot → sobe UI + core
│       ├── config.py           # Settings (pydantic-settings): paths, hotkeys, modelos, TTLs
│       │
│       ├── domain/             # ★ contratos — o coração estável do sistema
│       │   ├── models.py       # RawCapture, OcrResult, ScreenAnalysis, DetectedQuestion,
│       │   │                   # JobContext, CompanyProfile, SuggestedAnswer, FitAnalysis
│       │   ├── events.py       # PipelineStarted, QuestionDetected, AnswerReady, PipelineError
│       │   └── profile.py      # UserProfile, carga/validação do profile.yaml
│       │
│       ├── capture/
│       │   ├── screen.py       # mss: screenshot de janela ativa/monitor
│       │   ├── window.py       # título/processo da janela ativa (por SO)
│       │   └── hotkeys.py      # pynput: registro dos atalhos globais
│       │
│       ├── ocr/
│       │   ├── base.py         # interface OcrService (Protocol)
│       │   ├── rapidocr.py     # implementação padrão
│       │   └── postprocess.py  # merge de linhas, filtro de confiança, hash perceptual
│       │
│       ├── detection/
│       │   ├── heuristics.py   # regex/regras + layout (bbox)
│       │   └── llm_detector.py # fallback Haiku (structured output)
│       │
│       ├── context/
│       │   ├── extractor.py    # OCR/tela → JobContext (Haiku)
│       │   └── merger.py       # fusão acumulativa por vaga
│       │
│       ├── research/
│       │   ├── researcher.py   # Claude + web search tool → CompanyProfile
│       │   └── cache.py        # cache SQLite com TTL por domínio
│       │
│       ├── generation/
│       │   ├── prompts.py      # templates (system estável p/ cache, user variável)
│       │   ├── generator.py    # Opus 5, streaming, structured output
│       │   └── verifier.py     # checagem determinística + semântica (Haiku)
│       │
│       ├── privacy/
│       │   └── redactor.py     # remoção de PII — único caminho de saída p/ rede
│       │
│       ├── llm/
│       │   └── client.py       # wrapper do SDK anthropic: retries, cache_control,
│       │                       # contagem de custo, escolha de modelo por tarefa
│       │
│       ├── storage/
│       │   ├── db.py           # engine SQLAlchemy, sessão
│       │   ├── models.py       # tabelas: applications, questions, answers,
│       │   │                   # company_cache, settings
│       │   ├── repository.py   # consultas (inclui FTS5)
│       │   └── migrations/     # alembic
│       │
│       ├── orchestrator/
│       │   └── pipeline.py     # máquina de estados; publica domain.events
│       │
│       └── ui/
│           ├── app.py          # QApplication, wiring UI ↔ core (fila de eventos)
│           ├── tray.py         # ícone, menu, indicador de estado, kill switch
│           ├── overlay.py      # painel de sugestão (frameless, always-on-top)
│           ├── history.py      # janela de histórico + busca
│           └── styles.qss
│
├── profile.example.yaml        # modelo comentado do perfil (o real fica fora do repo)
│
└── tests/
    ├── conftest.py             # fixtures: screenshots sintéticos, respostas fake da API
    ├── test_detection.py       # heurísticas contra imagens de formulários reais
    ├── test_context_merge.py
    ├── test_verifier.py        # casos de alucinação propositais → deve bloquear
    ├── test_redactor.py        # PII nunca passa
    └── golden/                 # capturas de referência (Gupy, LinkedIn, Greenhouse...)
```

## Regras de dependência entre módulos

```
ui ──▶ orchestrator ──▶ capture / ocr / detection / context / research / generation
                 │                          │
                 ▼                          ▼
              storage                 llm + privacy
                 ▲                          
domain ◀── (todos dependem de domain; domain não depende de ninguém)
```

- `domain/` não importa nada do projeto — só Pydantic. É o vocabulário comum.
- `ui/` conhece apenas `domain.events` e o `orchestrator`. Nunca importa serviços.
- Toda chamada externa passa por `llm/client.py` (um único ponto para retry, custo, cache) e todo payload passa antes por `privacy/redactor.py`.
- Serviços expõem `Protocol`s (ex.: `OcrService`) — trocar RapidOCR por OCR nativo, ou OCR por extensão de navegador, é adicionar uma implementação.

## Como isso evolui para a V2 (daemon + UI)

1. `orchestrator` + serviços + `storage` viram o pacote do **daemon**; adiciona-se `api/` (FastAPI) que expõe os mesmos `domain.events` via WebSocket e comandos via REST.
2. `ui/` vira aplicativo cliente que fala WebSocket em vez de fila em memória (troca-se uma classe: o `EventBus`).
3. `domain/` é publicado como pacote compartilhado entre os dois.

Nenhum módulo muda de responsabilidade — só de endereço.
