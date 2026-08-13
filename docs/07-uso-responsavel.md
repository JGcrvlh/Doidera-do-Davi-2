# 07 — Limitações e Uso Responsável

Uma análise honesta dos riscos de usar (e construir) este tipo de ferramenta — e como o design do sistema mantém o usuário no controle.

## 1. Onde a ferramenta é legítima — e onde não é

A distinção central não é técnica, é sobre **o que a outra parte do processo espera que você esteja fazendo**:

| Cenário | Avaliação | Por quê |
|---|---|---|
| Redigir respostas de **formulários de candidatura** (motivação, experiências, "por que esta empresa") | ✅ Uso pretendido | É o mesmo território de pedir ajuda a um amigo, a um revisor ou ao ChatGPT para escrever a carta de apresentação. As afirmações são suas (vêm do seu perfil real), a redação é assistida — prática hoje comum e, em geral, aceita. A revisão obrigatória garante que a resposta final é algo que você endossa |
| Organizar histórico de candidaturas, pesquisar empresas, preparar-se para entrevistas **antes** delas | ✅ Uso pretendido | Pesquisa e preparação são exatamente o que recrutadores esperam de um bom candidato |
| **Testes técnicos / avaliações com regras de "sem ajuda externa"** | ❌ Fora do escopo | Isso é fraude de avaliação: o resultado deixa de medir você. Muitas plataformas de assessment proíbem expressamente e usam proctoring; ser pego encerra o processo (e às vezes queima o candidato na base da empresa) |
| **Entrevistas ao vivo** (colar respostas em tempo real) | ❌ Fora do escopo | Além de antiético, é autodestrutivo: você seria contratado para um nível que não sustenta no dia a dia. Entrevistadores percebem leitura de tela com facilidade |
| Inflar experiências/skills que você não tem | ❌ Bloqueado por design | O sistema é arquitetado para *impedir* isso (base de fatos + verificador), não para facilitar |

## 2. Riscos concretos a considerar

- **Termos de uso das plataformas.** LinkedIn e similares proíbem automação de interação com a plataforma (bots que aplicam sozinhos, scraping). Este projeto não automatiza nenhuma interação — não clica, não preenche, não envia; captura a *sua* tela e escreve num painel próprio. Ainda assim: (a) plataformas de *assessment* (HackerRank, Codility etc.) têm regras específicas sobre ferramentas auxiliares, que valem mais que qualquer racional técnico; (b) políticas mudam — a responsabilidade de conferir é do usuário, e o doc do app deve dizer isso sem rodeios.
- **Detecção de texto gerado por IA.** Algumas empresas passam respostas dissertativas por detectores. Respostas 100% geradas têm "sotaque de LLM". Mitigação honesta (não evasão): o few-shot com *suas* respostas aprovadas aproxima o texto do seu estilo real, e a etapa de edição existe para você reescrever com sua voz. **O projeto não implementa e não implementará funcionalidades de "burlar detector"** — a resposta certa para "parece IA demais" é o usuário editar mais, não a máquina disfarçar melhor.
- **Homogeneização.** Se todo mundo responde com IA, respostas convergem para a mesma sopa genérica. O diferencial desta ferramenta é ancorar tudo em fatos específicos seus — mas o risco residual existe e é mais um motivo para a edição humana.
- **Dependência.** Usar a ferramenta como muleta para *tudo* atrofia exatamente a habilidade (comunicar suas experiências) que a entrevista vai testar ao vivo. O modo "preparação de entrevista" (roadmap) empurra na direção certa: estudar antes, não colar durante.
- **Erro da máquina, consequência sua.** OCR pode ler errado, a pesquisa pode trazer informação desatualizada da empresa, o modelo pode interpretar mal a pergunta. Quem assina a resposta é você — por isso `rationale`, fontes e `caveats` são visíveis, não escondidos.

## 3. Como o design garante controle do usuário

Resumo dos mecanismos já detalhados nos docs 03 e 04, vistos pela lente de uso responsável:

1. **Nenhuma automação de envio.** Não existe código que preencha campo ou submeta formulário. O output final é texto na área de transferência, colocado lá por um clique seu.
2. **Revisão é etapa do pipeline, não opcional.** A resposta sempre para no overlay com justificativa, fatos usados e ressalvas antes de qualquer uso.
3. **Verdade por construção.** O gerador só afirma o que rastreia a fatos do seu perfil; lacunas viram `caveats` explícitos, não enfeites.
4. **Transparência de saída.** O log "o que foi enviado" mostra todo texto que saiu da máquina.
5. **Escopo declarado.** README e onboarding do app declaram os usos fora de escopo (assessments proctorados, entrevistas ao vivo) — quem constrói a ferramenta escolhe o que ela promove.

## 4. Nota para o portfólio

Tratar esta seção como parte do produto — e não como letra miúda — é diferencial num portfólio: demonstra maturidade de engenharia (threat model, minimização de dados, human-in-the-loop) e maturidade profissional (entender o contexto social da ferramenta). Vale destacar no README do projeto final e estar preparado para discutir em entrevista: "por que você construiu X e decidiu *não* construir Y" costuma render conversas melhores do que a feature list.
