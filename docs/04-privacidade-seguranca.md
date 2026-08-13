# 04 — Privacidade e Segurança

Um software que lê a tela é, por definição, um software que pode ver **tudo**: banco, e-mail, mensagens. O projeto trata isso como o risco número 1 e resolve com quatro mecanismos: **captura sob demanda**, **processamento local do dado bruto**, **redação antes de qualquer saída** e **transparência total na UI**.

## 1. O que é processado localmente × o que sai da máquina

| Dado | Onde fica | Sai da máquina? |
|---|---|---|
| Screenshot (imagem) | Memória, descartada após OCR | **Nunca** |
| Texto OCR bruto | Memória | Não — só o recorte relevante, após redação |
| Texto da pergunta + sinais da vaga (redigidos) | — | Sim → Claude API |
| Nome da empresa / domínio | — | Sim → Claude API (pesquisa) |
| Perfil profissional (profile.yaml) | Disco local | Sim, parcialmente → entra no prompt de geração (é a matéria-prima da resposta; decisão consciente e visível ao usuário) |
| Histórico de vagas/respostas | SQLite local | **Nunca** |
| Chave da API | Keyring do SO | Só como header de autenticação |

Sobre o lado do provedor: chamadas à Claude API não são usadas para treinar modelos por padrão, mas ficam sujeitas à política de retenção do provedor — o doc do usuário final deve deixar isso explícito, e o modo "local-only" (Ollama) na fase avançada existe para quem não aceitar nenhum tráfego externo.

## 2. Como evitar capturar o que não é do processo seletivo

Defesa em profundidade, em quatro camadas:

1. **Captura sob demanda (design principal)**: nada é capturado sem o hotkey. O modo padrão do app é *não estar olhando a tela*.
2. **Escopo por janela**: captura-se a **janela ativa**, não o desktop inteiro (notificações do WhatsApp no canto da tela nunca entram). O filtro de escopo compara título/processo da janela com padrões de plataformas de emprego; janela fora do padrão gera confirmação explícita.
3. **Redactor (obrigatório no caminho de saída)**: todo texto que vai para API passa por um filtro local de PII — regex de alta precisão para e-mail, telefone, CPF/CNPJ, cartões, endereços — substituindo por placeholders (`[EMAIL]`). Os dados do *próprio candidato* que a resposta precisa vêm do perfil, não da tela, então redigir a tela não degrada o resultado.
4. **Minimização estrutural**: o pipeline envia objetos tipados e recortados (`DetectedQuestion`, `JobSignals`), nunca o dump do OCR. O que não tem campo no contrato, não viaja.

## 3. Controles do usuário (iniciar/parar)

| Controle | Comportamento |
|---|---|
| **Hotkey de captura** | Única forma de iniciar uma análise no MVP |
| **Kill switch** (tray + hotkey secundário) | Cancela pipeline em andamento, descarta capturas em memória, pausa o app. Estado visível no ícone da bandeja |
| **Indicador de atividade** | O ícone muda de cor durante captura/processamento — o app nunca trabalha "invisível" |
| **Modo pausado** | O app abre pausado por padrão após instalação; o usuário arma quando vai se candidatar |
| **Log de transparência** | Tela "o que foi enviado": para cada análise, exatamente o texto que saiu para a API, após redação. Confiança se constrói com inspeção, não com promessa |
| **Apagar dados** | Botões para apagar uma candidatura, uma empresa ou tudo (drop do SQLite + cache) |

Se um dia existir modo semi-automático (V2: detecção por diff de tela), ele será **opt-in por janela/site específico**, com o indicador sempre ativo — nunca um watcher global.

## 4. Armazenamento seguro

- **Chave da API**: exclusivamente no keyring do SO. Nunca em `.env` no diretório do app, nunca em log.
- **SQLite**: em `%APPDATA%`/`~/.local/share` com permissão só do usuário. Opcional: **SQLCipher** (criptografia em repouso) para quem compartilha a máquina — chave derivada de senha via `argon2`.
- **profile.yaml**: local, versionável pelo usuário (é razoável mantê-lo num repositório *privado* pessoal — o app deve alertar para nunca commitá-lo em repo público).
- **Logs**: níveis de log nunca incluem conteúdo de tela nem respostas; apenas eventos e métricas ("OCR 480ms, 23 blocos").
- **Sem telemetria externa.** Nenhum analytics no MVP/V1.

## 5. Ameaças consideradas

| Ameaça | Mitigação |
|---|---|
| Captura acidental de conteúdo sensível (banco aberto atrás) | Captura por janela ativa + filtro de escopo + confirmação |
| Vazamento de PII para a API | Redactor no único caminho de saída + log de transparência para auditar |
| Roubo da chave da API | Keyring do SO; chave com limite de gasto configurado no console do provedor |
| Acesso ao histórico por terceiros na mesma máquina | Permissões de arquivo; SQLCipher opcional |
| Prompt injection vindo da tela (uma página maliciosa contendo "ignore suas instruções...") | O texto da tela entra sempre como *dados do usuário* delimitados, nunca como instrução; regras rígidas no system prompt; structured output limita o formato da saída; e o humano revisa tudo antes de usar |
| Dependência maliciosa | Lockfile (`uv.lock`), dependências mínimas, CI com auditoria (`pip-audit`) |
