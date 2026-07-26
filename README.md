🚀 LeBron Local UI - Guia de Sobrevivência no KaggleEste repositório/guia existe porque rodar a LeBron Local UI no Kaggle com a arquitetura J-Space-Deliberation exige contornar aproximadamente 15 erros encadeados, dependências desatualizadas e arquivos fora do lugar.Se você quer rodar o modelo sem perder 5 anos de expectativa de vida, siga as instruções abaixo.🛠️ O Problema (A "Putaria")Para o ambiente funcionar, foi necessário resolver:Modelos Não Encontrados: A interface busca artefatos na pasta stage2/final/, mas o upload no Hugging Face nem sempre reflete essa estrutura de pastas.Pip / Transformers Defasado: O Kaggle vem com o transformers antigo que não reconhece a arquitetura gemma4.Erros no Backend (Uvicorn/Ngrok): Processos antigos travando a porta 7860 (address already in use) e dependências do PyTorch corrompendo a memória (Intel MKL FATAL ERROR).Bugs no Código do Modelo: Um NameError: name 'positions' is not defined no arquivo reasoner.py da biblioteca LeBRON.📋 Pré-requisitos e Setup no KaggleAntes de rodar qualquer código, certifique-se de que a sessão do Kaggle está limpa:VÁ EM Session options $\rightarrow$ Restart Session (ou Factory Reset) para matar processos antigos travando a porta 7860 e limpar a GPU.📜 Script de Inicialização Único (One-Click Launcher)Crie uma célula no seu notebook do Kaggle, cole o código abaixo e execute UMA ÚNICA VEZ:Pythonimport os, sys, time, shutil, subprocess, threading

REPO = "https://github.com/guell11/Lebron-Local-UI"
WORK_DIR = "/kaggle/working"
DIR = os.path.join(WORK_DIR, "Lebron-Local-UI")
MODEL_DIR = os.path.join(WORK_DIR, "J-Space-Deliberation")
NGROK_TOKEN = "SEU_NGROK_TOKEN_AQUI"

# 1. Limpeza de diretório antigo
os.chdir(WORK_DIR)
if os.path.exists(DIR): 
    shutil.rmtree(DIR)

# 2. Instalação do Transformers direto da fonte (necessário para gemma4)
print("Instalando dependências e versão bleeding-edge do transformers...")
subprocess.run(
    "pip install -q pyngrok gradio fastapi uvicorn git+https://github.com/huggingface/transformers.git accelerate bitsandbytes huggingface_hub psutil", 
    shell=True
)

# 3. Download do modelo do Hugging Face
print("Baixando artefatos do Hugging Face...")
from huggingface_hub import snapshot_download
snapshot_download(repo_id="guell00/J-Space-Deliberation", local_dir=MODEL_DIR)

# 4. Reorganização dos arquivos para a estrutura esperada pela UI (stage2/final)
stage2_dir = os.path.join(MODEL_DIR, "stage2", "final")
os.makedirs(stage2_dir, exist_ok=True)

arquivos_necessarios = ["jreasoner_adapter.pt", "jreasoner_config.json", "manifest.json"]
for arquivo in arquivos_necessarios:
    src = os.path.join(MODEL_DIR, arquivo)
    if os.path.exists(src):
        shutil.move(src, os.path.join(stage2_dir, arquivo))

# 5. Clone e Setup da UI
subprocess.run(["git", "clone", REPO, DIR], check=True)
os.chdir(DIR)

if os.path.exists("requirements.txt"):
    subprocess.run("pip install -q -r requirements.txt", shell=True)

# 6. Aplicação do Patch de código no reasoner.py (Fix do NameError)
reasoner_path = os.path.join(WORK_DIR, "LeBRON", "lebron_jspace", "reasoner.py")
if os.path.exists(reasoner_path):
    with open(reasoner_path, "r") as f:
        code = f.read()
    
    old_code = "if self.supervision_positions is None:"
    new_code = "if self.supervision_positions is None:\n            positions = torch.tensor([seq - 1], device=slots.device)"
    
    if old_code in code:
        code = code.replace(old_code, new_code)
        with open(reasoner_path, "w") as f:
            f.write(code)
        print("-> Patch aplicado com sucesso no reasoner.py!")

# 7. Subir Servidor FastAPI/Uvicorn em Background
process = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
)

def stream_logs():
    for line in iter(process.stdout.readline, ''):
        if line: print(line.strip())

threading.Thread(target=stream_logs, daemon=True).start()
time.sleep(5)

# 8. Túnel Ngrok
from pyngrok import ngrok
if NGROK_TOKEN: 
    ngrok.set_auth_token(NGROK_TOKEN)

try:
    public_url = ngrok.connect(7860)
    print("\n==========================================")
    print(f" ONLINE: {public_url}")
    print("==========================================\n")
except Exception as e:
    print(f"\nErro ao iniciar Ngrok: {e}")
⚙️ Configuração da Interface (Campos para Preencher)Ao abrir a URL gerada pelo Ngrok, acesse o painel de configurações e preencha os campos exatamente assim:Campo na UICaminho ExatoPasta do repositório LeBRON/kaggle/working/LeBRONDicionário J-Space (.pt)/kaggle/working/J-Space-Deliberation/jspace_dictionary_v3.ptPasta do adapter final/kaggle/working/J-Space-Deliberation/stage2/final⚠️ Atenção: Não use caminhos relativos (com .. ou \). Sempre use caminhos absolutos no formato Linux do Kaggle (/kaggle/working/...).🔍 Solução de Problemas RápidosERR_NGROK_8012 / Connection Refused: A aplicação travou antes do Ngrok conectar ou o servidor morreu devido a um crash de GPU. Dê Restart Session no Kaggle.Address already in use: Você rodou a célula mais de uma vez. Reinicie a sessão.FileNotFoundError: Adapter manifest not found: O script não conseguiu mover o manifest.json. Verifique se o repositório do HF contém o arquivo manifest.json.
