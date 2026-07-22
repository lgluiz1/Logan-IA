# Logan AI — Fase 3: Integração de Inteligência Artificial (LLM)

Este documento guarda a especificação e o planejamento arquitetural da Fase 3 do projeto.
A Fase 3 deve ser implementada apenas quando a base do sistema (Fase 1 e 2) estiver rodando perfeitamente e 100% testada (OBD, alertas e áudio local).

## Objetivo da Fase 3
Transformar o Logan de um sistema "reativo" (que apenas avisa sobre alertas) em um assistente automotivo interativo e conversacional. O motorista poderá fazer perguntas via voz, e o Logan acessará o estado atual do veículo para responder de forma natural.

## 1. Componentes Planejados

### 1.1. AI Gateway (`services/ai_gateway.py`)
Um serviço central (desacoplado dos Workers) responsável por:
- Fazer a ponte entre o Logan AI e um LLM (Gemini 2.0 Flash via API ou modelo local como Llama 3 via Ollama).
- Manter o histórico de contexto da conversa.
- Receber injetado no prompt o `VehicleState` atualizado (RPM, Combustível, Velocidade, Alertas ativos).
- Retornar o texto gerado para ser sintetizado pelo TTS.

### 1.2. Wake Word Worker (`workers/wake_word_worker.py`)
Um Worker rodando localmente na Orange Pi:
- Utiliza a biblioteca `openwakeword` para escutar continuamente o microfone do ESP32.
- Fica aguardando pela palavra-chave: **"Logan"** ou **"E aí, Logan"**.
- Ao detectar a palavra-chave, dispara um evento no Event Bus que aciona o LED Azul (Modo de escuta) e inicia a gravação do comando do usuário.

### 1.3. User Speech Worker (`workers/user_speech_worker.py`)
Responsável por gravar o áudio após o Wake Word:
- Grava 3 a 5 segundos de áudio (ou até detectar silêncio usando VAD - Voice Activity Detection).
- Envia o áudio para o contêiner do `faster-whisper` (STT).
- Pega o texto transcrito e despacha para o AI Gateway responder.

## 2. Fluxo de Dados (Event Bus)

1. **Escuta Contínua**: O microfone (ESP32) envia áudio via serial.
2. **Wake Word**: `wake_word_worker` detecta "Logan" -> Publica `audio.start_recording`.
3. **STT**: `user_speech_worker` junta o áudio, envia para o Whisper -> Publica `voice.user_input` ("Quanto de gasolina nós temos?").
4. **Inteligência**: `ai_gateway` recebe `voice.user_input`. Ele monta o Prompt com o estado do carro (ex: `{fuel_level: 12%}`).
5. **Resposta**: A LLM gera *"Luiz, estamos com 12% de gasolina, recomendo abastecermos em breve."* -> O Gateway publica `voice.response`.
6. **TTS**: `voice_worker` recebe a resposta, passa pelo Kokoro TTS e toca o som.

## 3. Segurança e Modo Offline

- O carro não deve parar de funcionar ou travar a telemetria caso fique sem internet (LLM em nuvem fora do ar).
- Se a API falhar, o `ai_gateway` deve disparar um fallback de voz: *"Luiz, estou sem conexão com a nuvem no momento, mas continuo monitorando os sensores normalmente."*
- Alertas críticos (Temperatura, Óleo, Pane seca) continuam sendo gerados localmente e processados com prioridade MÁXIMA pelo `Scheduler`, cortando inclusive a fala do LLM caso ele esteja respondendo algo banal.

## 4. Passo a Passo para Implementação Futura

1. Criar o `ai_gateway.py` integrando com o pacote `google-genai` ou `openai`.
2. Criar os workers de captação (`wake_word` e `user_speech`).
3. Adicionar as chaves de API no `.env`.
4. Testar a latência do ciclo (Falar -> STT -> LLM -> TTS -> Áudio tocar) para garantir que fique abaixo de 3 segundos na Orange Pi.
