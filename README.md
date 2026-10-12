# Comic Panels to MiniMax H3 Ref2VA

Converte 1–9 imagens individuais em um prompt Ref2VA de seis seções. Analisa cada painel com o `Llama Vision Chat` instalado, em sequência, e entrega `prompt`, `analysis_json` e `warnings`, todos `STRING`. Não gera vídeo nem chama a API do MiniMax.

## Página inteira para uma cena animada, com H3 local

Reinicie o ComfyUI para registrar **Comic Page to MiniMax H3 Scene** e abra [comic_page_local_ref2va.json](examples/comic_page_local_ref2va.json). Esse workflow usa a página inteira como storyboard. O novo nó agenda duas chamadas locais estruturadas ao `Llama Vision Chat`: leitura visual e planejamento de ações, mudanças de expressão e interação. O montador insere as falas confirmadas da primeira etapa, sem permitir que o planejador as reescreva. O texto e a mesma imagem alimentam o **MiniMax H3 Reference to Video** nativo, seguido de sampling, decodificação de vídeo/áudio e Save Video.

1. Selecione a página no primeiro Load Image. A imagem fornecida para este exemplo está em [comic_page_reference.png](examples/comic_page_reference.png); copie-a para `ComfyUI/input` ou carregue-a pelo seletor de upload.
2. Confira os caminhos do GGUF e mmproj em **Visão local**. O exemplo usa o Qwen3.6-35B-A3B local, contexto 16384, `max_tokens=8192`, `reasoning=off`, temperatura 0,3, faixa de visão de 1024–1536 tokens e projetor na CPU. O processo iniciado pela extensão é reutilizado nas duas etapas e encerrado ao montar o prompt ou em caso de falha. O host é loopback; nenhum modelo é baixado.
3. Ajuste **Duração desejada**. O mesmo controle define os frames e a duração enviada ao roteirista. H3 usa a grade `17k+5` a 24 fps: 28 segundos resultam em 685 frames, aproximadamente 28,542 segundos. Geração acima de cerca de 15 segundos é experimental no caminho nativo instalado e exige mais memória; o exemplo de 28 segundos não representa qualidade ou VRAM garantidas.
4. Execute. Para revisar somente o roteiro antes de sampling, coloque Save Video em **Never**; o preview textual permanece ativo. Para gerar vídeo, use **Always**. O workflow vem com geração ativa, 864×480, 30 passos e seed 42. Os loaders selecionam arquivos já existentes nesta máquina, incluindo `h3ErosMax_beta5_fp8.safetensors`; trocar o checkpoint pode alterar bastante o resultado.

A direção editável está em [comic_scene_direction.txt](examples/comic_scene_direction.txt) e em `scene_prompt` no nó de cena. Ela pede fases de ação dentro de um único take, independentemente do número de quadros. O planejador estima pesos de duração; o montador os distribui dentro da duração escolhida, sem cortes ou reinícios de câmera entre fases. Remove layout, bordas, balões e lettering; personagens se movem e reagem na mesma cena. Falas legíveis são atribuídas a locutores estáveis e usadas apenas como áudio. Movimentos de ligação podem ser inferidos entre estados observados.

O planejador só pode referenciar personagens, fatos e IDs de fala existentes. Cada fala confirmada precisa aparecer uma vez, na ordem de leitura; IDs desconhecidos, pesos inválidos e tags indevidas interrompem a montagem. Falas longas geram avisos sem truncamento. Os previews mostram o roteiro, as observações, o plano e os avisos. Essas verificações não provam a veracidade do OCR, da identidade ou das ações: revise o material observado e o roteiro. Alterar a duração ou direção reutiliza a leitura em cache e solicita um novo planejamento.

A [versão API do grafo local](examples/comic_page_local_ref2va_api.json) também usa somente os nós locais. “API” aqui indica o formato de execução do ComfyUI, não um serviço remoto.

O método se aproxima do [relato do autor no Reddit](https://www.reddit.com/r/StableDiffusion/comments/1wih5rg/i_fed_minimax_h3_3_pages_of_a_comic_and_it_spit/): páginas completas como referências e um roteiro de cena. A [especificação oficial Ref2VA](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/ref-en.txt) distingue storyboard/referência de um frame que deve ser reproduzido. A aproximação visual precisa ser medida com geração de vídeo; um grafo válido ou um roteiro bem formado não comprova o resultado.

Validação em 02/10/2026: 73 testes existentes e 8 testes de cena passaram; o grafo local completo passou pela validação do executor. A leitura real da imagem anexada e o planejamento real com Qwen3.6-35B produziram [um prompt de exemplo](examples/comic_page_generated_prompt.txt) e [diagnósticos](examples/comic_page_generated_analysis.json), com 11 falas atribuídas e tempos dentro de 28,542 segundos. A leitura foi reutilizada no teste final do planejador. Houve um locutor incerto e avisos de duração de fala. O OCR também errou texto pequeno e alguns atributos visuais: esses arquivos demonstram a montagem, não uma transcrição fiel revisada. Nenhum vídeo H3 foi renderizado. Os testes novos podem ser executados com `python tests/test_scene.py` no ambiente ComfyUI.

## Instalação nesta máquina

Os arquivos já estão em `custom_nodes/comfyui-comic-ref2va/`. A integração também modifica `custom_nodes/comfyui-llama-server/__init__.py`; os dois diretórios fazem parte da entrega. Reinicie seu ComfyUI no ambiente conda `comfyui` e recarregue a página.

Não foram adicionadas dependências: usa PyTorch, Pillow, NumPy e Pydantic 2 já presentes no ComfyUI. Requer a API V3 com `io.Autogrow` e expansão de grafos, e o `llama-server` local com suporte a `response_format`/JSON Schema. A instalação inspecionada usa frontend 1.52.7 e Python 3.12.

Em outra instalação, copie ambos os diretórios para `custom_nodes`. Preserve adaptações locais do seu `comfyui-llama-server` ao incorporar as mudanças de integração. O caminho do binário continua sendo o configurado nessa extensão (`~/Projects/llama.cpp/build_ada/bin/llama-server` nesta instalação). Escolha os caminhos do modelo GGUF e do projetor de visão existentes; nenhum modelo é baixado automaticamente.

## Uso

1. Abra `examples/three_panels.json` no ComfyUI.
2. Em **Llama Vision Settings**, escolha o GGUF e seu `mmproj` correspondente. A integração usa `reasoning=off` para evitar respostas de raciocínio que consumam o limite de tokens; use `parallel=1`, host de loopback e `temperature=0`. Os pares de 4B/9B testados usam contexto 8192 e `max_tokens=4096`; os pares 35B usam contexto 16384 e `max_tokens=8192`, com `fit=on`, `fitt=128`, KV cache `q8_0` e `fa=on`. Valores maiores de contexto/token podem exigir mais RAM/VRAM e tempo de inicialização.
3. Conecte uma imagem RGB por entrada, de `image_1` até `image_9`. As entradas aparecem progressivamente, como no MiniMax. A ordem é a numeração dos sockets, não a ordem cronológica dos cliques. Após remover um painel intermediário, reconecte os restantes consecutivamente. Lacunas causam um erro explícito para evitar trocar referências silenciosamente.
4. Ajuste a duração entre 4 e 15 segundos; o padrão é 10. O workflow compartilha um único controle de duração com o MiniMax.
5. Edite `analysis_prompt` para orientar a inspeção. As regras de evidência e o esquema JSON continuam sendo enviados ao modelo.
6. Execute e examine **Final Ref2VA prompt**, **Panel analysis / identities / timing** e **Validation warnings**. `debug` também registra os dados intermediários no log do ComfyUI; as saídas de diagnóstico estão disponíveis mesmo quando ele está desativado.
7. Para gerar um vídeo depois da revisão, ative os nós **MiniMax H3 Reference to Video** e **Save Video**, que começam desativados. Isso usa o mecanismo de conta/créditos já existente no ComfyUI. O novo nó não inicia essa geração.

As mesmas imagens originais se conectam diretamente ao novo nó e ao MiniMax, na mesma ordem. Não há saídas de imagem de passagem. Batches são rejeitados: separe explicitamente um batch com os nós de imagem existentes antes de conectar os painéis.

### Falso plano-sequência

O prompt final pede um plano contínuo simulado, sem cortes secos, saltos de montagem, fades para preto ou dissolvências visíveis. Os marcadores `[Shot N]` e seus tempos continuam delimitando os intervalos das referências, mas cada passagem é descrita como uma emenda oculta por um breve movimento com desfoque, usando somente o conteúdo dos dois painéis adjacentes. A passagem termina na composição da próxima referência, dentro da duração já distribuída. Com uma imagem, o prompt pede um único plano contínuo.

Essa direção é aplicada pelo montador, sem alterar o prompt de análise visual nem o system prompt do Llama. Ela mantém a ordem das imagens, as falas e as restrições de evidência: não inventa ambientes intermediários, relações espaciais ou transformação entre personagens. Os controles de câmera abaixo orientam o enquadramento enquanto cada referência está estabelecida. O resultado visual depende de o MiniMax seguir essas instruções; os testes validam o prompt, sem gerar vídeo.

### Instruções extras

`extra_instructions` aceita estes controles, separados por ponto e vírgula:

```text
camera=slow_zoom_in; pace=slow; motion=subtle
```

| Controle | Valores |
| --- | --- |
| `camera` | `static`, `slow_zoom_in` |
| `pace` | `natural`, `slow` |
| `motion` | `subtle`, `hold` |

O campo é deliberadamente restrito a essas instruções verificáveis, em ambos os modos. Texto livre não reconhecido gera aviso e não é copiado para o prompt. Isso impede que uma instrução adicional introduza personagens, falas ou objetos. O zoom é sempre pequeno, para dentro, preservando os limites da imagem.

Com `strict_mode=True`, os movimentos usam modelos de frase conservadores associados a personagens e ações observados. Interpretações emocionais reconhecidas são substituídas por uma instrução para preservar a expressão da referência. Com `False`, podem ser usadas as descrições de movimento do modelo, ainda vinculadas a evidências válidas. Desligar o modo estrito não habilita falas inventadas, referências inexistentes ou música.

Se o modelo sugerir continuar um movimento, mas vinculá-lo apenas a um objeto ou cenário, a montagem mantém a pose original e emite aviso. Não transforma a sugestão em um novo acontecimento.

## Integração e execução

As classes instaladas foram verificadas, não deduzidas de seus nomes de exibição:

| Nome exibido | Classe / registro | Fonte local |
| --- | --- | --- |
| Llama Vision Chat | `LlamaVisionChat` | `custom_nodes/comfyui-llama-server/__init__.py` |
| MiniMax H3 Reference to Video | `MinimaxHailuo03ReferenceNode` | `comfy_api_nodes/nodes_minimax.py` |

O nó principal expande um grafo com `GraphBuilder`. Para cada imagem, **ComicPanelRequest → LlamaVisionChat → ComicPanelValidate** forma uma cadeia. O próximo pedido depende da confirmação do painel anterior. O próprio executor do ComfyUI agenda as chamadas ao nó original; não há chamada direta de `execute` em produção, novo cliente HTTP ou carregador de modelo paralelo.

O adaptador fornece um JSON Schema ao suporte nativo de saída estruturada do llama.cpp. A validação Pydantic e a validação semântica ocorrem depois da resposta. Uma resposta estruturalmente inválida pode receber **uma** tentativa adicional de correção, também agendada no grafo, com a mesma imagem. Uma segunda falha, erro de transporte, resposta truncada ou painel ausente interrompe o processamento. Não é produzido um prompt parcial.

As mudanças no nó original adicionam controles opcionais (`keep_alive`, `max_tokens`, `temperature`, `response_schema`) e o nó **Llama Vision Settings**. Uma resposta bem-sucedida continua sendo `STRING`; falhas de inicialização, transporte ou truncamento interrompem a execução também no nó avulso. Na cadeia, o processo é reutilizado e liberado após a montagem ou falha definitiva. Um temporizador de 90 segundos de inatividade cobre interrupções entre nós. Uma trava serializa o acesso. A limpeza encerra apenas o subprocesso criado pela extensão, substituindo o antigo `pkill` global.

Se já houver um servidor externo à extensão na porta selecionada, ele é utilizado e **não** é encerrado. Nesse caso, o modelo e as opções de inicialização são responsabilidade de quem iniciou esse servidor; mudar os widgets não reconfigura um processo externo. A extensão existente gerencia a VRAM via llama.cpp (`fit`/`fitt`), não via `ModelPatcher`. O novo nó não altera o gerenciamento de modelos do núcleo nem adiciona chamadas à internet. Para esta integração, apenas endpoints locais de loopback são aceitos.

### Cache e memória

O cache é o cache nativo do ComfyUI, baseado na dependência da imagem e nos parâmetros de análise/modelo. Imagens passam por links do grafo; o novo nó não cria um armazenamento persistente de tensores nem copia todos os painéis para um batch.

Duração, instruções extras, modo estrito, diagnóstico e `subject_overrides` pertencem à montagem: suas alterações reutilizam as análises em cache. A reconexão de uma imagem ou mudança no prompt de análise invalida as dependências afetadas. Como a ordem é garantida por dependências, uma alteração num painel pode também invalidar os painéis posteriores. Cache desabilitado, reinício ou expulsão por pressão de memória exigem nova inferência. Foram testados os modos clássico, LRU e RAM pressure.

Uma análise inválida é conservada no cache nativo como resultado bruto, mas nunca como prompt válido. Se as duas tentativas falharem, revise o erro e ajuste `analysis_prompt`, modelo ou parâmetros para obter uma nova inferência; o montador não recupera um resultado anterior silenciosamente.

## Evidência, diálogos e identidade

O JSON separa `observed` (estilo, composição, personagens, fatos e texto) de `inferred.motions`. Sons têm referência a um fato observado e indicação de sincronização. Não são extraídos personagens ou falas por expressões regulares de uma descrição livre.

Uma fala exige texto legível, idioma, posição do balão, personagem existente e atribuição por cauda do balão ou indicação explícita. Pensamentos, legendas e texto de locutor incerto permanecem visíveis e não são vocalizados. Palavras e pontuação são preservadas. Sem fala atribuída confirmada, não aparecem `<d>` nem IDs de locutor. Conteúdo que colide com tags reservadas do H3 exige revisão manual; não é reescrito silenciosamente.

A reconciliação cria um `<Subject N>` para **cada personagem observado**, inclusive aparições únicas. Os IDs seguem a primeira aparição por painel e a ordem validada dos personagens. Um personagem confirmado em mais de uma imagem mantém o mesmo ID e recebe uma única definição central com sua `<Picture N>` de origem e todas as imagens em que aparece. O formato oficial usa `<Picture N>` como referência de quadro; `<Image N>` não é uma etiqueta Ref2VA documentada.

Personagens são unidos somente por correspondência visual exata, normalizada em capitalização/espaçamento, de aparência, cabelo, roupa, acessórios e pelo menos duas características distintivas, com no máximo uma ocorrência por imagem. Não há similaridade aproximada: personagens semelhantes sem evidência suficiente ficam separados. Em `detailed_description`, os personagens são mencionados por `<Subject N>` e cada shot mantém a posição, pose, expressão física, movimento e fala locais. A descrição de aparência fica apenas em `subject_definitions`. Locutores `(Sx)` têm numeração global própria, baseada na primeira fala confirmada; um personagem silencioso pode ser `<Subject 1>` e o primeiro locutor ser `(S1)`.

`subject_overrides` é opcional e recebe um objeto JSON por ID de Subject. Exemplo:

Os descritores abaixo são ilustrativos. Com `strict_mode=True`, substitua-os pelos valores completos dos campos correspondentes na `analysis_json` do seu workflow.

```json
{
  "1": {
    "appearance": "A slim adult with a narrow face",
    "hair": "Short straight dark hair",
    "clothing": "A light jacket with diagonal seams",
    "accessories": "A triangular pendant",
    "distinctive_features": ["A crescent scar on the left cheek"]
  }
}
```

Os campos omitidos mantêm o valor observado. Com `strict_mode=True`, cada campo visual precisa corresponder ao valor completo observado, ignorando apenas maiúsculas, espaços repetidos e ponto final; fragmentos e combinações que mudem o sentido, inclusive negações, são recusados. Marcas distintivas podem selecionar marcas completas já observadas. Texto inventado, markup Ref2VA, IDs desconhecidos e tentativas de editar falas/identidade também são recusados. Abreviações e edições manuais exigem `strict_mode=False`; nesse modo, o diagnóstico avisa que a fidelidade não foi revalidada e as referências afetadas passam a `partially_preserved`. O nó rejeita markup e scripts não latinos, mas não inclui um detector linguístico completo para os textos manuais. As análises originais permanecem inalteradas. Alterar IDs, origem, fusão de personagens, atribuição ou conteúdo de fala não faz parte desse controle.

Os Subjects são reconstruídos para as mesmas análises e ordem de imagens; não são IDs persistentes entre workflows diferentes. Overrides, duração e direção remontam o prompt sem chamadas novas de visão enquanto o cache nativo conservar as análises.

Tempos são calculados em milissegundos, com divisão uniforme. O primeiro shot não tem timestamp; os demais usam `MM:SS.mmm`. Falas possivelmente longas demais geram aviso por uma estimativa conservadora de leitura (incluindo escrita CJK). A estimativa não é síntese de voz, nem corta, divide ou acelera falas. Há exatamente uma seção `overall_soundscape` e sempre `non_diegetic_music: N/A`.

**Limite de fidelidade:** validação de esquema, referências, ausência de diálogos confirmados, tons monocromáticos, tags, tempos e controles extras é determinística. A veracidade de uma observação visual, OCR, idioma e a força real de uma característica distintiva ainda dependem do modelo de visão. Um JSON consistente não prova que o modelo viu corretamente a imagem. Revise os diagnósticos antes de usar o prompt, principalmente para balões pequenos e personagens semelhantes. A reconciliação conservadora pode deixar separado um personagem realmente recorrente.

## Exemplos e testes

O runner da matriz verifica somente os pares de modelo e os arquivos de imagem necessários às opções selecionadas; ao retomar um relatório, preserva as células históricas não selecionadas.

Os nove PNGs em `examples/` são desenhos sintéticos de teste, em tons monocromáticos. Nesta máquina também estão em `input/comic_ref2va_panel_1.png` até `input/comic_ref2va_panel_9.png`, usados pelos exemplos. Em outra instalação, copie os arquivos para `input/` ou selecione imagens próprias nos nós Load Image. Os arquivos ficam na raiz de `input` porque a lista de seleção do Load Image instalado não inclui subpastas.

`three_panels_preview_api.json` é a versão API que executa somente análise e visualização textual. `three_panels.json` é o workflow visual completo com três painéis. `nine_panels.json` demonstra os nove sockets e mantém cada imagem original ligada, na mesma ordem, ao MiniMax desativado.

`continuous_take_prompt.txt` demonstra a montagem atual em falso plano-sequência, usando as análises reais salvas de três painéis do Qwen3.5-4B. Foi remontado sem nova inferência e sem gerar vídeo. `generated_prompt.txt` e `generated_analysis.json` preservam uma execução histórica de três painéis anterior à mudança de transições. Esses arquivos não são transcrições de referência garantidas.

Na raiz do ComfyUI:

```bash
conda run -n comfyui python custom_nodes/comfyui-comic-ref2va/tests/test_ref2va.py
```

Os testes usam `unittest`, sem instalar pytest. Exercitam o executor e os caches reais do ComfyUI com inferência simulada, além do transporte/lifecycle do servidor simulado. Incluem os onze cenários pedidos, JSON inválido e reparo limitado, sons, markup, campos ausentes, pensamentos, locutores globais, rejeição explícita de batches, carregamento das imagens do exemplo e consistência das conexões. Nenhum teste automatizado chama o MiniMax.

Após centralizar Subjects e adicionar os Overrides, **50 testes automatizados passaram**, incluindo falso plano-sequência para 1–9 imagens, durações de 4/10/15 s, reconciliação conservadora, identidades independentes de locutores, validação de Overrides e reutilização de cache. As 46 células reais anteriormente aprovadas também foram remontadas (226 análises salvas), sem novas chamadas de visão; ordem, tempos, dados observados e falas permaneceram iguais.

Para reproduzir a remontagem histórica sem inferência:

```bash
/home/<USER>/miniconda3/envs/comfyui/bin/python custom_nodes/comfyui-comic-ref2va/tests/remount_subjects.py
```

O teste real direcionado de edição com Qwen3.5-4B, `mmproj-BF16`, reasoning desligado, três imagens e cache do executor ComfyUI é:

```bash
/home/<USER>/miniconda3/envs/comfyui/bin/python custom_nodes/comfyui-comic-ref2va/tests/run_subject_override_check.py
```

Ele analisa as três imagens uma vez e troca Override/duração na mesma sessão; não chama o MiniMax. Resultados em [SUBJECT_DEFINITIONS_RESULTS.md](SUBJECT_DEFINITIONS_RESULTS.md). O registro completo da matriz anterior continua em [MODEL_COMPATIBILITY_RESULTS.md](MODEL_COMPATIBILITY_RESULTS.md) e não foi substituído.

Para verificar também o modelo de visão local real, com os três desenhos de teste e seus caminhos de modelo já configurados no exemplo:

```bash
conda run -n comfyui python custom_nodes/comfyui-comic-ref2va/tests/smoke_local.py --report /tmp/comic-ref2va-smoke.json
```

Esse teste usa a GPU/CPU do llama.cpp, pode demorar alguns minutos e salva análises, avisos e erros no relatório indicado. Confere também a transcrição exata de `Wait!`. Não gera vídeo.

Validação em 29/09/2026: **42 testes automatizados aprovados**. A matriz de inferência real cobriu sete pares GGUF/mmproj com 1–9 imagens (63 células): 46 passaram todos os testes de estrutura e fidelidade dos fixtures; 17 falharam por limitações observadas em dois modelos (Gemma não transcreveu exatamente lettering no primeiro fixture; Qwen3.5-9B não atribuiu com confiança balões apontados claramente para a figura). Os demais cinco pares passaram 1–9. Todos os perfis de 35B passaram sem truncamento com reasoning desligado e contexto 16k/8192 tokens. A falha Gemma no primeiro painel interrompeu corretamente painéis subsequentes nessa execução, então 36 das 315 chamadas-base não foram emitidas; houve 12 tentativas de reparo. As 291 inferências realizadas levaram 77,8 minutos somando as células. O teste real de cache/reconexão/duração/troca de modelo passou com Qwen3.5-4B. Os exemplos de três e nove painéis foram importados visualmente no frontend ComfyUI instalado; nomes, widgets, conexões em ordem, previews, duração e nós MiniMax/Save Video desativados foram conferidos. O grafo original de nove painéis também passou serialização e reabertura no frontend. A inspeção não validou uma rodada completa de edição e reconexão de sockets dinâmicos seguida de reabertura; os artefatos de teste do editor registram que o método automatizado de reconexão não preservou o mapa esperado, portanto não use essa tentativa como prova de edição dinâmica. Nenhum vídeo foi gerado nem chamada MiniMax foi feita. Veja [relatório e artefatos da matriz](MODEL_COMPATIBILITY_RESULTS.md).

## Fontes consultadas

- [MiniMax H3 Prompt Writing](https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills/h3-prompt-writing)
- [Formato Ref2VA oficial](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/ref-en.txt)
- [Sintaxe compartilhada de falas e shots](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/base-en.txt)
- [Nós oficiais MiniMax do ComfyUI](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_api_nodes/nodes_minimax.py)
- Documentação local de `llama.cpp/tools/server/README.md` e implementação de `tools/server/server-common.cpp`. A implementação instalada requer `response_format.json_schema.schema`; o exemplo antigo do README local omite esse nível intermediário.
