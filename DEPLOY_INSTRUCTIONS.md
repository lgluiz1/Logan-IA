# Instruções de Implantação e Configuração no Carro (Logan AI)

Este documento explica o que você precisa alterar nos arquivos de configuração para rodar o Logan AI no computador do carro (Raspberry Pi ou outro PC) usando os sensores físicos reais (adaptador ELM327 USB/Bluetooth e fiação OBD-II).

---

## 1. Ativar o Modo de Produção (Sensores Reais)
Atualmente, o Logan está rodando em modo **Demo** (simulador). Para conectar ao carro real:

1. Abra o arquivo [config/logan.yml](file:///C:/Users/Luiz/Desktop/Logan_IA/config/logan.yml).
2. Na linha 8, mude o valor de `environment` de `"demo"` para `"production"`:
   ```yaml
   system:
     name: "Logan AI"
     version: "1.0.0"
     environment: "production"  # Altere aqui de "demo" para "production"
   ```

---

## 2. Configuração de Portas USB / COM do OBD-II
* **Varredura Automática:** O Logan já está configurado por padrão com `obd_port: "auto"` na linha 26 de `config/logan.yml`.
* **Como funciona:** Quando definido como `"auto"`, o driver usa a biblioteca `python-obd` para **varrer todas as portas COM e conexões seriais USB automaticamente**, buscando o dispositivo que responde pelo chip ELM327 (adaptador OBD-II). Você não precisa alterar nada para isso funcionar.
* **Porta Fixa (Se desejar travar):** Se preferir travar em uma porta fixa (para carregar mais rápido sem varredura), mude em `config/logan.yml`:
  * No Windows: `obd_port: "COM3"` (ou a porta correspondente no Gerenciador de Dispositivos).
  * No Linux/Raspberry Pi: `obd_port: "/dev/ttyUSB0"` (ou similar).

---

## 3. Configuração do Dispositivo ESP32 (Fita LED / Áudio)
Se você estiver utilizando a placa ESP32 integrada para controlar os LEDs e saídas:
* Verifique qual porta COM/USB o seu ESP32 foi conectado.
* Atualize a linha 31 de `config/logan.yml`:
  * No Windows: `esp32_port: "COM4"`
  * No Linux/Raspberry Pi: `esp32_port: "/dev/ttyACM0"`

---

## 4. Endereço dos Serviços (Docker vs Local)
Se você estiver rodando o Docker no outro computador para as IAs (Whisper e Kokoro):
* As URLs na máquina do carro podem mudar se não estiverem no mesmo container de rede.
* Se estiver rodando tudo na mesma máquina local física, as conexões devem apontar para `localhost`:
  * `whisper_url: "http://localhost:9000"`
  * `kokoro_url: "http://localhost:8880"`

---

## 5. Como Iniciar no Outro Computador
1. Clone o repositório no PC do carro:
   ```bash
   git clone https://github.com/lgluiz1/Logan-IA.git
   cd Logan-IA
   ```
2. Crie e ative o ambiente virtual virtualenv:
   ```bash
   python -m venv venv
   # No Windows:
   .\venv\Scripts\activate
   # No Linux/Mac:
   source venv/bin/activate
   ```
3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
4. Execute o Logan AI:
   ```bash
   python main.py
   ```
