# 02 — Stack Tecnológica

Critério geral: **Python em tudo que der** (é sua linguagem forte; um MVP de portfólio vive ou morre pela velocidade de iteração), bibliotecas que rodam local sem serviço externo, e APIs pagas só onde compram qualidade que não existe local (geração de texto e busca web).

## Captura e análise de tela

| Tecnologia | Papel | Por quê |
|---|---|---|
| **mss** | Screenshot | Biblioteca Python minimalista e muito rápida (usa APIs nativas de cada SO), multiplataforma, sem dependências pesadas. `PIL.ImageGrab` é a alternativa, mas `mss` é mais rápida e lida melhor com multi-monitor |
| **pynput** | Hotkey global | Registra atalhos de teclado no nível do SO sem a janela precisar de foco — essencial para o fluxo "estou no formulário, aperto o atalho" |
| **pywin32 / pyobjc / python-xlib** | Metadados da janela ativa | Saber título e processo da janela ativa alimenta o filtro de escopo ("só capturar se a janela parecer de candidatura") e permite capturar só a janela, não o monitor inteiro |

## OCR e processamento de texto

| Tecnologia | Papel | Por quê |
|---|---|---|
| **RapidOCR** (ONNX) | OCR principal | Instala via `pip` (sem binário externo como o Tesseract exige), roda em CPU com boa velocidade, precisão forte em texto de tela (fontes renderizadas, não manuscrito) e suporta português. Retorna bounding boxes, que preservam o layout |
| **Tesseract + pytesseract** | Alternativa | Padrão histórico, ótimo com `por` traineddata; desvantagem é exigir instalação do binário. Vale manter como fallback configurável |
| **OCR nativo do SO** (Windows.Media.Ocr / Apple Vision) | Upgrade opcional | Gratuito, excelente qualidade, zero modelo para distribuir — mas específico por plataforma. Bom candidato a V2 atrás da mesma interface `OcrService` |
| **regex + heurísticas próprias** | Pré-detecção de perguntas | Linhas terminadas em `?`, labels típicos de formulário ("Por que você...", "Descreva..."), campos `*obrigatório` — filtra 80% dos casos sem tocar em modelo |
| **Pydantic** | Modelos de dados | Todos os contratos do pipeline (`ScreenAnalysis`, `JobContext`, `Answer`) são modelos Pydantic — validação de graça e integração direta com structured outputs do Claude |

## LLM / IA

| Tecnologia | Papel | Por quê |
|---|---|---|
| **Claude API — `claude-opus-5`** | Geração da resposta + pesquisa de empresa | O passo de escrita é o produto; Opus 5 é o modelo forte da faixa ($5/$25 por MTok). Suporta *structured outputs* (resposta sempre no schema esperado), *prompt caching* (o perfil + system prompt são idênticos entre chamadas → ~90% de desconto na parte cacheada) e a *web search tool* server-side |
| **Claude API — `claude-haiku-4-5`** | Classificação e extração | Detectar pergunta, extrair `JobContext`, verificar fatos: tarefas pequenas e frequentes. Haiku custa $1/$5 por MTok — centavos por candidatura — e é rápido (importa na percepção de latência) |
| **SDK oficial `anthropic` (Python)** | Cliente | `client.messages.parse()` com Pydantic valida a saída contra o schema automaticamente; streaming nativo para o overlay |
| **Ollama (Llama/Qwen local)** | Opcional, V2+ | Modo "privacidade máxima" para classificação/extração sem rede. Não recomendado para a geração final (qualidade de escrita inferior é perceptível no produto) |

**Por que dois modelos?** O pipeline faz 3–6 chamadas por pergunta, mas só uma exige o modelo caro. Roteamento por dificuldade é a alavanca de custo mais simples que existe: a conta mensal cai ~5× sem perda perceptível.

## Pesquisa na web

| Tecnologia | Papel | Por quê |
|---|---|---|
| **Web search tool do Claude** (`web_search_20260209`, server-side) | Pesquisa de empresa | Decisão que **elimina um subsistema inteiro**: sem API de busca separada, sem scraping, sem parsing de HTML, sem ranqueamento próprio. O modelo busca, filtra (a versão 20260209 tem filtragem dinâmica) e já devolve o `CompanyProfile` estruturado com fontes citadas, em uma única chamada. Custo: ~US$10/1.000 buscas + tokens |
| **Tavily / Brave Search API** | Alternativa | Se um dia você quiser controle total do ranqueamento ou desacoplar busca de geração. Ambas têm free tier razoável. Não vale a complexidade no MVP |

## Backend

| Tecnologia | Papel | Por quê |
|---|---|---|
| **Python 3.12 + asyncio** | Núcleo | O pipeline é I/O-bound (rede, OCR); asyncio permite pesquisa em background + geração + UI responsiva sem gerenciar threads na mão |
| **FastAPI** | Só na V2 (daemon) | Quando o núcleo virar processo separado, FastAPI dá REST + WebSocket com Pydantic nativo — os mesmos modelos do pipeline viram o contrato da API sem retrabalho. **No MVP não há servidor**: seria complexidade sem função |

## Banco de dados

| Tecnologia | Papel | Por quê |
|---|---|---|
| **SQLite** | Histórico, cache, config | Zero operação, um arquivo, transacional, perfeito para single-user local. Postgres seria overkill sem nenhum benefício aqui |
| **FTS5** (extensão do SQLite) | Busca no histórico | "O que eu respondi sobre liderança na vaga da empresa X?" — busca full-text sem serviço de busca |
| **SQLAlchemy 2.0 + Alembic** | ORM + migrações | O schema vai evoluir (V1, V2); migrações versionadas desde o dia 1 evitam dor. SQLAlchemy também mantém a porta aberta para Postgres na fase de sync |
| **sqlite-vec** (opcional, V1) | Busca vetorial | Para RAG sobre o perfil (selecionar as experiências mais relevantes à pergunta) e "perguntas parecidas que já respondi". Roda dentro do próprio SQLite — sem Chroma/Qdrant |

## Interface gráfica

| Tecnologia | Papel | Por quê |
|---|---|---|
| **PySide6 (Qt for Python)** | Tray, overlay, histórico | Único toolkit Python maduro que entrega os três requisitos de discrição: **tray icon**, **janela frameless always-on-top** com transparência (o overlay) e integração nativa de eventos. Licença LGPL ok para portfólio |
| **QSS (Qt Style Sheets)** | Estilo | Overlay pequeno e limpo sem trazer stack web |

Rejeitados: Electron/Tauri (runtime extra, outra linguagem), Tkinter (sem suporte decente a overlay/transparência), app web (não consegue capturar tela do SO nem hotkey global).

## Comunicação entre processos

| Fase | Tecnologia | Por quê |
|---|---|---|
| MVP | **Nenhuma** — fila de eventos in-process + sinais Qt | Um processo só; IPC seria custo sem benefício |
| V2 | **WebSocket (FastAPI)** para eventos + REST para comandos | Mesmos eventos do MVP serializados em JSON; WebSocket porque o fluxo é o servidor empurrando estado do pipeline para a UI |

## Cache

| Camada | Tecnologia | Por quê |
|---|---|---|
| Pesquisa de empresa | **Tabela SQLite com TTL** (7 dias, chave = domínio) | Sobrevive a restart; a mesma empresa aparece em várias vagas |
| Prompt do LLM | **Prompt caching da Claude API** | System prompt + perfil são o prefixo estável de toda chamada; cache reduz custo (~0,1× na leitura) e latência |
| Sessão | **Dicionário em memória** | `JobContext` da vaga atual, últimos OCRs (para diff) |
| Rejeitado | Redis | Serviço externo para um cache de processo único — não |

## Autenticação e segredos

| Necessidade | Tecnologia | Por quê |
|---|---|---|
| Chave da Claude API | **keyring** (Credential Manager / Keychain / Secret Service) | Nunca em texto plano em config; o SO já tem cofre |
| Login de usuário | **Não existe no MVP/V1** | App local single-user não autentica ninguém |
| Sync multi-dispositivo (fase avançada) | FastAPI na nuvem + OAuth/JWT | Só quando (se) existir servidor com dados de usuários |
| Criptografia do banco (opcional) | **SQLCipher** | Para quem quiser o histórico criptografado em repouso |

## Qualidade e ferramentas de desenvolvimento

- **uv** (gerenciador de pacotes/venv — rápido e moderno), **ruff** (lint + format), **mypy** (os contratos Pydantic rendem mais com tipos checados), **pytest** (+ fixtures com screenshots sintéticos para testar OCR/detecção sem tela real), **pre-commit**.
- **PyInstaller** para empacotar o executável na V1 (um portfólio impressiona mais com um `.exe`/`.app` instalável).
