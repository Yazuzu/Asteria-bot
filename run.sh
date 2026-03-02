#!/bin/bash
# ═══════════════════════════════════════════════════════
#  run.sh — Astéria Bot Launcher
#  Sobe KoboldCPP (ROCm/AMD) em background e bot em paralelo
# ═══════════════════════════════════════════════════════
cd "$(dirname "$0")"

# ── Configuração ────────────────────────────────────────
KOBOLD_DIR="/home/yuzuki/Projeto/Asteria_v2.3"
KOBOLD_PORT=5001
KOBOLD_LOG="/tmp/koboldcpp.log"

# AMD Radeon iGPU (gfx900/Vega) -> Vulkan é a melhor escolha para compatibilidade
KOBOLD_BIN="$KOBOLD_DIR/koboldcpp-linux-x64"

# Modelo preferido (abliterated = RP sem censura)
MODELO="$KOBOLD_DIR/models/Llama-3.2-3B-Instruct-abliterated.Q6_K.gguf"

# Fallback: qualquer .gguf disponível
if [ ! -f "$MODELO" ]; then
    MODELO=$(find "$KOBOLD_DIR/models" -name "*.gguf" | head -1)
fi

# ── Inicia KoboldCPP se não estiver rodando ─────────────
kobold_running() {
    curl -s --max-time 2 "http://localhost:${KOBOLD_PORT}/api/v1/model" > /dev/null 2>&1
}

if kobold_running; then
    echo "✅ KoboldCPP já está rodando na porta ${KOBOLD_PORT}."
else
    if [ ! -f "$KOBOLD_BIN" ]; then
        echo "⚠️  Binário KoboldCPP não encontrado — bot iniciará sem LLM."
    elif [ -z "$MODELO" ] || [ ! -f "$MODELO" ]; then
        echo "⚠️  Nenhum modelo .gguf encontrado — bot iniciará sem LLM."
    else
        echo "🧠 Iniciando KoboldCPP (Vulkan Acceleration) em background..."
        echo "   Modelo: $(basename $MODELO)"
        echo "   Log:    $KOBOLD_LOG"

        # Variáveis ROCm para AMD Radeon Vega (iGPU)
        HSA_OVERRIDE_GFX_VERSION=9.0.0 \
        "$KOBOLD_BIN" \
            --model "$MODELO" \
            --port "$KOBOLD_PORT" \
            --contextsize 4096 \
            --threads 8 \
            --usevulkan 0 \
            --gpulayers 35 \
            --quiet \
            > "$KOBOLD_LOG" 2>&1 &

        echo "   PID: $! (carregando em background...)"
        echo "   Use 'tail -f $KOBOLD_LOG' para acompanhar a inicialização."
    fi
fi

# ── Venv ────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "⚙️  Criando venv Python..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📦 Instalando dependências..."
    pip install -q -r requirements.txt
else
    source venv/bin/activate
fi

# ── Bot (sobe imediatamente, sem esperar o KoboldCPP) ───
echo ""
echo "🌸 Iniciando Astéria Bot..."
echo "══════════════════════════════"
echo "   (Astéria responderá normalmente assim que o LLM carregar)"
echo ""
python main.py
